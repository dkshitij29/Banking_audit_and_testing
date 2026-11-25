# Run every test-set sample for one or more tickers, one ticker after another,
# each ticker's samples oldest date first.
#
#   .\run_dataset.ps1 -Tickers NVDA
#   .\run_dataset.ps1 -Tickers "NVDA,JPM,WMT" -Dataset dataset\test_set_v1.csv -RunPrefix ds1
#   .\run_dataset.ps1 -Tickers NVDA -RunPrefix gemma_ds1 -BackendUrl http://localhost:9003/v1 -Model gemma-4-12B
#   .\run_dataset.ps1 -Tickers NVDA -RunPrefix gemma_ind_ds1 -BackendUrl http://localhost:9003/v1 -Model gemma-4-12B -ExtraIndicators
#
# -BackendUrl and -Model override TradingAgents\.env for this window only (both model roles).
# -ExtraIndicators turns on the extra market-analyst indicators (arm C's setting).
# Results: results\backtest\<RunPrefix>_<TICKER>\ (memory log, reports, console log).
# Rerunning resumes: finished samples are skipped. Needs the tunnel running.
# Default settings match the first evaluation: baseline prompts (extra indicators off), FRED off.
param(
    [Parameter(Mandatory)][string]$Tickers,
    [string]$Dataset = "$PSScriptRoot\dataset\test_set_v1.csv",
    [string]$RunPrefix = "ds1",
    [string]$BackendUrl = "",
    [string]$Model = "",
    [switch]$ExtraIndicators
)
$list = $Tickers -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$Host.UI.RawUI.WindowTitle = "Test set $RunPrefix - $($list -join ', ')"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"
$env:TRADINGAGENTS_EXTRA_INDICATORS = if ($ExtraIndicators) { "true" } else { "false" }
# .env is loaded without override, so variables set here win
if ($BackendUrl) { $env:TRADINGAGENTS_LLM_BACKEND_URL = $BackendUrl }
if ($Model) { $env:TRADINGAGENTS_DEEP_THINK_LLM = $Model; $env:TRADINGAGENTS_QUICK_THINK_LLM = $Model }
Set-Location "$PSScriptRoot\TradingAgents"   # .env (model, log locations) is read from here

$all = @(Import-Csv $Dataset)
foreach ($ticker in $list) {
    $samples = @($all | Where-Object { $_.ticker -eq $ticker } | Sort-Object date)
    if ($samples.Count -eq 0) { Write-Host "No samples for $ticker in $Dataset" -ForegroundColor Red; continue }

    $runId = "${RunPrefix}_$ticker"
    $runDir = "$PSScriptRoot\results\backtest\$runId"
    New-Item -ItemType Directory -Force $runDir | Out-Null
    $log = "$runDir\backtest_console.log"

    foreach ($s in $samples) {
        $header = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') sample $($s.sample_id): $ticker $($s.date)"
        Write-Host $header -ForegroundColor Cyan
        Add-Content $log $header -Encoding utf8
        & .\.venv\Scripts\tradingagents.exe backtest $ticker --start $s.date --end $s.date --every 1 --run-id $runId 2>&1 |
            ForEach-Object {
                $line = "$_"
                if ($line -notmatch 'Pandas4Warning|pandas\.pydata|inplace=True|^\s+(df|quotes|dividends|splits|data)\.') {
                    Write-Host $line
                    Add-Content $log $line -Encoding utf8
                }
            }
    }
}
Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') done: $($list -join ', ')" -ForegroundColor Green
