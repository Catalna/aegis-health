@echo off
echo Starting J-ARI Backend...
start cmd /k "cd /d C:\Users\Radith\E-Jak && venv\Scripts\activate && python -m uvicorn backend.app.api.main:app --reload --port 8000 --loop backend.app.core.windows_loop:selector_event_loop"

echo Starting J-ARI Frontend...
start cmd /k "cd /d C:\Users\Radith\E-Jak\frontend && npm run dev"

echo J-ARI System started!
