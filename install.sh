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
    if command -v codex-acp &> /dev/null || (command -v npx &> /dev/null && timeout 5 npx --yes @zed-industries/codex-acp --help &> /dev/null); then
        codex_status=" ${DIM}(already installed)${NC}"
    fi

    echo -e "  ${BOLD}1)${NC} ${CYAN}Gemini CLI${NC}  — Google Gemini (free tier available)${gemini_status}"
    echo -e "     ${DIM}npm install -g @google/gemini-cli${NC}"
    echo ""
    echo -e "  ${BOLD}2)${NC} ${CYAN}Claude Code${NC} — Anthropic Claude (API key required)${claude_status}"
    echo -e "     ${DIM}npm install -g @anthropic-ai/claude-code${NC}"
    echo ""
    echo -e "  ${BOLD}3)${NC} ${CYAN}Codex CLI${NC}   — OpenAI Codex via ACP (API key required)${codex_status}"
    echo -e "     ${DIM}npx @zed-industries/codex-acp${NC}"
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
        print_ok "$1 found: $(which $1)"
        return 0
    else
        print_warn "$1 not found"
        return 1
    fi
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
        echo "    Install: npm install -g @google/gemini-cli"
    fi

    # Claude Code
    if check_command claude; then
        echo "    Version: $(claude --version 2>/dev/null || echo 'N/A')"
    else
        print_warn "Claude Code is not installed"
        echo "    Install: npm install -g @anthropic-ai/claude-code"
    fi

    # Codex CLI (codex-acp)
    if command -v codex-acp &> /dev/null; then
        print_ok "codex-acp found: $(which codex-acp)"
    elif command -v npx &> /dev/null; then
        # Check if codex-acp is cached via npx
        if timeout 5 npx --yes @zed-industries/codex-acp --help &> /dev/null; then
            print_ok "codex-acp found (via npx)"
        else
            print_warn "codex-acp is not installed"
            echo "    Install: npx @zed-industries/codex-acp (auto-fetched on first use)"
        fi
    else
        print_warn "codex-acp requires npx (Node.js)"
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

    # Check npm for Gemini/Claude (they need global npm install)
    if ($INSTALL_GEMINI || $INSTALL_CLAUDE) && ! command -v npm &> /dev/null; then
        print_error "npm is not installed!"
        echo "Install Node.js: sudo pacman -S nodejs npm"
        exit 1
    fi

    # Check npx for Codex
    if $INSTALL_CODEX && ! command -v npx &> /dev/null; then
        print_error "npx is not installed!"
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
            npm install -g @google/gemini-cli
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
            npm install -g @anthropic-ai/claude-code
            print_ok "Claude Code installed"
        fi
    fi

    # --- Codex CLI (codex-acp) ---
    if $INSTALL_CODEX; then
        echo -e "\n${YELLOW}Codex CLI (codex-acp):${NC}"
        echo "Codex uses npx to auto-fetch @zed-industries/codex-acp on first use."
        echo "Pre-fetching package to cache..."
        if timeout 15 npx --yes @zed-industries/codex-acp --help &> /dev/null; then
            print_ok "codex-acp cached via npx"
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
        echo "  gemini           # Run once to authenticate with Google"
    fi
    if $INSTALL_CLAUDE; then
        echo "  claude           # Run once to authenticate with Anthropic"
    fi
    if $INSTALL_CODEX; then
        echo "  codex login      # For ChatGPT auth, or set OPENAI_API_KEY / CODEX_API_KEY"
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

    # Activate venv
    source .venv/bin/activate

    # Core dependencies
    echo "Installing core dependencies..."
    uv pip install pyyaml

    # ACP SDK (needed for Gemini ACP and Codex ACP)
    if $INSTALL_GEMINI || $INSTALL_CODEX; then
        echo "Installing ACP SDK (for Gemini/Codex warm sessions)..."
        uv pip install agent-client-protocol || print_warn "ACP SDK installation failed (warm sessions will be unavailable)"
    fi

    # MCP SDK (optional, useful for all providers)
    echo "Installing MCP SDK..."
    uv pip install mcp || print_warn "MCP SDK installation failed (optional)"

    # Development tools (optional)
    read -p "Install development tools (pytest, pytest-asyncio, ruff, mypy)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        uv pip install pytest pytest-asyncio ruff mypy
    fi

    print_ok "Python dependencies installed"
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
echo "Run examples:"
echo "  python examples.py basic"
echo "  python examples.py --help"
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
echo "Run examples:"
echo "  python examples.py basic"
echo "  python examples.py --help"
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
        --all)
            # Non-interactive: install everything
            INSTALL_GEMINI=true
            INSTALL_CLAUDE=true
            INSTALL_CODEX=true

            print_header "Avatar Engine - Full Installation"
            check_dependencies
            install_uv
            install_python_deps
            install_cli_tools
            create_activate_script

            print_header "Installation complete!"
            echo "All providers installed: Gemini, Claude, Codex"
            ;;
        --help|-h)
            echo "Avatar Engine - Install Script"
            echo ""
            echo "Usage:"
            echo "  ./install.sh              Full installation (interactive provider selection)"
            echo "  ./install.sh --check      Check all dependencies"
            echo "  ./install.sh --setup-cli  Install AI agent CLIs (interactive)"
            echo "  ./install.sh --all        Install everything without prompts"
            echo "  ./install.sh --help       Show this help"
            echo ""
            echo "Supported AI Agents:"
            echo "  1) Gemini CLI   — Google Gemini     (npm: @google/gemini-cli)"
            echo "  2) Claude Code  — Anthropic Claude  (npm: @anthropic-ai/claude-code)"
            echo "  3) Codex CLI    — OpenAI Codex      (npx: @zed-industries/codex-acp)"
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

            # 6. Activation scripts
            create_activate_script

            # 7. Done
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
                echo "   claude           # Anthropic account"
            fi
            if $INSTALL_CODEX; then
                echo "   codex login      # ChatGPT auth, or set OPENAI_API_KEY"
            fi
            echo ""
            echo "4. Run an example:"
            echo "   python examples.py basic"
            echo ""
            ;;
    esac
}

main "$@"
