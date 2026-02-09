#!/bin/bash
# ============================================================================
# Avatar Engine - Install Script
# ============================================================================
#
# Installs dependencies using the uv package manager.
# Supports selective installation of AI agent providers:
#   - Gemini CLI  (Google Gemini)
#   - Claude Code (Anthropic Claude)
#   - Codex CLI   (OpenAI Codex via codex-acp)
#
# Usage:
#   ./install.sh              # Full installation (interactive)
#   ./install.sh --check      # Check dependencies
#   ./install.sh --setup-cli  # Install AI agent CLIs (interactive)
#   ./install.sh --all        # Install everything without prompts
#
# ============================================================================

set -e

# ============================================================================
# Detect the parent shell (the shell that invoked this script)
# ============================================================================

detect_parent_shell() {
    local parent_comm
    parent_comm=$(ps -p "$PPID" -o comm= 2>/dev/null || echo "")

    if [[ "$parent_comm" == *fish* ]]; then
        PARENT_SHELL="fish"
    elif [[ "$parent_comm" == *zsh* ]]; then
        PARENT_SHELL="zsh"
    else
        PARENT_SHELL="bash"
    fi
}

detect_parent_shell

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Selected providers (global)
INSTALL_GEMINI=false
INSTALL_CLAUDE=false
INSTALL_CODEX=false
INSTALL_WEB=false

print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"
}

print_ok() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}!${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# ============================================================================
# Provider selection menu
# ============================================================================

select_providers() {
    print_header "Select AI Agent Providers"

    echo -e "Avatar Engine supports multiple AI providers."
    echo -e "Select which ones you want to install:\n"

    # Detect what's already installed
    local gemini_status="" claude_status="" codex_status=""
    if command -v gemini &> /dev/null; then
        gemini_status=" ${DIM}(already installed)${NC}"
    fi
    if command -v claude &> /dev/null; then
        claude_status=" ${DIM}(already installed)${NC}"
    fi
    if command -v codex &> /dev/null; then
        codex_status=" ${DIM}(already installed)${NC}"
    fi

    echo -e "  ${BOLD}1)${NC} ${CYAN}Gemini CLI${NC}  — Google Gemini (free tier / Pro / Max)${gemini_status}"
    echo -e "     ${DIM}sudo npm install -g @google/gemini-cli${NC}"
    echo ""
    echo -e "  ${BOLD}2)${NC} ${CYAN}Claude Code${NC} — Anthropic Claude (Pro / Max subscription)${claude_status}"
    echo -e "     ${DIM}sudo npm install -g @anthropic-ai/claude-code${NC}"
    echo ""
    echo -e "  ${BOLD}3)${NC} ${CYAN}Codex CLI${NC}   — OpenAI Codex (Plus / Pro subscription)${codex_status}"
    echo -e "     ${DIM}sudo npm install -g @openai/codex${NC}"
    echo -e "     ${DIM}+ npx @zed-industries/codex-acp (ACP adapter)${NC}"
    echo ""
    echo -e "  ${BOLD}a)${NC} All providers"
    echo -e "  ${BOLD}n)${NC} None (Python library only, install CLIs later)"
    echo ""

    read -p "Enter your choices (e.g. 1,2 or a for all): " -r choices
    echo ""

    if [[ "$choices" == "a" || "$choices" == "A" ]]; then
        INSTALL_GEMINI=true
        INSTALL_CLAUDE=true
        INSTALL_CODEX=true
    elif [[ "$choices" == "n" || "$choices" == "N" || -z "$choices" ]]; then
        print_warn "No providers selected. You can install them later with ./install.sh --setup-cli"
        return
    else
        if [[ "$choices" == *"1"* ]]; then INSTALL_GEMINI=true; fi
        if [[ "$choices" == *"2"* ]]; then INSTALL_CLAUDE=true; fi
        if [[ "$choices" == *"3"* ]]; then INSTALL_CODEX=true; fi
    fi

    # Summary
    echo -e "Selected providers:"
    if $INSTALL_GEMINI; then print_ok "Gemini CLI"; fi
    if $INSTALL_CLAUDE; then print_ok "Claude Code"; fi
    if $INSTALL_CODEX; then print_ok "Codex CLI (codex-acp)"; fi
    echo ""
}

# ============================================================================
# Dependency check
# ============================================================================

check_command() {
    if command -v "$1" &> /dev/null; then
        print_ok "$1 found: $(command -v "$1")"
        return 0
    else
        print_warn "$1 not found"
        return 1
    fi
}

check_python_module() {
    local python_bin="$1"
    local module_name="$2"
    local display_name="$3"
    local required="${4:-false}"

    if "$python_bin" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$module_name') else 1)" &> /dev/null; then
        print_ok "${display_name} installed"
        return 0
    fi

    if [[ "$required" == "true" ]]; then
        print_warn "${display_name} missing"
    else
        print_warn "${display_name} missing (optional)"
    fi
    return 1
}

check_acp_module() {
    local python_bin="$1"
    if "$python_bin" -c "import importlib.util, sys; sys.exit(0 if (importlib.util.find_spec('acp') or importlib.util.find_spec('agent_client_protocol')) else 1)" &> /dev/null; then
        print_ok "agent-client-protocol (ACP) installed"
        return 0
    fi
    print_warn "agent-client-protocol (ACP) missing"
    return 1
}

check_dependencies() {
    print_header "Checking dependencies"

    print_ok "Detected shell: ${PARENT_SHELL}"
    echo ""

    local all_ok=true

    # Python
    if check_command python3; then
        echo "    Version: $(python3 --version)"
    else
        all_ok=false
    fi

    # uv
    if check_command uv; then
        echo "    Version: $(uv --version)"
    else
        all_ok=false
    fi

    # Node.js (for CLI tools)
    if check_command node; then
        echo "    Version: $(node --version)"
    else
        print_warn "Node.js is required for AI CLI tools"
    fi

    # npm / npx
    if check_command npm; then
        echo "    Version: $(npm --version)"
    else
        print_warn "npm is required for AI CLI tools"
    fi

    # --- AI Agent CLIs ---
    echo ""
    echo -e "${BOLD}AI Agent CLIs:${NC}"

    # Gemini CLI
    if check_command gemini; then
        echo "    Version: $(gemini --version 2>/dev/null || echo 'N/A')"
    else
        print_warn "Gemini CLI is not installed"
        echo "    Install: sudo npm install -g @google/gemini-cli"
    fi

    # Claude Code
    if check_command claude; then
        echo "    Version: $(claude --version 2>/dev/null || echo 'N/A')"
    else
        print_warn "Claude Code is not installed"
        echo "    Install: sudo npm install -g @anthropic-ai/claude-code"
    fi

    # Codex CLI
    if check_command codex; then
        echo "    Version: $(codex --version 2>/dev/null || echo 'N/A')"
    else
        print_warn "Codex CLI is not installed"
        echo "    Install: sudo npm install -g @openai/codex"
    fi

    # codex-acp adapter
    if command -v codex-acp &> /dev/null; then
        print_ok "codex-acp adapter found: $(which codex-acp)"
    elif command -v npx &> /dev/null; then
        if timeout 5 npx --yes @zed-industries/codex-acp --help &> /dev/null; then
            print_ok "codex-acp adapter found (via npx)"
        else
            print_warn "codex-acp adapter not cached"
            echo "    Pre-fetch: npx @zed-industries/codex-acp --help"
        fi
    else
        print_warn "codex-acp adapter requires npx (Node.js)"
    fi

    # --- Python package dependencies ---
    echo ""
    echo -e "${BOLD}Python packages:${NC}"
    local python_bin=""
    if [ -x ".venv/bin/python" ]; then
        python_bin=".venv/bin/python"
        print_ok "Using project venv: ${python_bin}"
    elif command -v python3 &> /dev/null; then
        python_bin="$(command -v python3)"
        print_warn "Project venv not found, checking system Python: ${python_bin}"
    fi

    if [ -n "$python_bin" ]; then
        check_python_module "$python_bin" "click" "click (CLI)" true || all_ok=false
        check_python_module "$python_bin" "rich" "rich (CLI rendering)" true || all_ok=false
        check_python_module "$python_bin" "prompt_toolkit" "prompt_toolkit (REPL input)" true || all_ok=false
        check_acp_module "$python_bin" || all_ok=false
    else
        print_warn "Python interpreter unavailable for package checks"
        all_ok=false
    fi

    echo "    Install/repair: uv sync --extra cli --extra dev"

    # --- Web demo ---
    echo ""
    echo -e "${BOLD}Web Demo:${NC}"
    if [ -n "$python_bin" ]; then
        check_python_module "$python_bin" "fastapi" "fastapi (web server)" false || true
        check_python_module "$python_bin" "uvicorn" "uvicorn (ASGI server)" false || true
    fi
    if [ -d "examples/web-demo/node_modules" ]; then
        print_ok "Web demo frontend deps installed"
    else
        print_warn "Web demo frontend deps not installed"
        echo "    Install: ./install.sh --web"
    fi

    echo ""
    if $all_ok; then
        print_ok "All base dependencies are satisfied"
    else
        print_error "Some dependencies are missing"
    fi
}

# ============================================================================
# Install uv
# ============================================================================

install_uv() {
    if command -v uv &> /dev/null; then
        print_ok "uv is already installed"
        return 0
    fi

    print_header "Installing uv"

    # Try pacman
    if command -v pacman &> /dev/null; then
        echo "Trying pacman..."
        if pacman -Ss "^python-uv$" &> /dev/null; then
            sudo pacman -S --noconfirm python-uv
            print_ok "uv installed via pacman"
            return 0
        fi
    fi

    # Try AUR helper
    for helper in yay paru; do
        if command -v $helper &> /dev/null; then
            echo "Trying $helper..."
            $helper -S --noconfirm python-uv 2>/dev/null && {
                print_ok "uv installed via $helper"
                return 0
            }
        fi
    done

    # Fallback: official installer
    echo "Installing via official script..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uv &> /dev/null; then
        print_ok "uv installed"
    else
        print_error "uv installation failed"
        exit 1
    fi
}

# ============================================================================
# Install CLI tools (respects provider selection)
# ============================================================================

install_cli_tools() {
    # If no providers selected yet, ask
    if ! $INSTALL_GEMINI && ! $INSTALL_CLAUDE && ! $INSTALL_CODEX; then
        select_providers
    fi

    # Nothing to install
    if ! $INSTALL_GEMINI && ! $INSTALL_CLAUDE && ! $INSTALL_CODEX; then
        return 0
    fi

    print_header "Installing AI Agent CLIs"

    # Check npm (all providers need it)
    if ($INSTALL_GEMINI || $INSTALL_CLAUDE || $INSTALL_CODEX) && ! command -v npm &> /dev/null; then
        print_error "npm is not installed!"
        echo "Install Node.js: sudo pacman -S nodejs npm"
        exit 1
    fi

    # --- Gemini CLI ---
    if $INSTALL_GEMINI; then
        echo -e "\n${YELLOW}Gemini CLI:${NC}"
        if command -v gemini &> /dev/null; then
            print_ok "Already installed"
        else
            echo "Installing @google/gemini-cli..."
            sudo npm install -g @google/gemini-cli
            print_ok "Gemini CLI installed"
        fi
    fi

    # --- Claude Code ---
    if $INSTALL_CLAUDE; then
        echo -e "\n${YELLOW}Claude Code:${NC}"
        if command -v claude &> /dev/null; then
            print_ok "Already installed"
        else
            echo "Installing @anthropic-ai/claude-code..."
            sudo npm install -g @anthropic-ai/claude-code
            print_ok "Claude Code installed"
        fi
    fi

    # --- Codex CLI ---
    if $INSTALL_CODEX; then
        echo -e "\n${YELLOW}Codex CLI:${NC}"
        # 1. Install Codex CLI itself
        if command -v codex &> /dev/null; then
            print_ok "Codex CLI already installed"
        else
            echo "Installing @openai/codex..."
            sudo npm install -g @openai/codex
            print_ok "Codex CLI installed"
        fi
        # 2. Pre-fetch codex-acp adapter (ACP bridge for Avatar Engine)
        echo "Pre-fetching @zed-industries/codex-acp (ACP adapter)..."
        if timeout 15 npx --yes @zed-industries/codex-acp --help &> /dev/null; then
            print_ok "codex-acp adapter cached via npx"
        else
            print_warn "codex-acp pre-fetch failed (will be fetched on first use)"
        fi
    fi

    # --- Sign-in instructions ---
    echo ""
    print_ok "CLI tools installed"
    echo ""
    echo "To sign in, run:"
    if $INSTALL_GEMINI; then
        echo "  gemini           # Sign in with Google account"
    fi
    if $INSTALL_CLAUDE; then
        echo "  claude           # Sign in with Anthropic account (Pro/Max)"
    fi
    if $INSTALL_CODEX; then
        echo "  codex login      # Sign in with ChatGPT account (Plus/Pro)"
    fi
}

# ============================================================================
# Install Python dependencies
# ============================================================================

install_python_deps() {
    print_header "Installing Python dependencies"

    # Create venv if it doesn't exist
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment..."
        uv venv
    fi

    # Build the extras list
    local extras="--extra cli"
    if $INSTALL_WEB; then
        extras="$extras --extra web"
    fi

    echo "Installing project dependencies (core + CLI extras)..."
    uv sync $extras

    # Development tools (optional extra)
    read -p "Install development tools extra ([dev]: pytest, ruff, mypy)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        uv sync $extras --extra dev
    fi

    print_ok "Python dependencies installed"
}

# ============================================================================
# Install Web Demo dependencies (React frontend)
# ============================================================================

install_web_demo() {
    if ! $INSTALL_WEB; then
        return 0
    fi

    print_header "Installing Web Demo (React frontend)"

    local web_dir="examples/web-demo"
    if [ ! -d "$web_dir" ]; then
        print_error "Web demo directory not found: $web_dir"
        return 1
    fi

    # Detect package manager (prefer pnpm > npm)
    local pkg_cmd=""
    if command -v pnpm &> /dev/null; then
        pkg_cmd="pnpm"
        print_ok "Using pnpm: $(pnpm --version)"
    elif command -v npm &> /dev/null; then
        pkg_cmd="npm"
        print_ok "Using npm: $(npm --version)"
    else
        print_error "No Node.js package manager found (pnpm or npm required)"
        echo "Install Node.js: sudo pacman -S nodejs npm"
        echo "Or install pnpm: npm install -g pnpm"
        return 1
    fi

    echo "Installing frontend dependencies in $web_dir..."
    (cd "$web_dir" && $pkg_cmd install)

    print_ok "Web demo frontend dependencies installed"
    echo ""
    echo "To start the web demo:"
    echo "  ./scripts/start-web.sh"
    echo ""
    echo "Or manually:"
    echo "  uv run avatar-web --provider gemini  # Backend (port 8420)"
    echo "  cd examples/web-demo && $pkg_cmd dev  # Frontend (port 5173)"
}

# ============================================================================
# Create activation scripts
# ============================================================================

create_activate_script() {
    print_header "Creating activation scripts"

    # --- activate.sh (bash/zsh) ---
    cat > activate.sh << 'EOF'
#!/bin/bash
# Avatar Engine - Activation script
# Usage: source activate.sh

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "✗ Virtual environment not found, run ./install.sh"
    return 1
fi

# Set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Info
echo ""
echo "Avatar Engine ready!"
echo "  Provider from .avatar.yaml: $(grep '^provider:' .avatar.yaml 2>/dev/null | awk '{print $2}')"
echo ""
echo "Commands:"
echo "  uv run avatar repl          # Interactive REPL"
echo "  ./scripts/start-web.sh      # Web Demo (React UI)"
EOF
    chmod +x activate.sh
    print_ok "Created activate.sh (bash/zsh)"

    # --- activate.fish ---
    cat > activate.fish << 'FISHEOF'
# Avatar Engine - Activation script for fish
# Usage: source activate.fish

# Activate virtual environment
if test -d .venv
    source .venv/bin/activate.fish
    echo "✓ Virtual environment activated"
else
    echo "✗ Virtual environment not found, run ./install.sh"
    return 1
end

# Set PYTHONPATH
set -gx PYTHONPATH "$PYTHONPATH:(pwd)"

# Info
echo ""
echo "Avatar Engine ready!"
set -l provider (grep '^provider:' .avatar.yaml 2>/dev/null | awk '{print $2}')
if test -n "$provider"
    echo "  Provider from .avatar.yaml: $provider"
end
echo ""
echo "Commands:"
echo "  uv run avatar repl          # Interactive REPL"
echo "  ./scripts/start-web.sh      # Web Demo (React UI)"
FISHEOF
    chmod +x activate.fish
    print_ok "Created activate.fish (fish)"
}

# ============================================================================
# Main
# ============================================================================

main() {
    cd "$(dirname "$0")"

    case "${1:-}" in
        --check)
            check_dependencies
            ;;
        --setup-cli)
            select_providers
            install_cli_tools
            ;;
        --web)
            # Install web demo dependencies only
            INSTALL_WEB=true
            print_header "Avatar Engine - Web Demo Setup"
            install_uv
            install_python_deps
            install_web_demo
            print_header "Web demo setup complete!"
            echo "Start the demo:"
            echo "  ./scripts/start-web.sh"
            ;;
        --all)
            # Non-interactive: install everything
            INSTALL_GEMINI=true
            INSTALL_CLAUDE=true
            INSTALL_CODEX=true
            INSTALL_WEB=true

            print_header "Avatar Engine - Full Installation"
            check_dependencies
            install_uv
            install_python_deps
            install_cli_tools
            install_web_demo
            create_activate_script

            print_header "Installation complete!"
            echo "All providers installed: Gemini, Claude, Codex"
            echo "Web demo installed: examples/web-demo"
            ;;
        --help|-h)
            echo "Avatar Engine - Install Script"
            echo ""
            echo "Usage:"
            echo "  ./install.sh              Full installation (interactive provider selection)"
            echo "  ./install.sh --check      Check all dependencies"
            echo "  ./install.sh --setup-cli  Install AI agent CLIs (interactive)"
            echo "  ./install.sh --web        Install web demo dependencies"
            echo "  ./install.sh --all        Install everything without prompts"
            echo "  ./install.sh --help       Show this help"
            echo ""
            echo "Supported AI Agents:"
            echo "  1) Gemini CLI   — Google Gemini     (npm: @google/gemini-cli)"
            echo "  2) Claude Code  — Anthropic Claude  (npm: @anthropic-ai/claude-code)"
            echo "  3) Codex CLI    — OpenAI Codex      (npm: @openai/codex + @zed-industries/codex-acp)"
            ;;
        *)
            print_header "Avatar Engine - Installation"

            # 1. Check dependencies
            check_dependencies

            # 2. Select providers
            select_providers

            # 3. Install uv
            install_uv

            # 4. Python dependencies
            install_python_deps

            # 5. CLI tools (based on selection)
            install_cli_tools

            # 6. Web demo (optional)
            echo ""
            read -p "Install Web Demo (React UI for Avatar Engine)? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                INSTALL_WEB=true
                install_web_demo
            fi

            # 7. Activation scripts
            create_activate_script

            # 8. Done
            print_header "Installation complete!"
            echo "Detected shell: ${PARENT_SHELL}"
            echo ""

            # Show what was installed
            echo "Installed providers:"
            if $INSTALL_GEMINI; then echo "  - Gemini CLI"; fi
            if $INSTALL_CLAUDE; then echo "  - Claude Code"; fi
            if $INSTALL_CODEX; then echo "  - Codex CLI (codex-acp)"; fi
            if ! $INSTALL_GEMINI && ! $INSTALL_CLAUDE && ! $INSTALL_CODEX; then
                echo "  (none — install later with ./install.sh --setup-cli)"
            fi
            echo ""

            echo "Next steps:"
            echo ""
            echo "1. Activate the environment:"
            if [ "$PARENT_SHELL" = "fish" ]; then
                echo "   source activate.fish"
            else
                echo "   source activate.sh"
            fi
            echo ""
            echo "2. Edit configuration:"
            echo "   nano .avatar.yaml"
            echo ""
            echo "3. Sign in to your provider(s):"
            if $INSTALL_GEMINI; then
                echo "   gemini           # Google account"
            fi
            if $INSTALL_CLAUDE; then
                echo "   claude           # Anthropic account (Pro/Max)"
            fi
            if $INSTALL_CODEX; then
                echo "   codex login      # ChatGPT account (Plus/Pro)"
            fi
            echo ""
            echo "4. Run an example:"
            echo "   uv run avatar repl"
            echo ""
            if $INSTALL_WEB; then
                echo "5. Start the Web Demo:"
                echo "   ./scripts/start-web.sh"
                echo ""
            fi
            ;;
    esac
}

main "$@"
