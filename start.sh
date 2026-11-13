#!/usr/bin/env bash
# One-command setup and start for macOS / Linux:  ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi
echo "Installing Python packages..."
.venv/bin/python -m pip install -q -r backend/requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "  Created .env -- open it and paste your ANTHROPIC_API_KEY to enable AI questions."
  echo
fi

if [ ! -f frontend/dist/index.html ]; then
  echo "Building the website..."
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

cd backend
OPEN_BROWSER=1 exec ../.venv/bin/python -m app
