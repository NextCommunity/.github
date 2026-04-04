# NextCommunity Leaderboard Backend

A dynamic Python API that serves the [NextCommunity](https://github.com/NextCommunity) organization leaderboard with gamified levels, achievements, points, and streaks.

## Features

- **Real-time leaderboard API** — JSON endpoints for contributor rankings
- **Contributor profiles** — individual stats with level, achievements, streak, points
- **Aggregate statistics** — org-wide metrics and rarity distribution
- **Level & achievement catalogs** — complete gamification reference data
- **Automatic caching** — TTL-based in-memory cache to respect GitHub API rate limits
- **API key protection** — optional authentication for write endpoints
- **Cloud-ready** — configurations for Railway, Render, Fly.io, AWS Lambda, Google Cloud Run, and self-hosted

## Quick Start

### Prerequisites

- Python 3.13+
- A [GitHub personal access token](https://github.com/settings/tokens) (recommended for higher API rate limits)

### Local Development

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Set environment variables
export GITHUB_TOKEN="ghp_your_token_here"
export ORG_NAME="NextCommunity"

# Run the server
cd ..  # back to repo root
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs are at `http://localhost:8000/docs`.

### Docker

```bash
# Build and run
docker compose -f backend/docker-compose.yml up --build

# Or build manually
docker build -f backend/Dockerfile -t nextcommunity-api .
docker run -p 8000:8000 -e GITHUB_TOKEN=ghp_... nextcommunity-api
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/leaderboard` | Full leaderboard with all contributors |
| `GET` | `/api/contributors/{login}` | Individual contributor profile |
| `GET` | `/api/stats` | Aggregate org-wide statistics |
| `GET` | `/api/levels` | All level definitions |
| `GET` | `/api/achievements` | Achievement catalog |
| `POST` | `/api/refresh` | Force cache refresh (API key required when configured) |

Full OpenAPI documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | *(empty)* | GitHub personal access token |
| `ORG_NAME` | `NextCommunity` | GitHub organization name |
| `CACHE_TTL` | `900` | Cache time-to-live in seconds (15 min) |
| `API_KEY` | *(empty)* | API key for protected endpoints (empty = open) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `info` | Logging level |
| `LEVELS_JSON_URL` | *(canonical URL)* | URL for level definitions JSON |

## Cloud Deployment

Pre-built configurations are provided in the `deploy/` directory:

### Railway (Recommended)

1. Connect your GitHub repo to [Railway](https://railway.app)
2. Set environment variables in the Railway dashboard
3. Railway auto-detects the `deploy/railway.toml` configuration

### Render

1. Create a new Web Service on [Render](https://render.com)
2. Use the `deploy/render.yaml` blueprint or configure manually
3. Set environment variables in the Render dashboard

### Fly.io

```bash
fly launch --config backend/deploy/fly.toml
fly secrets set GITHUB_TOKEN=ghp_...
fly deploy
```

### AWS Lambda (Serverless)

1. Install [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
2. Uncomment `mangum` in `requirements.txt`
3. Deploy:

```bash
cd backend/deploy
sam build --template template.yaml
sam deploy --guided
```

### Google Cloud Run

```bash
gcloud builds submit --config backend/deploy/cloudbuild.yaml .
```

### Self-hosted (VPS)

1. Copy the repository to your server
2. Set up the systemd service: `sudo cp backend/deploy/leaderboard-api.service /etc/systemd/system/`
3. Configure Nginx: `sudo cp backend/deploy/nginx.conf /etc/nginx/sites-available/leaderboard`
4. Create a `.env` file and enable the service:

```bash
sudo systemctl enable --now leaderboard-api
sudo systemctl reload nginx
```

## Testing

```bash
# Run all tests
python -m pytest backend/tests/ -v

# Run specific test file
python -m pytest backend/tests/test_leaderboard.py -v
python -m pytest backend/tests/test_api.py -v
```

## Architecture

```
backend/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Environment-based settings
│   ├── routers/
│   │   ├── leaderboard.py   # GET /api/leaderboard, POST /api/refresh
│   │   ├── contributors.py  # GET /api/contributors/{login}
│   │   └── stats.py         # GET /api/stats, /api/levels, /api/achievements
│   ├── services/
│   │   ├── github_client.py # Async GitHub API client (httpx)
│   │   ├── leaderboard.py   # Core leaderboard aggregation logic
│   │   ├── levels.py        # Level computation, rarity, progress bars
│   │   ├── achievements.py  # Achievement definitions and evaluation
│   │   └── cache.py         # TTL-based in-memory cache
│   └── models/
│       ├── contributor.py   # Pydantic models for contributor data
│       └── leaderboard.py   # Response schemas
├── deploy/                  # Cloud hosting configurations
├── tests/                   # Unit and integration tests
├── requirements.txt         # Python dependencies
├── Dockerfile               # Multi-stage container build
└── docker-compose.yml       # Local development setup
```

## Relationship to the Leaderboard Script

The existing `scripts/leaderboard.py` continues to run as a GitHub Action to update the static `profile/README.md`. This backend provides the same data through a dynamic API. Both systems share the same gamification logic and level definitions.
