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

- `API_URL`: defaults to the deployed backend at `https://netcoopai.onrender.com`; use `http://localhost:8000` only when intentionally connecting the dashboard to a locally running API.
- `BACKEND_URL`: defaults to `https://netcoopai.onrender.com` for the worker; use `http://localhost:8000` when the worker should process against the local API.
- `INTERNAL_TOKEN`: replace the placeholder with a random private value, e.g. `openssl rand -hex 32`.
- `REDIS_URL`: for local Redis use `redis://localhost:6379/0`.
- `GROQ_API_KEY`: optional; enables Groq cause scoring and report narrative.
- `GROQ_MODEL`: optional; defaults to `llama-3.3-70b-versatile`.
- `TAVILY_API_KEY`: optional; enables external issue research only when telemetry is abnormal and no local diagnostic rule matches.
- `REDIS_URL`: defaults to local Redis. For Upstash, use its **Redis connection string** (`rediss://...`), not its REST URL; the API and worker must use the same value.
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

### Streamlit Community Cloud

When creating or editing the Streamlit app, use the repository `Tirtha29/AgenticAI-Hackathon`, select the `new-main` branch (or merge its latest frontend changes into `main` first), and set the main file to `frontend/streamlit_app.py`. The `main` branch currently has an older frontend import that fails on Streamlit Cloud. Dependencies are read from the root `requirements.txt`. The dashboard defaults to `https://netcoopai.onrender.com`; set `API_URL` in the app's Secrets only if you need to override it.

The 3D campus map is a separate Render web service; Streamlit Cloud cannot embed a server running at `localhost`. Deploy the `netcoopai-campus-map` service from the repository's `render.yaml` Blueprint. After deployment, check its `/api/buildings` health URL returns HTTP 200. The dashboard defaults `CAMPUS_MAP_URL` to `https://netcoopai-campus-map.onrender.com`; if Render assigns a different service URL, set `CAMPUS_MAP_URL` in the Streamlit app's Secrets to that exact HTTPS origin. The dashboard posts each map's inventory snapshot to the map service before embedding its iframe.

The dashboard includes an overview with device health counts, live status and hot-zone maps, recent telemetry charts, incident investigation with an HITL follow-up dialog, a searchable rule knowledge base, device inventory, analytics, settings, and agent execution health/latency. Use the sidebar's **Dark theme** toggle to switch the dashboard appearance. The sidebar can load 15 synthetic IIT Bhubaneswar campus-area devices; this replaces the current inventory, and the sample coordinates are illustrative rather than surveyed placements. The knowledge explorer is also available through `GET /knowledge/rules?q=latency&limit=20`.

### Event-impact simulation

The **Event Simulation** page models festival, sports, livestream, exam, and outage scenarios using the located device inventory. It estimates event demand, device overload, roaming spill-over, shared-uplink effects, timelines, and optional capacity/traffic-shaping mitigations. The animation and ranked recommendations are what-if results only: they do not write to device health or telemetry, and their capacity/traffic assumptions are not calibrated forecasts.

The API exposes `GET /simulation/presets` and `POST /simulation/run`. Omitted scenario settings use preset defaults. For example:

```bash
curl -X POST http://localhost:8000/simulation/run \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"festival","latitude":20.1520,"longitude":85.6748,"attendance":6000}'
```

Upload or load a located inventory before calling the run endpoint; otherwise it returns HTTP 409. Scenario inputs are validated, and simulations support at most 1,500 located devices.

### Docker Compose alternative

Docker Desktop must be running:

```bash
docker compose up --build
```

Compose starts Redis, the Python worker, FastAPI, and Streamlit. It supplies container-specific Redis/API addresses. When running processes directly on the host, use the local addresses in `.env`.

## `.env` reference

Copy `.env.example` to `.env`. Keep only these settings unless you need custom values:

```dotenv
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
INTERNAL_TOKEN=replace-with-a-random-secret
REDIS_URL=redis://localhost:6379/0
API_URL=https://netcoopai.onrender.com
BACKEND_URL=https://netcoopai.onrender.com
DATABASE_PATH=./data/netcoop.db
BLAST_RADIUS_KM=5
TELEMETRY_STREAM=netcoop:telemetry
TELEMETRY_CONSUMER_GROUP=netcoop-workers
WORKER_MAX_DELIVERIES=5
```

Never commit a real API key or `INTERNAL_TOKEN`. Without `GROQ_API_KEY`, static fallback scoring is used and the report labels it as such.

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
7. Web Research searches Tavily only when the device is abnormal and no local rule matches. It stores a few titled, linked search references; it never fetches pages or treats search snippets as verified device facts.
8. Correlation builds candidates from static rules and scores them with Groq using an explicit weighted rubric: rule match 30%, cross-metric support 25%, severity 15%, two-hour history 15%, topology 5%, and client confirmation 10%. If Tavily sources exist, Groq may add up to three separately cited web hypotheses. The backend computes final scores from Pydantic-validated model factors; external hypotheses remain suggestions requiring operator verification. Without a Groq key, deterministic static fallback scores are used and web results are shown as references only.
9. Reporting returns a typed incident report and the map highlights healthy, warning, critical, and nearby-risk devices.

The Python worker uses Redis Streams consumer groups, acknowledges successful processing, retries failures, and moves messages that exceed `WORKER_MAX_DELIVERIES` to `netcoop:telemetry:dead`. Redis Streams is used instead of BullMQ because BullMQ is Node.js-only; this keeps the complete backend and worker in Python.

Set `GROQ_API_KEY` and optionally `TAVILY_API_KEY` in your local `.env`, then restart the API. If Groq is configured but its request or structured response fails, processing fails visibly and the worker retries before dead-lettering; it does not silently substitute static scores. Tavily failures are included in the report while local diagnosis continues. Groq scores are evidence-based confidence estimates, not statistically calibrated forecasts. SQLite is for this demo; use a production database, authentication, and network-validated rules before operational deployment.
