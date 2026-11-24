# Runs the whole test set in a few parallel windows (see run_dataset.ps1).
# The tickers are dealt out round-robin, so each window works through 2-3 stocks.
# Rerun to resume after an interruption: finished samples are skipped.
#
#   .\launch_dataset.ps1                  # 4 windows
#   .\launch_dataset.ps1 -Windows 3       # gentler on the shared GPU
#   .\launch_dataset.ps1 -RunPrefix gemma_ds1 -BackendUrl http://localhost:9003/v1 -Model gemma-4-12B
#   .\launch_dataset.ps1 -RunPrefix gemma_ind_ds1 -BackendUrl http://localhost:9003/v1 -Model gemma-4-12B -ExtraIndicators
param(
    [string]$Dataset = "$PSScriptRoot\dataset\test_set_v1.csv",
    [string]$RunPrefix = "ds1",
    [int]$Windows = 4,     # 5 parallel runs overloaded the shared GPU last time
    [string]$BackendUrl = "",   # override the model server in TradingAgents\.env
    [string]$Model = "",        # override the model name in TradingAgents\.env
    [switch]$ExtraIndicators    # arm C's setting: extra market-analyst indicators on
)
$url = if ($BackendUrl) { $BackendUrl } else {
    (Get-Content "$PSScriptRoot\TradingAgents\.env" | Where-Object { $_ -match '^TRADINGAGENTS_LLM_BACKEND_URL=' }) -replace '^[^=]+=', ''
}
try {
    Invoke-RestMethod "$url/models" -TimeoutSec 10 | Out-Null
} catch {
    Write-Host "The model server is not reachable at $url. Start the tunnel first: .\start_tunnel.ps1" -ForegroundColor Red
    exit 1
}
$tickers = @(Import-Csv $Dataset | Select-Object -ExpandProperty ticker -Unique)
$n = [Math]::Min($Windows, $tickers.Count)
$groups = @(for ($w = 0; $w -lt $n; $w++) { ,@(for ($i = $w; $i -lt $tickers.Count; $i += $n) { $tickers[$i] }) })
foreach ($g in $groups) {
    $runArgs = @(
        '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSScriptRoot\run_dataset.ps1`"",
        '-Tickers', ($g -join ','), '-Dataset', "`"$Dataset`"", '-RunPrefix', $RunPrefix,
        '-BackendUrl', "`"$BackendUrl`"", '-Model', "`"$Model`""
    )
    if ($ExtraIndicators) { $runArgs += '-ExtraIndicators' }
    Start-Process powershell -ArgumentList $runArgs
    Write-Host "Window: $($g -join ', ')"
    Start-Sleep 30   # stagger start-up so the social-data sources are not hit all at once
}
Write-Host "Started $n windows for $($tickers.Count) stocks." -ForegroundColor Green
