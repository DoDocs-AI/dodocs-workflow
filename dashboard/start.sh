#!/usr/bin/env bash
# Start the AI Workspace OS Dashboard
# Backend (Python, port 7474) + Frontend (Vite, port 7475)
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting AI Workspace OS Dashboard..."
echo "  Backend:  http://localhost:7474"
echo "  Frontend: http://localhost:7475"
echo "  Data:     ~/.claude/workspace/registry.json"
echo ""

# Start backend in background
python3 "$DIR/server.py" &
BACKEND_PID=$!

# Start frontend
cd "$DIR/ui"
if [ ! -d node_modules ]; then
  echo "Installing frontend dependencies..."
  npm install
fi
npx vite &
FRONTEND_PID=$!

# Trap to clean up both processes
cleanup() {
  echo ""
  echo "Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
}
trap cleanup INT TERM

echo ""
echo "Dashboard running. Press Ctrl+C to stop."
wait
