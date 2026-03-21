# Local Dev Observability Stack

Lightweight log aggregation for local development.
**File-based collectors → Loki → Grafana** — no cloud account required.

```
your app writes logs          tails files          stores logs        visualises
  ./logs/*.log    ──►  Vector (or Promtail)  ──►  Loki  ──►  Grafana
  ./logs/*.jsonl
```

---

## Quick Start

```bash
# 1. Copy and edit the environment file
cp .env.example .env
#    Set LOG_DIR to the folder where your app writes log files.

# 2. Start the stack
docker compose -f docker-compose.observability.yml up -d

# 3. Open Grafana
open http://localhost:3000
#    Navigate to: Dashboards → Local Dev → "Local Dev — Log Explorer"
```

---

## Directory Layout

```
observability/
├── docker-compose.observability.yml  # Main compose file (Vector variant)
├── .env.example                      # Environment variables template
│
├── vector/
│   └── vector.toml          # Collector config — watches LOG_DIR, ships to Loki
│
├── promtail/
│   └── promtail.yaml        # Alternative collector (Grafana Promtail)
│
├── loki/
│   └── loki.yaml            # Single-process Loki, filesystem storage
│
└── grafana/
    └── provisioning/
        ├── datasources/
        │   └── loki.yaml            # Auto-wires Loki as default datasource
        └── dashboards/
            ├── dashboard-provider.yaml
            └── local-dev-logs.json  # Pre-built log explorer dashboard
```

---

## Choosing a Collector

| | **Vector** (default) | **Promtail** |
|---|---|---|
| Image | `timberio/vector` | `grafana/promtail` |
| Config | `vector/vector.toml` | `promtail/promtail.yaml` |
| Strengths | Rich VRL transforms, multi-sink | Native Loki integration, simple pipeline |
| Best for | Complex parsing / routing | Teams already using the Grafana stack |

To switch to Promtail, replace the `vector` service block in `docker-compose.observability.yml` with:

```yaml
  promtail:
    image: grafana/promtail:2.9.6
    container_name: obs-promtail
    restart: unless-stopped
    command: -config.file=/etc/promtail/promtail.yaml
    volumes:
      - ./promtail/promtail.yaml:/etc/promtail/promtail.yaml:ro
      - ${LOG_DIR:-./logs}:/var/log/app:ro
    networks:
      - obs-net
    depends_on:
      - loki
```

---

## Log File Conventions

### Plain text logs
Any line matching this pattern is auto-parsed:
```
2024-03-14T10:22:01Z  INFO  server started on :8080
2024-03-14T10:22:05Z  ERROR failed to connect to db: timeout
```

### JSON / NDJSON logs
One JSON object per line; common field names are normalised automatically:

| Accepted field names | Normalised to |
|---|---|
| `level`, `severity`, `lvl` | `level` |
| `message`, `msg`, `text` | `message` |
| `service`, `app` | `service` |
| `timestamp`, `ts` | timestamp (RFC3339 or Unix ms) |

---

## Ports

| Service | Port | Purpose |
|---|---|---|
| Grafana | 3000 | Web UI |
| Loki | 3100 | HTTP API (push + query) |
| Vector | 8686 | Health / management API |

---

## Retention

Logs are kept for **7 days** by default (configured in `loki/loki.yaml`).
Change `retention_period` to adjust.

---

## Stopping / Cleanup

```bash
# Stop services (keep data)
docker compose -f docker-compose.observability.yml down

# Stop and wipe all data
docker compose -f docker-compose.observability.yml down -v
```
