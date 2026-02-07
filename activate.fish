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
set -l provider (grep '^provider:' config.yaml 2>/dev/null | awk '{print $2}')
if test -n "$provider"
    echo "  Provider from config.yaml: $provider"
end
echo ""
echo "Run examples:"
echo "  python examples.py basic"
echo "  python examples.py --help"
