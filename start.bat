@echo off
echo Starting J-ARI Backend...
start cmd /k "cd /d C:\Users\Radith\E-Jak && venv\Scripts\activate && uvicorn backend.app.api.main:app --reload --port 8000"

echo Starting J-ARI Frontend...
start cmd /k "cd /d C:\Users\Radith\E-Jak\frontend && npm run dev"

echo J-ARI System started!
