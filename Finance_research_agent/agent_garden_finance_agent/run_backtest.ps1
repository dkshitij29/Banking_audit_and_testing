# Runs a TradingAgents backtest and saves everything under results\backtest\<run-id>\.
#
#   .\run_backtest.ps1                                   # NVDA,AAPL, 2026-09-21..2026-10-19, every 14 days
#   .\run_backtest.ps1 -Tickers MSFT,GOOGL -Start 2026-08-03 -End 2026-10-19 -Every 7
#   .\run_backtest.ps1 -RunId 20261029_200000            # resume a stopped run (finished cells are skipped)
#
# Needs the tunnel (start_tunnel.ps1) running in another window.
param(
    [string]$Tickers = "NVDA,AAPL",
    [string]$Start = "2026-09-21",
    [string]$End = "2026-10-19",
    [int]$Every = 14,
    [string]$Analysts = "",
    [string]$RunId = (Get-Date -Format "yyyyMMdd_HHmmss")
)
$Host.UI.RawUI.WindowTitle = "TradingAgents backtest $RunId"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"
Set-Location "$PSScriptRoot\TradingAgents"   # .env (model + log locations) is read from here

$runDir = "$PSScriptRoot\results\backtest\$RunId"
New-Item -ItemType Directory -Force $runDir | Out-Null
$log = "$runDir\backtest_console.log"

$cmd = @("backtest", $Tickers, "--start", $Start, "--end", $End, "--every", $Every, "--run-id", $RunId)
if ($Analysts) { $cmd += @("--analysts", $Analysts) }
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') tradingagents $($cmd -join ' ')" | Add-Content $log -Encoding utf8

& .\.venv\Scripts\tradingagents.exe @cmd 2>&1 | ForEach-Object {
    $line = "$_"
    if ($line -notmatch 'Pandas4Warning|pandas\.pydata|inplace=True|^\s+(df|quotes|dividends|splits)\.') {
        Write-Host $line
        Add-Content $log $line -Encoding utf8
    }
}
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') finished" | Add-Content $log -Encoding utf8
Write-Host "`nBacktest finished. Results and logs: $runDir" -ForegroundColor Green
