# Opens one experiment window per ticker (arms B and C, see run_experiment.ps1).
# Rerun to resume after an interruption: finished cells are skipped.
param([string[]]$Tickers = @("NVDA", "AAPL", "MSFT", "AMZN", "JPM"))
foreach ($t in $Tickers) {
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSScriptRoot\run_experiment.ps1`"", '-Ticker', $t
    )
    Start-Sleep 30   # stagger start-up: five simultaneous Reddit fetches got rate-limited (429) last time
}
