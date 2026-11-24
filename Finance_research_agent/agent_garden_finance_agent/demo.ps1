# Demo for the video: one live decision by the 12 agents, then its score.
#   .\demo.ps1                       # NVDA on 6 Apr 2026, gemma-4-12B (port 9003)
#   .\demo.ps1 -Ticker JPM -Date 2026-02-23 -BackendUrl http://localhost:9000/v1 -Model Qwen3.6-27B
# Needs the tunnel (start_tunnel.ps1) and a running model server. One decision takes about 10-20 minutes.
param(
    [string]$Ticker = "NVDA",
    [string]$Date = "2026-04-06",
    [string]$BackendUrl = "http://localhost:9003/v1",
    [string]$Model = "gemma-4-12B"
)
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"
$env:TRADINGAGENTS_LLM_BACKEND_URL = $BackendUrl
$env:TRADINGAGENTS_DEEP_THINK_LLM = $Model
$env:TRADINGAGENTS_QUICK_THINK_LLM = $Model
$env:TRADINGAGENTS_EXTRA_INDICATORS = "false"

try { Invoke-RestMethod "$BackendUrl/models" -TimeoutSec 10 | Out-Null } catch {
    Write-Host "The model server is not reachable at $BackendUrl. Start the tunnel and check that the lab's model job is running." -ForegroundColor Red
    exit 1
}
$run = "demo_${Ticker}_$($Date -replace '-', '')"

Write-Host "`n=== 1. Input: $Ticker on $Date, model $Model ===`n" -ForegroundColor Cyan
Set-Location "$PSScriptRoot\TradingAgents"
& .\.venv\Scripts\tradingagents.exe backtest $Ticker --start $Date --end $Date --every 1 --run-id $run 2>&1 |
    ForEach-Object { if ("$_" -notmatch 'Pandas4Warning|pandas\.pydata|inplace=True|^\s+(df|quotes|dividends|splits|data)\.') { Write-Host "$_" } }

Write-Host "`n=== 2. Output: the final decision ===`n" -ForegroundColor Cyan
$log = Get-ChildItem "$PSScriptRoot\results\backtest\$run" -Recurse -Filter "full_states_log_$Date.json" | Select-Object -First 1
if (-not $log) { Write-Host "No decision was saved for $run." -ForegroundColor Red; exit 1 }
$state = Get-Content $log.FullName -Raw -Encoding utf8 | ConvertFrom-Json
Write-Host $state.final_trade_decision

Write-Host "`n=== 3. Score: did the stock beat the market (SPY)? ===`n" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe ..\evaluate.py --name $run $run
