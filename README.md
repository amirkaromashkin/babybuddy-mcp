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

## Deploying to Google Cloud Run

The included `Dockerfile` targets Cloud Run. One-time setup then a single deploy command.

### Prerequisites

```bash
# Install gcloud CLI if you don't have it: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project $PROJECT_ID
gcloud config set region $GCP_REGION
```

### Deploy to GCP

```bash
gcloud run deploy babybuddy-mcp \
  --source=. \
  --allow-unauthenticated \
  --timeout=3600 \
  --min-instances=1 \
  --max-instances=1 \
  --set-env-vars="SERVER_URL=$BABYBUDDY_INSTANCE_URL"
```

Cloud Run will print your service URL, e.g. `https://babybuddy-mcp-1234567890.europe-north1.run.app`.

### Update Claude Desktop config

```json
{
  "mcpServers": {
    "babybuddy": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://babybuddy-mcp-1234567890.europe-north1.run.app/mcp"]
    }
  }
}
```

### Subsequent deploys

```bash
gcloud run deploy babybuddy-mcp --source . --region $GCP_REGION
```

---

## Persistent Login (Always-on)

By default, tokens are stored in memory and lost when the server restarts (e.g., when Cloud Run recycles the container). To avoid having to log in manually after every restart, you can provide your credentials directly via environment variables.

### How to configure:

1.  **Set Environment Variables**:
    *   `BABYBUDDY_INSTANCE`: Your full BabyBuddy URL (e.g., `https://your-instance.com/`)
    *   `BABYBUDDY_TOKEN`: Your API token.

2.  **Deploy with Variables**:
    ```bash
    gcloud run deploy babybuddy-mcp \
      --source . \
      --region $GCP_REGION \
      --set-env-vars="BABYBUDDY_INSTANCE=$BABYBUDDY_INSTANCE,BABYBUDDY_TOKEN=$BABYBUDDY_TOKEN,SERVER_URL=$BABYBUDDY_INSTANCE_URL"
    ```

When these variables are set, the login page will automatically authenticate you and redirect back to Claude without showing any form.
