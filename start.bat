@echo off
rem Portable launcher: works from any directory the repo is placed in.
setlocal
cd /d "%~dp0"

echo Starting J-ARI Backend...
start cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m uvicorn backend.app.api.main:app --reload --port 8000 --loop backend.app.core.windows_loop:selector_event_loop"

echo Starting J-ARI Frontend...
start cmd /k "cd /d %~dp0frontend && npm run dev"

echo J-ARI System started!
