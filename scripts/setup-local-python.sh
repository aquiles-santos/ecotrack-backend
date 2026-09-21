#!/usr/bin/env bash
# Instala Python 3.12 no Ubuntu/WSL via deadsnakes (requer sudo).
# Alternativa sem sudo: use apenas Docker (make up / make lint).

set -euo pipefail

if command -v python3.12 >/dev/null 2>&1; then
  echo "Python 3.12 já instalado: $(python3.12 --version)"
else
  echo "Instalando Python 3.12 (deadsnakes)..."
  sudo apt-get update
  sudo apt-get install -y software-properties-common
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt-get update
  sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
fi

cd "$(dirname "$0")/.."
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

echo ""
echo "Ambiente local pronto. Ative com: source .venv/bin/activate"
echo "Valide com: python -c \"from app.main import app\" && ruff check app"
