# Indicator experiment for one ticker: on every date, run arm B (repeat baseline,
# extra indicators OFF) and arm C (extra indicators ON) back to back, alternating
# which goes first. Both arms cover the same dates even if the night is cut short.
#
#   .\run_experiment.ps1 -Ticker NVDA
#
# Results: results\backtest\expB_<TICKER>\ and results\backtest\expC_<TICKER>\
# Rerunning resumes: finished cells are skipped. Needs the tunnel running.
param(
    [Parameter(Mandatory)][string]$Ticker,
    [string[]]$Dates = @("2026-07-20", "2026-08-03", "2026-08-17", "2026-08-31", "2026-09-14", "2026-09-28")
)
$Host.UI.RawUI.WindowTitle = "Experiment $Ticker (B = indicators off, C = on)"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"
Set-Location "$PSScriptRoot\TradingAgents"   # .env (model, log locations; FRED stays off) is read from here

function Invoke-Arm([string]$Arm, [string]$Date) {
    $env:TRADINGAGENTS_EXTRA_INDICATORS = if ($Arm -eq "C") { "true" } else { "false" }
    $runId = "exp${Arm}_$Ticker"
    $runDir = "$PSScriptRoot\results\backtest\$runId"
    New-Item -ItemType Directory -Force $runDir | Out-Null
    $log = "$runDir\backtest_console.log"
    $header = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') arm $Arm, extra_indicators=$env:TRADINGAGENTS_EXTRA_INDICATORS, $Ticker $Date"
    Write-Host $header -ForegroundColor Cyan
    Add-Content $log $header -Encoding utf8
    & .\.venv\Scripts\tradingagents.exe backtest $Ticker --start $Date --end $Date --every 1 --run-id $runId 2>&1 |
        ForEach-Object {
            $line = "$_"
            if ($line -notmatch 'Pandas4Warning|pandas\.pydata|inplace=True|^\s+(df|quotes|dividends|splits)\.') {
                Write-Host $line
                Add-Content $log $line -Encoding utf8
            }
        }
}

for ($i = 0; $i -lt $Dates.Count; $i++) {
    $order = if ($i % 2 -eq 0) { @("B", "C") } else { @("C", "B") }
    foreach ($arm in $order) { Invoke-Arm $arm $Dates[$i] }
}
Write-Host "`nExperiment for $Ticker finished." -ForegroundColor Green
