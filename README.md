# ADAM

*A.D.A.M. — Administrative Directive & Archival Memory.*

ADAM is a platform for turning approved Uttarakhand public records into a connected, queryable knowledge base — not a single assistant, but the infrastructure behind one. Connect your data and ADAM's ingestion pipelines take care of getting it into the database; choose which models power your workspace, local or API-based; and bring your organization on board with shared access for its members. ADAM runs local-first by default, with the option to connect hosted model APIs where that fits your deployment. Under the hood: a FastAPI backend, a Next.js web interface, PostgreSQL/pgvector persistence, document ingestion, OCR support, and local or API-based model and voice services.

## Quick start with Docker

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- 8 GB RAM minimum; 16 GB is recommended when running local models.
- Optional: [Ollama](https://ollama.com/) for natural local-model answers.

Clone the repository and start the editable development stack:

```bash
git clone <YOUR-REPOSITORY-URL> adam
cd adam
docker compose up --build
```

Open:

- UI: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API health check: <http://localhost:8000/api/health>

The first build downloads the Python, Node, Postgres, OCR, and voice dependencies. Subsequent starts use Docker cache and named volumes.

Stop the stack with `Ctrl+C`, then run:

```bash
docker compose down
```

This keeps the Postgres and application-storage volumes. To intentionally remove all local Compose data, run `docker compose down --volumes`; this deletes your local database and uploaded documents.

## Development workflow

The default `docker-compose.yml` is development-oriented:

- `./adam` and `./tests` are mounted into the API container; Uvicorn reloads Python changes.
- `./ui` is mounted into the UI container; Next.js hot reloads UI changes.
- Dependencies live in Docker images/named volumes, not in the checked-out source tree.
- PostgreSQL and document storage persist in named Docker volumes.

Useful commands:

```bash
make docker-up       # Start and build the stack
make docker-down     # Stop it, preserving local data volumes
make docker-logs     # Follow API and UI logs
make docker-build    # Rebuild images without cache
make docker-test     # Run backend tests inside the API image
docker compose ps    # Inspect container health
```

To run the production image configuration locally:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

Production images do not mount application source code or the UI `node_modules` folder.

## Configuration

Copy the template only when you need to override defaults:

```bash
cp .env.example .env
```

`.env` is intentionally ignored by Git. Do not put credentials, access tokens, signing keys, model paths, or real connection strings in tracked files.

| Variable | Purpose | Development default |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose Postgres configuration | `adam`, `adam`, `adam_dev_password` |
| `DATABASE_URL` | Native API database URL | Compose provides a container URL |
| `STORAGE_DIR` | Uploaded documents and processing artifacts | `/app/.adam_storage` in Docker |
| `SIGNING_SECRET` | Manifest/audit signing secret | Development-only placeholder |
| `ADAM_PROFILE` | Resource profile | `DEV_SERVER` |
| `ADAM_MODEL_BACKEND` | Model runtime | `ollama` |
| `OLLAMA_HOST` | Ollama-compatible endpoint | `http://host.docker.internal:11434` |
| `API_PORT`, `UI_PORT`, `POSTGRES_PORT` | Host port overrides | `8000`, `3000`, `5432` |

On Linux, `host.docker.internal` may not resolve to a host Ollama installation. Compose includes a host-gateway mapping on modern Docker versions; otherwise set `OLLAMA_HOST` in `.env` to your reachable Ollama address.

## Local models and large assets

Model weights, datasets, uploads, caches, and local databases are deliberately excluded from Git. They are covered by `.gitignore` and `.dockerignore`.

ADAM defaults to local models so a workspace can run fully offline, but model selection is meant to be a choice, not a constraint — a workspace can point at a hosted API-based model instead of, or alongside, a local one, depending on what that deployment needs.

For the default local chat model:

```bash
ollama pull qwen2.5:3b
```

With Docker running, ADAM will reach a host Ollama service through `OLLAMA_HOST`. The model selector only enables models that are actually installed. Never commit model files (`*.gguf`, `*.safetensors`, `*.onnx`, etc.); distribute them through Ollama, an artifact registry, or a separately mounted volume.

Fast Whisper is included in the API Docker image. On first transcription it may download its configured Whisper model into the container cache. For production, mount a managed cache/model volume and document its provenance instead of adding it to Git.

## Native development (without Docker)

Requires Python 3.10+ and Node.js 20+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,voice]"
cd ui && npm ci && cd ..
adam serve --reload
```

In a second terminal:

```bash
cd ui
npm run dev
```

Run checks:

```bash
python3 -m pytest -q
cd ui && npm run build
```

## Troubleshooting

**Port already in use** — stop the process using port 3000, 8000, or 5432, or override `UI_PORT`, `API_PORT`, or `POSTGRES_PORT` in `.env`.

**UI cannot reach the API** — run `docker compose ps`, then visit <http://localhost:8000/api/health>. In Docker, the UI proxies `/api/*` to the `api` service; do not point browser code at the internal hostname.

**Model remains disabled** — run `ollama list`, pull the exact requested tag, and wait up to 15 seconds for the UI model inventory refresh. Confirm `OLLAMA_HOST` is reachable from the API container.

**Voice input reports unavailable** — inspect `docker compose logs api`. The API requires Fast Whisper and FFmpeg; rebuild with `docker compose build --no-cache api` if an earlier image predates this setup.

**Database reset needed** — use `docker compose down --volumes` only when you intentionally want to delete all local Postgres and application storage data.

## Git hygiene

Only source code, documentation, manifests, Docker configuration, and safe templates belong in Git. Before committing, review:

```bash
git status --ignored
git check-ignore -v .env adam.db .adam_storage/example-file
```

Keep `.env.example` current, but never commit a real `.env`, downloaded model, local database, upload, generated artifact, virtual environment, or IDE workspace file.