# Docker Development

Setup ini menjalankan backend Linux, PostgreSQL, dan frontend Nginx. Tidak ada
seed script atau data sintetis yang dijalankan saat startup.

## Prerequisites

Install and start Docker Desktop, then open a new PowerShell window so the
`docker` command is available.

## Start

Create a Docker-only environment file without replacing the existing `.env`:

```powershell
Copy-Item .env.example .env.docker
```

Edit `.env.docker` and replace `change-this-local-password` with a local
development password. Then build and start all services:

```powershell
docker compose --env-file .env.docker up --build
```

Open `http://localhost:5173`. The API is also available at
`http://localhost:8000`; its health endpoint is `/api/health`.

The backend connects to Ollama on the Windows host through
`host.docker.internal:11434`. Change `OLLAMA_BASE_URL` in `.env.docker` if
Ollama runs elsewhere.

## Stop

```powershell
docker compose --env-file .env.docker down
```

PostgreSQL, LanceDB, and the Hugging Face model cache persist in Docker
volumes. To delete those volumes and start with an empty database again:

```powershell
docker compose --env-file .env.docker down -v
```

The trained model files are mounted read-only from `backend/models_trained`.
