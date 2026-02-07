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
