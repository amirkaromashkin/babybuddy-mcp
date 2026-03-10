# BabyBuddy MCP Server

MCP server for self-hosted [BabyBuddy](https://github.com/babybuddy/babybuddy).

**Transport:** Streamable HTTP (runs on `http://localhost:8080`)
**Auth:** OAuth 2.1 — users log in with their BabyBuddy URL + API token via a browser form, no config files or hardcoded secrets needed.

---

## Quick Start

### 1. Install

```bash
cd babybuddy-mcp
pip install -r requirements.txt
```

### 2. Run

```bash
python3 server.py
# → 🍼 BabyBuddy MCP server starting on http://localhost:8080
```

Optional env vars:

| Variable | Default | Description |
|---|---|---|
| `HOST` | `localhost` | Bind address |
| `PORT` | `8080` | Listen port |
| `SERVER_URL` | `http://localhost:8080` | Public base URL (important if behind a proxy) |
| `TOKEN_TTL` | `86400` | Access token lifetime in seconds |

### 3. Add to Claude Desktop

Claude Desktop only supports stdio transport, so use **`mcp-remote`** as a bridge — it handles the stdio↔HTTP translation and opens the OAuth browser popup automatically.

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "babybuddy": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8080/mcp"]
    }
  }
}
```

Restart Claude Desktop. On first use a browser window opens to `http://localhost:8080/oauth/login` — enter your BabyBuddy URL and API token once. Tokens are remembered for 24 hours.

---

## Tools (24 total)

| Tool | Description |
|---|---|
| `list_children` | List all children (returns IDs needed by other tools) |
| `log_feeding` | Log a feeding — type, method, start/end, optional amount |
| `get_feedings` | Recent feedings for a child |
| `log_sleep` | Log a sleep session (nap or night) |
| `get_sleep` | Recent sleep sessions |
| `log_diaper_change` | Log a diaper change — wet, solid, color, amount |
| `get_diaper_changes` | Recent diaper changes |
| `log_temperature` | Log temperature in °C |
| `get_temperature` | Recent temperature readings |
| `log_weight` | Log weight in kg |
| `get_weight` | Weight history |
| `log_height` | Log height in cm |
| `get_height` | Height history |
| `log_head_circumference` | Log head circumference in cm |
| `get_head_circumference` | Head circumference history |
| `log_pumping` | Log a pumping session in ml |
| `get_pumping` | Recent pumping sessions |
| `add_note` | Add a free-text note |
| `get_notes` | Recent notes |
| `get_timers` | List active timers |
| `start_timer` | Start a new timer |
| `stop_timer` | Stop/delete a timer |
| `get_tags` | List all tags |
| `get_daily_summary` | All events for a child on a given day |

---

## OAuth Flow

```
Claude Desktop ──► MCP server /mcp           (401 + WWW-Authenticate)
                ──► /.well-known/...          (OAuth metadata discovery)
                ──► /oauth/authorize          (server returns login URL)
  Browser       ──► /oauth/login?state=...    (login form)
  User fills in URL + token, hits Connect
  Server validates token against BabyBuddy /api/children/
                ──► redirect_uri?code=...     (back to Claude with auth code)
Claude Desktop  ──► /oauth/token             (exchange code → access token)
                ──► /mcp (Bearer token)       (all subsequent requests)
```

No BabyBuddy configuration needed — the server works with any instance. Multiple users can authenticate independently (each gets their own session).

---

## Deploying to Google Cloud Run

The included `Dockerfile` targets Cloud Run. One-time setup then a single deploy command.

### Prerequisites

```bash
# Set your deployment variables
export BABYBUDDY_INSTANCE_PROJECT_ID="playground-2-489517"
export BABYBUDDY_INSTANCE_REGION="europe-north1"
export BABYBUDDY_INSTANCE_URL="https://babybuddy-mcp-191758225341.europe-north1.run.app"
export BABYBUDDY_INSTANCE_AUTH_TOKEN="83879a020e89c31ea801b40e99faabf70122abdc"

# Login and configure gcloud
gcloud auth login
gcloud config set project $BABYBUDDY_INSTANCE_PROJECT_ID
```

### Deploy to GCP

```bash
gcloud run deploy babybuddy-mcp \
  --project=$BABYBUDDY_INSTANCE_PROJECT_ID \
  --source=. \
  --region=$BABYBUDDY_INSTANCE_REGION \
  --allow-unauthenticated \
  --timeout=3600 \
  --min-instances=0 \
  --max-instances=1 \
  --set-env-vars="SERVER_URL=$BABYBUDDY_INSTANCE_URL"
```

Cloud Run will print your service URL, e.g. `https://babybuddy-mcp-191758225341.europe-north1.run.app`.

Then set `SERVER_URL` so OAuth redirects use the correct public URL:

```bash
gcloud run services update babybuddy-mcp \
  --region europe-north1 \
  --set-env-vars SERVER_URL=https://babybuddy-mcp-xxxxxxxxxx-lz.a.run.app
```

### Update Claude Desktop config

```json
{
  "mcpServers": {
    "babybuddy": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://babybuddy-mcp-xxxxxxxxxx-lz.a.run.app/mcp"]
    }
  }
}
```

### Subsequent deploys

```bash
gcloud run deploy babybuddy-mcp --source . --region europe-north1
```

---

## Persistent Storage

By default tokens are in-memory and lost on restart (Cloud Run scales to zero after inactivity, so users re-authenticate on next use). For always-on deployments, replace `_auth_codes`, `_access_tokens`, `_refresh_tokens`, and `_clients` with a Cloud Firestore or Redis backend in `server.py`.
