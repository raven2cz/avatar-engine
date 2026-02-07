#!/bin/bash
# ============================================================================
# Avatar Engine - Install Script for Arch Linux
# ============================================================================
#
# Installs dependencies using the uv package manager.
# Supports Gemini CLI and Claude Code.
#
# Usage:
#   ./install.sh              # Full installation
#   ./install.sh --check      # Check dependencies
#   ./install.sh --setup-cli  # Install Gemini CLI and Claude Code
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
NC='\033[0m'

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
        print_warn "Node.js is required for Gemini CLI and Claude Code"
    fi

    # npm
    if check_command npm; then
        echo "    Version: $(npm --version)"
    else
        print_warn "npm is required for Gemini CLI and Claude Code"
    fi

    # Gemini CLI
    echo ""
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
# Install CLI tools
# ============================================================================

install_cli_tools() {
    print_header "Installing AI CLI tools"

    if ! command -v npm &> /dev/null; then
        print_error "npm is not installed!"
        echo "Install Node.js: sudo pacman -S nodejs npm"
        exit 1
    fi

    # Gemini CLI
    echo -e "\n${YELLOW}Gemini CLI:${NC}"
    if command -v gemini &> /dev/null; then
        print_ok "Already installed"
    else
        echo "Installing @google/gemini-cli..."
        npm install -g @google/gemini-cli
        print_ok "Gemini CLI installed"
    fi

    # Claude Code
    echo -e "\n${YELLOW}Claude Code:${NC}"
    if command -v claude &> /dev/null; then
        print_ok "Already installed"
    else
        echo "Installing @anthropic-ai/claude-code..."
        npm install -g @anthropic-ai/claude-code
        print_ok "Claude Code installed"
    fi

    echo ""
    print_ok "CLI tools installed"
    echo ""
    echo "To sign in, run:"
    echo "  gemini auth login    # For Gemini CLI"
    echo "  claude auth login    # For Claude Code"
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

    # Install dependencies
    echo "Installing dependencies..."
    uv pip install pyyaml
    uv pip install agent-client-protocol || print_warn "ACP SDK installation failed (Gemini ACP warm session will be unavailable)"

    # MCP SDK (optional)
    echo "Installing MCP SDK..."
    uv pip install mcp || print_warn "MCP SDK installation failed (optional)"

    # Development tools (optional)
    read -p "Install development tools (pytest, black, mypy)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        uv pip install pytest black mypy
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
            install_cli_tools
            ;;
        --help|-h)
            echo "Avatar Engine - Install Script"
            echo ""
            echo "Usage:"
            echo "  ./install.sh              Full installation"
            echo "  ./install.sh --check      Check dependencies"
            echo "  ./install.sh --setup-cli  Install Gemini CLI and Claude Code"
            echo "  ./install.sh --help       Show this help"
            ;;
        *)
            print_header "Avatar Engine - Installation"

            # 1. Check dependencies
            check_dependencies

            # 2. Install uv
            install_uv

            # 3. Python dependencies
            install_python_deps

            # 4. Activation scripts
            create_activate_script

            # 5. Done
            print_header "Installation complete!"
            echo "Detected shell: ${PARENT_SHELL}"
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
            echo "3. Sign in to CLI (if not already):"
            echo "   gemini auth login    # For Gemini"
            echo "   claude auth login    # For Claude"
            echo ""
            echo "4. Run an example:"
            echo "   python examples.py basic"
            echo ""
            ;;
    esac
}

main "$@"
