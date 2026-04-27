#!/bin/bash
# Script to update all requirements files

echo "🔄 Updating dependencies with UV..."

# Update the lockfile
echo "📦 Updating lockfile..."
uv lock --upgrade

# Regenerate local runtime requirements.txt
echo "📝 Generating requirements.txt..."
uv pip compile pyproject.toml --extra local -o requirements/requirements.txt

# Regenerate requirements-dev.txt
echo "🛠️ Generating requirements-dev.txt..."
uv pip compile pyproject.toml --extra local --extra dev -o requirements/requirements-dev.txt

echo "✅ Requirements files updated!"
echo ""
echo "📋 Generated files:"
echo "  - requirements/requirements.txt (production)"
echo "  - requirements/requirements-dev.txt (development)"
echo "  - uv.lock (lockfile)"
