#!/usr/bin/env bash
set -e

echo "═══ ADJUTANT INSTALLER ═══"
echo ""

# Check Python version
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.12+ first."
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    echo "ERROR: Python 3.12+ required (found $PY_VER)"
    exit 1
fi

echo "[1/4] Python $PY_VER detected"

# Create venv if not exists
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[2/4] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "[2/4] Virtual environment exists"
fi

# Install package
echo "[3/5] Installing Adjutant and dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$SCRIPT_DIR"

# Optional: local embeddings (for RAG/memory without Ollama)
echo "[4/5] Local embeddings (sentence-transformers)..."
read -p "  Install local embedding models? (skip if using Ollama) [y/N] " INSTALL_EMB
if [[ "$INSTALL_EMB" =~ ^[Yy]$ ]]; then
    "$VENV_DIR/bin/pip" install --quiet -e "$SCRIPT_DIR[local-embeddings]"
    echo "  Local embeddings installed"
else
    echo "  Skipped (install later: pip install -e '.[local-embeddings]')"
fi

# Run init if not configured
echo "[5/5] Checking configuration..."
if [ ! -f "$HOME/.adjutant/config.toml" ]; then
    echo ""
    echo "First time setup — running 'adjutant init'..."
    "$VENV_DIR/bin/adjutant" init
else
    echo "Configuration found at ~/.adjutant/config.toml"
fi

echo ""
echo "═══ INSTALLATION COMPLETE ═══"
echo ""
echo "Activate the environment:"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "Quick start:"
echo "  adjutant              # Interactive chat"
echo "  adjutant web          # Web UI at http://127.0.0.1:8100"
echo "  adjutant bot          # Telegram bot (standalone)"
echo "  adjutant triage       # Run inbox triage SOP"
echo ""
echo "RAG & Memory (requires Ollama or local-embeddings):"
echo "  adjutant index build  # Build semantic search index"
echo "  adjutant index search # Search your notes"
echo "  adjutant memory add   # Add to vector memory"
echo ""
echo "MCP Server (for Claude Code / Cursor):"
echo "  adjutant mcp          # Start MCP server (stdio)"
echo ""
echo "Or run directly without activating:"
echo "  $VENV_DIR/bin/adjutant web"
echo ""
