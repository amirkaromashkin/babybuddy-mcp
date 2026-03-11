# BabyBuddy MCP Server

MCP server for self-hosted [BabyBuddy](https://github.com/babybuddy/babybuddy).

**Transport:** Streamable HTTP (runs on `http://localhost:8080`)
**Auth:** Direct API Token via environment variables. No login required.

---

## Quick Start

### 1. Install

```bash
cd babybuddy-mcp
pip install -r requirements.txt
```

### 2. Configure

Set the following environment variables in your `.env` file or shell:

| Variable | Description |
|---|---|
| `BABYBUDDY_INSTANCE` | Your full BabyBuddy URL (e.g., `https://your-instance.com/`) |
| `BABYBUDDY_TOKEN` | Your API token (Settings → API → your token) |

Optional:

| Variable | Default | Description |
|---|---|---|
| `HOST` | `localhost` | Bind address |
| `PORT` | `8080` | Listen port |
| `SERVER_URL` | `http://localhost:8080` | Public base URL |

### 3. Run

```bash
python3 server.py
```

---

## Tools (33 total)

| Tool | Description |
|---|---|
| `list_children` | List all children (returns IDs needed by other tools) |
| `log_feeding` | Log a feeding — type, method, start/end, optional amount |
| `get_feedings` | Recent feedings for a child |
| `delete_feeding` | Delete a feeding session by ID |
| `log_sleep` | Log a sleep session (nap or night) |
| `get_sleep` | Recent sleep sessions |
| `delete_sleep` | Delete a sleep session by ID |
| `log_diaper_change` | Log a diaper change — wet, solid, color, amount |
| `get_diaper_changes` | Recent diaper changes |
| `delete_diaper_change` | Delete a diaper change by ID |
| `log_temperature` | Log temperature in °C |
| `get_temperature` | Recent temperature readings |
| `delete_temperature` | Delete a temperature reading by ID |
| `log_weight` | Log weight in kg |
| `get_weight` | Weight history |
| `delete_weight` | Delete a weight measurement by ID |
| `log_height` | Log height in cm |
| `get_height` | Height history |
| `delete_height` | Delete a height measurement by ID |
| `log_head_circumference` | Log head circumference in cm |
| `get_head_circumference` | Head circumference history |
| `delete_head_circumference` | Delete a head circumference measurement by ID |
| `log_pumping` | Log a pumping session in ml |
| `get_pumping` | Recent pumping sessions |
| `delete_pumping` | Delete a pumping session by ID |
| `add_note` | Add a free-text note |
| `get_notes` | Recent notes |
| `delete_note` | Delete a note by ID |
| `get_timers` | List active timers |
| `start_timer` | Start a new timer |
| `stop_timer` | Stop/delete a timer |
| `get_tags` | List all tags |
| `get_daily_summary` | All events for a child on a given day |

---

## Deploying to Google Cloud Run

The included `Dockerfile` targets Cloud Run.

### Deploy to GCP

```bash
gcloud run deploy babybuddy-mcp \
  --source=. \
  --allow-unauthenticated \
  --set-env-vars="BABYBUDDY_INSTANCE=$BABYBUDDY_INSTANCE,BABYBUDDY_TOKEN=$BABYBUDDY_TOKEN"
```

---

## Testing

To run the end-to-end tests against your real BabyBuddy instance:

1. Ensure your `.env` file has `BABYBUDDY_INSTANCE` and `BABYBUDDY_TOKEN` set.
2. Install test dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```
3. Run the tests:
   ```bash
   uv run pytest tests/test_e2e.py
   ```
