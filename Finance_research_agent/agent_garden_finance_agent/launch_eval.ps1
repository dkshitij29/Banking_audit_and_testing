# Starts one backtest window per ticker, in parallel, all sharing the same date grid.
# Each ticker gets its own run folder: results\backtest\eval_<TICKER>\
# Rerun this script to resume: finished cells are skipped.
# Needs the tunnel (start_tunnel.ps1) running.
param(
    [string[]]$Tickers = @("NVDA", "AAPL", "MSFT", "AMZN", "JPM"),
    [string]$Start = "2026-07-20",
    [string]$End = "2026-09-28",
    [int]$Every = 14
)
foreach ($t in $Tickers) {
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSScriptRoot\run_backtest.ps1`"",
        '-Tickers', $t, '-Start', $Start, '-End', $End, '-Every', $Every, '-RunId', "eval_$t"
    )
    Start-Sleep 3   # stagger start-up so the data fetches don't all hit Yahoo at once
}
