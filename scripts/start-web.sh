#!/bin/bash
# ============================================================================
# Avatar Engine — Web Demo Start Script
# ============================================================================
#
# Launches both the Python backend (FastAPI) and React frontend (Vite dev)
# with proper signal handling and cleanup.
#
# Usage:
#   ./scripts/start-web.sh                    # Default (Gemini, port 8420)
#   ./scripts/start-web.sh --provider claude   # Use Claude provider
#   ./scripts/start-web.sh --port 9000         # Custom backend port
#   ./scripts/start-web.sh --build             # Serve production build only
#
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Navigate to project root
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
WEB_DEMO_DIR="$PROJECT_ROOT/examples/web-demo"

# Defaults
PROVIDER="gemini"
MODEL=""
BACKEND_PORT=8420
FRONTEND_PORT=5173
CONFIG=""
WORKING_DIR=""
BUILD_MODE=false
LOG_LEVEL="INFO"

# PIDs for cleanup
BACKEND_PID=""
FRONTEND_PID=""

# ============================================================================
# Argument parsing
# ============================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--provider)
            PROVIDER="$2"; shift 2 ;;
        -m|--model)
            MODEL="$2"; shift 2 ;;
        --port)
            BACKEND_PORT="$2"; shift 2 ;;
        --frontend-port)
            FRONTEND_PORT="$2"; shift 2 ;;
        -c|--config)
            CONFIG="$2"; shift 2 ;;
        -w|--working-dir)
            WORKING_DIR="$2"; shift 2 ;;
        --build)
            BUILD_MODE=true; shift ;;
        --log-level)
            LOG_LEVEL="$2"; shift 2 ;;
        -h|--help)
            echo "Avatar Engine — Web Demo Start Script"
            echo ""
            echo "Usage: ./scripts/start-web.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -p, --provider NAME    AI provider: gemini, claude, codex (default: gemini)"
            echo "  -m, --model NAME       Model name override"
            echo "  --port PORT            Backend port (default: 8420)"
            echo "  --frontend-port PORT   Frontend dev port (default: 5173)"
            echo "  -c, --config PATH      Path to YAML config file"
            echo "  -w, --working-dir DIR  Working directory for AI session"
            echo "  --build                Production mode: build frontend and serve via backend"
            echo "  --log-level LEVEL      Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)"
            echo "  -h, --help             Show this help"
            echo ""
            echo "Examples:"
            echo "  ./scripts/start-web.sh"
            echo "  ./scripts/start-web.sh --provider claude --model claude-sonnet-4-5"
            echo "  ./scripts/start-web.sh --build"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}" >&2
            exit 1
            ;;
    esac
done

# ============================================================================
# Cleanup handler
# ============================================================================

cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"

    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null
        wait "$FRONTEND_PID" 2>/dev/null
        echo -e "${DIM}  Frontend stopped${NC}"
    fi

    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null
        wait "$BACKEND_PID" 2>/dev/null
        echo -e "${DIM}  Backend stopped${NC}"
    fi

    echo -e "${GREEN}Done.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# ============================================================================
# Preflight checks
# ============================================================================

# Check uv
if ! command -v uv &> /dev/null; then
    echo -e "${RED}uv not found. Run ./install.sh first.${NC}" >&2
    exit 1
fi

# Check venv
if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo -e "${RED}Virtual environment not found. Run ./install.sh first.${NC}" >&2
    exit 1
fi

# uv run extras — ensures fastapi + cli deps are available
UV_EXTRAS="--extra cli --extra web"

# Check web extra installed
if ! uv run $UV_EXTRAS python -c "import fastapi" 2>/dev/null; then
    echo -e "${RED}FastAPI not installed. Run: ./install.sh --web${NC}" >&2
    exit 1
fi

# ============================================================================
# Build backend command
# ============================================================================

BACKEND_CMD="uv run $UV_EXTRAS python -m avatar_engine.web"
BACKEND_CMD="$BACKEND_CMD --provider $PROVIDER"
BACKEND_CMD="$BACKEND_CMD --port $BACKEND_PORT"
BACKEND_CMD="$BACKEND_CMD --log-level $LOG_LEVEL"

if [ -n "$MODEL" ]; then
    BACKEND_CMD="$BACKEND_CMD --model $MODEL"
fi
if [ -n "$CONFIG" ]; then
    BACKEND_CMD="$BACKEND_CMD --config $CONFIG"
fi
if [ -n "$WORKING_DIR" ]; then
    BACKEND_CMD="$BACKEND_CMD --working-dir $WORKING_DIR"
fi

# ============================================================================
# Production build mode
# ============================================================================

if $BUILD_MODE; then
    echo -e "${MAGENTA}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║   Avatar Engine — Web Demo (Production)  ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"

    # Build frontend
    if [ ! -d "$WEB_DEMO_DIR" ]; then
        echo -e "${RED}Web demo directory not found: $WEB_DEMO_DIR${NC}" >&2
        exit 1
    fi

    echo -e "${CYAN}Building frontend...${NC}"
    if command -v pnpm &> /dev/null; then
        (cd "$WEB_DEMO_DIR" && pnpm build)
    elif command -v npm &> /dev/null; then
        (cd "$WEB_DEMO_DIR" && npm run build)
    else
        echo -e "${RED}No package manager found (pnpm or npm)${NC}" >&2
        exit 1
    fi

    echo ""
    echo -e "${GREEN}Frontend built. Starting server...${NC}"
    echo -e "${DIM}  Provider:  ${NC}${BOLD}$PROVIDER${NC}"
    if [ -n "$MODEL" ]; then
        echo -e "${DIM}  Model:     ${NC}${BOLD}$MODEL${NC}"
    fi
    echo -e "${DIM}  URL:       ${NC}${BOLD}http://localhost:$BACKEND_PORT${NC}"
    echo ""

    # Run backend with static serving (default)
    exec $BACKEND_CMD
fi

# ============================================================================
# Development mode (backend + frontend dev server)
# ============================================================================

echo -e "${MAGENTA}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   Avatar Engine — Web Demo (Development)     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${DIM}  Provider:  ${NC}${BOLD}$PROVIDER${NC}"
if [ -n "$MODEL" ]; then
    echo -e "${DIM}  Model:     ${NC}${BOLD}$MODEL${NC}"
fi
echo -e "${DIM}  Backend:   ${NC}${BOLD}http://localhost:$BACKEND_PORT${NC}"
echo -e "${DIM}  Frontend:  ${NC}${BOLD}http://localhost:$FRONTEND_PORT${NC}"
echo -e "${DIM}  WebSocket: ${NC}${BOLD}ws://localhost:$BACKEND_PORT/api/avatar/ws${NC}"
echo ""
echo -e "${DIM}  Press Ctrl+C to stop both servers${NC}"
echo ""

# Start backend (no static serving in dev mode — Vite serves frontend)
BACKEND_CMD="$BACKEND_CMD --no-static"

echo -e "${BLUE}Starting backend...${NC}"
$BACKEND_CMD &
BACKEND_PID=$!

# Wait a moment for backend to bind
sleep 1

# Check backend started
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo -e "${RED}Backend failed to start${NC}" >&2
    exit 1
fi

# Start frontend dev server
if [ ! -d "$WEB_DEMO_DIR" ]; then
    echo -e "${RED}Web demo directory not found: $WEB_DEMO_DIR${NC}" >&2
    exit 1
fi

if [ ! -d "$WEB_DEMO_DIR/node_modules" ]; then
    echo -e "${YELLOW}Frontend deps not installed. Installing...${NC}"
    if command -v pnpm &> /dev/null; then
        (cd "$WEB_DEMO_DIR" && pnpm install)
    elif command -v npm &> /dev/null; then
        (cd "$WEB_DEMO_DIR" && npm install)
    else
        echo -e "${RED}No package manager found (pnpm or npm)${NC}" >&2
        exit 1
    fi
fi

echo -e "${BLUE}Starting frontend dev server...${NC}"
if command -v pnpm &> /dev/null; then
    (cd "$WEB_DEMO_DIR" && pnpm dev --port "$FRONTEND_PORT") &
elif command -v npm &> /dev/null; then
    (cd "$WEB_DEMO_DIR" && npm run dev -- --port "$FRONTEND_PORT") &
fi
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}Both servers running. Open ${BOLD}http://localhost:$FRONTEND_PORT${NC}${GREEN} in your browser.${NC}"
echo ""

# Wait for either process to exit
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
