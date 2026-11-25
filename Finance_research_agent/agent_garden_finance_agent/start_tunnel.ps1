# Keeps the SSH tunnel to the lab's vLLM servers on slurm-comp01 open:
#   localhost:9000 -> Qwen3.6-27B   (the lab's usual port)
#   localhost:9002 -> Qwen3.8-27B   (when the lab runs it; it did on 2026-11-18)
#   localhost:9003 -> gemma-4-12B   (served from 2026-11-20)
# The lab swaps models between these ports; TradingAgents/.env picks which one we use.
# Reconnects automatically if the connection drops. Close this window to stop it.
#
# Your lab login is read from environment variables (see .env.example), never stored here:
#   $env:LAB_SSH_USER = "<your lab user>"; $env:LAB_SSH_HOST = "<lab login host>"
#   $env:LAB_SSH_KEY  = "$HOME\.ssh\<your key file>"     (optional; default id_ed25519)
param(
    [string]$User = $env:LAB_SSH_USER,
    [string]$LabHost = $env:LAB_SSH_HOST,
    [string]$Key = $(if ($env:LAB_SSH_KEY) { $env:LAB_SSH_KEY } else { "$HOME\.ssh\id_ed25519" })
)
if (-not $User -or -not $LabHost) {
    Write-Host "Set LAB_SSH_USER and LAB_SSH_HOST first (see .env.example)." -ForegroundColor Red
    exit 1
}
$Host.UI.RawUI.WindowTitle = "vLLM tunnel (localhost:9000, 9002 and 9003)"
while ($true) {
    Write-Host "$(Get-Date -Format HH:mm:ss) connecting tunnel..." -ForegroundColor Cyan
    ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 `
        -i $Key -L 9000:slurm-comp01:9000 -L 9002:slurm-comp01:9002 -L 9003:slurm-comp01:9003 "$User@$LabHost"
    Write-Host "$(Get-Date -Format HH:mm:ss) tunnel exited ($LASTEXITCODE), reconnecting in 5s" -ForegroundColor Yellow
    Start-Sleep 5
}
