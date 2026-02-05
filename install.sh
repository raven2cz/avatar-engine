#!/bin/bash
# ============================================================================
# Avatar Engine - Install Script for Arch Linux
# ============================================================================
#
# Instaluje závislosti pomocí uv package manager.
# Podporuje Gemini CLI a Claude Code.
#
# Použití:
#   ./install.sh              # Instalace
#   ./install.sh --check      # Kontrola závislostí
#   ./install.sh --setup-cli  # Instalace Gemini CLI a Claude Code
#
# ============================================================================

set -e

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
# Kontrola závislostí
# ============================================================================

check_command() {
    if command -v "$1" &> /dev/null; then
        print_ok "$1 nalezen: $(which $1)"
        return 0
    else
        print_warn "$1 nenalezen"
        return 1
    fi
}

check_dependencies() {
    print_header "Kontrola závislostí"
    
    local all_ok=true
    
    # Python
    if check_command python3; then
        echo "    Verze: $(python3 --version)"
    else
        all_ok=false
    fi
    
    # uv
    if check_command uv; then
        echo "    Verze: $(uv --version)"
    else
        all_ok=false
    fi
    
    # Node.js (pro CLI)
    if check_command node; then
        echo "    Verze: $(node --version)"
    else
        print_warn "Node.js potřebný pro Gemini CLI a Claude Code"
    fi
    
    # npm
    if check_command npm; then
        echo "    Verze: $(npm --version)"
    else
        print_warn "npm potřebný pro Gemini CLI a Claude Code"
    fi
    
    # Gemini CLI
    echo ""
    if check_command gemini; then
        echo "    Verze: $(gemini --version 2>/dev/null || echo 'N/A')"
    else
        print_warn "Gemini CLI není nainstalován"
        echo "    Instaluj: npm install -g @google/gemini-cli"
    fi
    
    # Claude Code
    if check_command claude; then
        echo "    Verze: $(claude --version 2>/dev/null || echo 'N/A')"
    else
        print_warn "Claude Code není nainstalován"
        echo "    Instaluj: npm install -g @anthropic-ai/claude-code"
    fi
    
    echo ""
    if $all_ok; then
        print_ok "Všechny základní závislosti jsou splněny"
    else
        print_error "Některé závislosti chybí"
    fi
}

# ============================================================================
# Instalace uv
# ============================================================================

install_uv() {
    if command -v uv &> /dev/null; then
        print_ok "uv je již nainstalován"
        return 0
    fi
    
    print_header "Instalace uv"
    
    # Zkus pacman
    if command -v pacman &> /dev/null; then
        echo "Zkouším pacman..."
        if pacman -Ss "^python-uv$" &> /dev/null; then
            sudo pacman -S --noconfirm python-uv
            print_ok "uv nainstalován přes pacman"
            return 0
        fi
    fi
    
    # Zkus AUR helper
    for helper in yay paru; do
        if command -v $helper &> /dev/null; then
            echo "Zkouším $helper..."
            $helper -S --noconfirm python-uv 2>/dev/null && {
                print_ok "uv nainstalován přes $helper"
                return 0
            }
        fi
    done
    
    # Fallback: oficiální instalátor
    echo "Instaluji přes oficiální skript..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Přidej do PATH
    export PATH="$HOME/.local/bin:$PATH"
    
    if command -v uv &> /dev/null; then
        print_ok "uv nainstalován"
    else
        print_error "Instalace uv selhala"
        exit 1
    fi
}

# ============================================================================
# Instalace CLI nástrojů
# ============================================================================

install_cli_tools() {
    print_header "Instalace AI CLI nástrojů"
    
    if ! command -v npm &> /dev/null; then
        print_error "npm není nainstalován!"
        echo "Instaluj Node.js: sudo pacman -S nodejs npm"
        exit 1
    fi
    
    # Gemini CLI
    echo -e "\n${YELLOW}Gemini CLI:${NC}"
    if command -v gemini &> /dev/null; then
        print_ok "Již nainstalován"
    else
        echo "Instaluji @google/gemini-cli..."
        npm install -g @google/gemini-cli
        print_ok "Gemini CLI nainstalován"
    fi
    
    # Claude Code
    echo -e "\n${YELLOW}Claude Code:${NC}"
    if command -v claude &> /dev/null; then
        print_ok "Již nainstalován"
    else
        echo "Instaluji @anthropic-ai/claude-code..."
        npm install -g @anthropic-ai/claude-code
        print_ok "Claude Code nainstalován"
    fi
    
    echo ""
    print_ok "CLI nástroje nainstalovány"
    echo ""
    echo "Pro přihlášení spusť:"
    echo "  gemini auth login    # Pro Gemini CLI"
    echo "  claude auth login    # Pro Claude Code"
}

# ============================================================================
# Instalace Python závislostí
# ============================================================================

install_python_deps() {
    print_header "Instalace Python závislostí"
    
    # Vytvoř venv pokud neexistuje
    if [ ! -d ".venv" ]; then
        echo "Vytvářím virtuální prostředí..."
        uv venv
    fi
    
    # Aktivuj venv
    source .venv/bin/activate
    
    # Instaluj závislosti
    echo "Instaluji závislosti..."
    uv pip install pyyaml
    uv pip install agent-client-protocol || print_warn "ACP SDK se nepodařilo nainstalovat (Gemini ACP warm session nebude dostupný)"
    
    # MCP SDK (volitelné)
    echo "Instaluji MCP SDK..."
    uv pip install mcp || print_warn "MCP SDK se nepodařilo nainstalovat (volitelné)"
    
    # Vývojové nástroje (volitelné)
    read -p "Instalovat vývojové nástroje (pytest, black, mypy)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        uv pip install pytest black mypy
    fi
    
    print_ok "Python závislosti nainstalovány"
}

# ============================================================================
# Vytvoření aktivačního skriptu
# ============================================================================

create_activate_script() {
    print_header "Vytváření aktivačního skriptu"
    
    cat > activate.sh << 'EOF'
#!/bin/bash
# Avatar Engine - Aktivační skript
# Použití: source activate.sh

# Aktivuj virtuální prostředí
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "✓ Virtuální prostředí aktivováno"
else
    echo "✗ Virtuální prostředí nenalezeno, spusť ./install.sh"
    return 1
fi

# Nastav PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Info
echo ""
echo "Avatar Engine připraven!"
echo "  Provider z config.yaml: $(grep '^provider:' config.yaml 2>/dev/null | awk '{print $2}')"
echo ""
echo "Spusť příklady:"
echo "  python examples.py basic"
echo "  python examples.py --help"
EOF

    chmod +x activate.sh
    print_ok "Vytvořen activate.sh"
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
            echo "Použití:"
            echo "  ./install.sh              Kompletní instalace"
            echo "  ./install.sh --check      Kontrola závislostí"
            echo "  ./install.sh --setup-cli  Instalace Gemini CLI a Claude Code"
            echo "  ./install.sh --help       Tato nápověda"
            ;;
        *)
            print_header "Avatar Engine - Instalace"
            
            # 1. Kontrola
            check_dependencies
            
            # 2. Instalace uv
            install_uv
            
            # 3. Python závislosti
            install_python_deps
            
            # 4. Aktivační skript
            create_activate_script
            
            # 5. Hotovo
            print_header "Instalace dokončena!"
            echo "Další kroky:"
            echo ""
            echo "1. Aktivuj prostředí:"
            echo "   source activate.sh"
            echo ""
            echo "2. Uprav konfiguraci:"
            echo "   nano config.yaml"
            echo ""
            echo "3. Přihlaš se do CLI (pokud ještě ne):"
            echo "   gemini auth login    # Pro Gemini"
            echo "   claude auth login    # Pro Claude"
            echo ""
            echo "4. Spusť příklad:"
            echo "   python examples.py basic"
            echo ""
            ;;
    esac
}

main "$@"
