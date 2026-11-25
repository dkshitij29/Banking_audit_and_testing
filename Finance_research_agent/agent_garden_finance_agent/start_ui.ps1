# Opens the finance agent's live dashboard for the demo video.
# You type the input (stock, date, analysts); the 12 agents then work live on screen
# until the final decision. When you leave the dashboard, the decision is scored.
#   .\start_ui.ps1                                                   # gemma-4-12B (port 9003)
#   .\start_ui.ps1 -BackendUrl http://localhost:9000/v1 -Model Qwen3.6-27B
#   .\start_ui.ps1 -RunName ui_demo_today          # a second recording with its own log and score
# Needs the tunnel (start_tunnel.ps1) and a running model server. Run it in a normal
# PowerShell window (not inside an editor), maximised, so the dashboard has room.
param(
    [string]$BackendUrl = "http://localhost:9003/v1",
    [string]$Model = "gemma-4-12B",
    [string]$RunName = "ui_demo"
)
$Host.UI.RawUI.WindowTitle = "Finance agent: live demo ($Model)"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"
# Same settings as the experiments; set here so the dashboard only asks for the input
$env:TRADINGAGENTS_LLM_PROVIDER = "openai_compatible"
$env:TRADINGAGENTS_LLM_BACKEND_URL = $BackendUrl
$env:TRADINGAGENTS_DEEP_THINK_LLM = $Model
$env:TRADINGAGENTS_QUICK_THINK_LLM = $Model
$env:TRADINGAGENTS_MAX_DEBATE_ROUNDS = "1"
$env:TRADINGAGENTS_MAX_RISK_ROUNDS = "1"
$env:TRADINGAGENTS_OUTPUT_LANGUAGE = "English"
$env:TRADINGAGENTS_EXTRA_INDICATORS = "false"
# Plain project header instead of the welcome banner, and no "What's new" box
$env:FINANCE_AGENT_DEMO = "1"
$env:TRADINGAGENTS_NO_UPDATE_CHECK = "1"
# Demo decisions go to their own log, apart from the experiment results
$demoDir = "$PSScriptRoot\results\backtest\$RunName"
New-Item -ItemType Directory -Force $demoDir | Out-Null
$env:TRADINGAGENTS_MEMORY_LOG_PATH = "$demoDir\trading_memory.md"

try { Invoke-RestMethod "$BackendUrl/models" -TimeoutSec 10 | Out-Null } catch {
    Write-Host "The model server is not reachable at $BackendUrl. Start the tunnel and check that the lab's model job is running." -ForegroundColor Red
    exit 1
}

Set-Location "$PSScriptRoot\TradingAgents"
& .\.venv\Scripts\tradingagents.exe --save --show --no-html

Write-Host "`n=== Score: did the stock beat the market (SPY) after 5, 10 and 20 trading days? ===`n" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe ..\evaluate.py --name $RunName $RunName
