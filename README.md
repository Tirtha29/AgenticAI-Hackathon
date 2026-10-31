# NetCoop AI

Streamlit network operations dashboard, Python FastAPI API and Redis Streams worker, Redis geospatial index, and a typed LangGraph workflow for network diagnostics.

## Run locally

Requirements: Python 3.11+ and Redis 6.2+ (Redis 7 recommended).

```bash
cd AgenticAI-Hackathon
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- `INTERNAL_TOKEN`: replace the placeholder with a random private value, e.g. `openssl rand -hex 32`.
- `REDIS_URL`: for local Redis use `redis://localhost:6379/0`.
- `OPENAI_API_KEY`: optional; only used for Pydantic-parsed report narrative.
- Other settings are optional and have working defaults in `.env.example`.

On macOS with Homebrew, install/start Redis:

```bash
brew install redis
brew services start redis
```

Open three terminals in the project directory and activate the venv in each:

```bash
# Terminal 1: FastAPI
source .venv/bin/activate
uvicorn backend.main:app --reload
```

```bash
# Terminal 2: Redis Streams worker
source .venv/bin/activate
python -m backend.worker
```

```bash
# Terminal 3: Streamlit dashboard
source .venv/bin/activate
streamlit run frontend/streamlit_app.py
```

Open the dashboard at <http://localhost:8501>, API docs at <http://localhost:8000/docs>, and agent/worker health at <http://localhost:8000/health>. Run tests with `python -m unittest discover -s tests -v`.

The dashboard includes an overview with device health counts, live status and hot-zone maps, recent telemetry charts, incident investigation/HITL, a searchable rule knowledge base, device inventory, analytics, settings, and agent execution health/latency. The sidebar can load 15 synthetic IIT Bhubaneswar campus-area devices; this replaces the current inventory, and the sample coordinates are illustrative rather than surveyed placements. The knowledge explorer is also available through `GET /knowledge/rules?q=latency&limit=20`.

### Docker Compose alternative

Docker Desktop must be running:

```bash
docker compose up --build
```

Compose starts Redis, the Python worker, FastAPI, and Streamlit. It supplies container-specific Redis/API addresses. When running processes directly on the host, use the local addresses in `.env`.

## `.env` reference

Copy `.env.example` to `.env`. Keep only these settings unless you need custom values:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
INTERNAL_TOKEN=replace-with-a-random-secret
REDIS_URL=redis://localhost:6379/0
BACKEND_URL=http://localhost:8000
DATABASE_PATH=./data/netcoop.db
BLAST_RADIUS_KM=5
TELEMETRY_STREAM=netcoop:telemetry
TELEMETRY_CONSUMER_GROUP=netcoop-workers
WORKER_MAX_DELIVERIES=5
```

Never commit a real API key or `INTERNAL_TOKEN`. `OPENAI_API_KEY` is optional; the agents and static rules run without it.

## Device inventory and telemetry

Upload a CSV or GeoJSON device map before telemetry to populate Redis GEOSEARCH. CSV columns: `device_id,latitude,longitude`, and optional `name,device_type,vendor,neighbors`; `neighbors` accepts semicolon-separated IDs. GeoJSON Point properties should contain `device_id` or `id`, and `device_type`.

Fetch `GET /telemetry/schema` for accepted telemetry metrics, units, and expected ranges. Include source units with every upload so values can be normalized (for example 2.5 Gbps -> 2500 Mbps):

```bash
curl -X POST http://localhost:8000/telemetry \
  -H 'Content-Type: application/json' \
  -d '{
    "device_id":"RTR_CAMPUS_1",
    "metrics":{"bandwidth":2.5,"latency_ms":35,"packet_loss_pct":0.2},
    "units":{"bandwidth":"Gbps","latency_ms":"ms","packet_loss_pct":"%"}
  }'
```

The dashboard also accepts a telemetry JSON file. Normalized units are Mbps for bandwidth, ms for latency/jitter, % for utilization/loss, °C for temperature, and documented event/packet/error units for counters.

## Agent workflow

Agent functions are isolated in `backend/agents/`; shared Pydantic classes live in `backend/common/classes/`.

1. Normalization validates metric names and units.
2. Performance compares telemetry to normal ranges.
3. Infrastructure evaluates queue drops, interface errors, and temperature.
4. Health Check reviews up to two hours of device data and identifies affected routers.
5. Connectivity searches nearby inventory devices with Redis geospatial queries.
6. UTM checks firewall metrics and asks for missing security information.
7. Correlation combines static rules and client answers. It reports causes only when a rule is at least 90%; otherwise it requests information or reports insufficient information.
8. Reporting returns a typed incident report and the map highlights healthy, warning, critical, and nearby-risk devices.

The Python worker uses Redis Streams consumer groups, acknowledges successful processing, retries failures, and moves messages that exceed `WORKER_MAX_DELIVERIES` to `netcoop:telemetry:dead`. Redis Streams is used instead of BullMQ because BullMQ is Node.js-only; this keeps the complete backend and worker in Python.

Rule probabilities are deterministic confidence settings, not statistically calibrated forecasts. SQLite is for this demo; use a production database, authentication, and network-validated rules before operational deployment.
