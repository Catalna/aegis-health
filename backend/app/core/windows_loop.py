"""Factory event loop untuk uvicorn di Windows.

ProactorEventLoop bawaan Python 3.10 pada Windows dapat berhenti menerima
koneksi setelah klien disconnect kasar (WinError 64 pada accept coroutine),
sehingga proses server tetap hidup tetapi listener mati (zombie server).
SelectorEventLoop tidak memiliki cacat tersebut dan bekap penuh kebutuhan
FastAPI/SSE/asyncpg pada skala pengembangan proyek ini.

Dipakai dengan (kontrak uvicorn: nilai --loop dipanggil tanpa argumen):
    uvicorn ... --loop backend.app.core.windows_loop:selector_event_loop
"""
import asyncio


def selector_event_loop():
    """Buat instance SelectorEventLoop untuk uvicorn di Windows."""
    return asyncio.SelectorEventLoop()
