#!/usr/bin/env bash
set -e

# ─── Finance Research Agent — Start Script ───────────────────────────────────
# Starts both the backend (uvicorn on :8000) and frontend (Vite on :5173).
# Kill either terminal or Ctrl+C to stop everything.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Color helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         Finance Research Agent — Starting Up                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Pre-flight checks ────────────────────────────────────────────────────────

# Python / venv
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠  Virtual environment not found. Creating one...${NC}"
    uv venv || python3 -m venv .venv
fi

if [ ! -f ".env" ]; then
    echo -e "${RED}✗  .env file missing. Copying .env.example → .env${NC}"
    cp .env.example .env
    echo -e "${YELLOW}   Edit .env to configure your LLM provider.${NC}"
    echo ""
fi

# Install Python deps (fast no-op if already done)
echo -e "${CYAN}📦 Installing Python dependencies...${NC}"
source .venv/bin/activate
uv pip install -e ".[dev,openai]" --quiet 2>/dev/null

# Node / frontend
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}⚠  Frontend dependencies not installed.${NC}"
    if command -v npm &> /dev/null; then
        echo -e "${CYAN}📦 Installing frontend dependencies...${NC}"
        (cd frontend && npm install --silent)
    else
        echo -e "${RED}✗  npm not found. Cannot start frontend.${NC}"
        echo "   Skipping frontend — starting backend only."
        SKIP_FRONTEND=true
    fi
fi

# ── Show config ──────────────────────────────────────────────────────────────
PROVIDER=$(grep -E "^LLM_PROVIDER=" .env 2>/dev/null | cut -d= -f2 || echo "openai")
MODEL=$(grep -E "^LLM_MODEL=" .env 2>/dev/null | cut -d= -f2 || echo "gpt-4o")
BASE_URL=$(grep -E "^VLLM_BASE_URL=" .env 2>/dev/null | cut -d= -f2- || echo "N/A")

echo -e "${GREEN}✓${NC}  LLM Provider : $PROVIDER"
echo -e "${GREEN}✓${NC}  Model        : $MODEL"
if [ "$PROVIDER" = "vllm" ]; then
    echo -e "${GREEN}✓${NC}  Base URL     : $BASE_URL
"
fi

# ── Trap Ctrl+C ──────────────────────────────────────────────────────────────
PIDS=()
cleanup() {
    echo -e "\n${YELLOW}⏹  Shutting down...${NC}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null && echo -e "${GREEN}✓${NC}  Stopped PID $pid"
    done
    wait 2>/dev/null
    echo -e "${CYAN}Done.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Start Backend ─────────────────────────────────────────────────────────────
echo -e "${CYAN}🚀 Starting backend on http://localhost:8000${NC}"
PYDANTIC_AI_NO_BANNER=1 .venv/bin/python -m uvicorn agent.api.server:app \
    --host 0.0.0.0 --port 8000 &
PIDS+=($!)

# Wait for backend to be ready
echo -n "   Waiting for backend..."
for i in $(seq 1 20); do
    if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
        echo -e " ${GREEN}✓ ready${NC}"
        break
    fi
    sleep 0.5
done

# ── Start Frontend (if not skipped) ───────────────────────────────────────────
if [ "$SKIP_FRONTEND" != true ]; then
    echo -e "${CYAN}🚀 Starting frontend on http://localhost:5173${NC}"
    (cd frontend && npx vite --host 0.0.0.0 --port 5173) &
    PIDS+=($!)
    echo -e "   ${GREEN}✓ ready${NC}"
fi

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Backend API  → http://localhost:8000${NC}"
echo -e "${GREEN}  API Docs     → http://localhost:8000/docs${NC}"
if [ "$SKIP_FRONTEND" != true ]; then
    echo -e "${GREEN}  Frontend     → http://localhost:5173${NC}"
fi
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Press Ctrl+C to stop${NC}"
echo ""

# ── Wait for background processes ────────────────────────────────────────────
wait
