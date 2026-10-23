# NightShift: Alexa+ On-Call Copilot

A voice-first on-call copilot built as a Python MCP server for the Alexa+ track.
It covers the full incident loop by voice: check status, log actions, draft the RCA.

> Incident and service data is **simulated** for this hackathon demo.

## Tools

| Tool | Example phrase | What it does |
|---|---|---|
| `get_active_incidents` | "What P1s are active right now?" | Short spoken summary, most severe first |
| `get_service_health` | "How is the payments service doing?" | Health status plus most likely cause from recent changes (or says it doesn't know) |
| `log_and_draft_rca` | "Log that I restarted the node pool" / "Draft the RCA" | Saves timestamped timeline entries, then builds a structured RCA draft |

## Run it

```bash
pip install -r requirements.txt

python server.py          # stdio transport
python server.py --http   # streamable HTTP at http://localhost:8000/mcp
```

Logged entries are saved to `data/timeline.json`; RCA drafts to `data/rca_<incident>.md`.

## Design notes

- **Written for the ear:** answers are short and ordered by severity.
- **Honest:** it reports only what is in the data and says when a cause is unknown.
- **Clear tool descriptions:** each docstring tells Alexa+ when to call the tool.

## Next

Real sources (Azure Service Health, ServiceNow), voice escalation, a confirmation step
before any system-changing action, and multi-language support.
