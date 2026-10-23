"""NightShift: voice-first on-call copilot (MCP server for Alexa+).

Tools:
  - get_active_incidents
  - get_service_health
  - log_and_draft_rca

Incident and service data is SIMULATED for the hackathon demo.
Run:  python server.py            (stdio)
      python server.py --http     (streamable HTTP on :8000/mcp)
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("nightshift", host="0.0.0.0", port=8000)

NOW = lambda: datetime.now(timezone.utc)
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
TIMELINE_FILE = DATA_DIR / "timeline.json"

# ---------------------------------------------------------------------------
# Simulated data (offsets are minutes before "now" so the demo always looks live)
# ---------------------------------------------------------------------------
INCIDENTS = [
    {"id": "INC-1042", "severity": "P1", "service": "payments",
     "summary": "elevated 5xx errors on the payments API",
     "started_min_ago": 38, "status": "investigating"},
    {"id": "INC-1043", "severity": "P1", "service": "identity",
     "summary": "intermittent sign-in failures in West Europe",
     "started_min_ago": 15, "status": "mitigating"},
    {"id": "INC-1039", "severity": "P2", "service": "search",
     "summary": "slow query latency",
     "started_min_ago": 190, "status": "monitoring"},
]

SERVICES = {
    "payments": {
        "status": "degraded",
        "detail": "error rate about 12 percent, normal is under 1 percent",
        "recent_changes": [
            {"what": "deployment payments-api v2.14.3", "min_ago": 54},
            {"what": "node pool scale-down in East US", "min_ago": 70},
        ],
    },
    "identity": {
        "status": "degraded",
        "detail": "about 4 percent of sign-ins failing in West Europe",
        "recent_changes": [{"what": "certificate rotation", "min_ago": 33}],
    },
    "search": {
        "status": "degraded",
        "detail": "p95 latency is 3 times normal",
        "recent_changes": [],
    },
    "storage": {"status": "healthy", "detail": "all metrics normal", "recent_changes": []},
}

SEV_ORDER = {"P1": 0, "P2": 1, "P3": 2}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_timeline() -> dict:
    if TIMELINE_FILE.exists():
        return json.loads(TIMELINE_FILE.read_text())
    return {}


def _save_timeline(tl: dict) -> None:
    TIMELINE_FILE.write_text(json.dumps(tl, indent=2))


def _norm_service(name: str) -> str:
    n = name.lower().strip()
    for suffix in (" service", " api"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return n


def _minutes_phrase(m: int) -> str:
    if m < 60:
        return f"{m} minutes"
    h, rem = divmod(m, 60)
    return f"{h} hour{'s' if h != 1 else ''}" + (f" {rem} minutes" if rem else "")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool()
def get_active_incidents(severity: str = "P1") -> str:
    """Use when the user asks which incidents are active, open, or ongoing right now,
    e.g. "what P1s are active?". `severity` is "P1", "P2", or "all" (default "P1").
    Returns a short spoken summary, most severe and newest first."""
    sev = severity.upper().strip()
    items = [i for i in INCIDENTS if sev == "ALL" or i["severity"] == sev]
    items.sort(key=lambda i: (SEV_ORDER[i["severity"]], i["started_min_ago"]))
    label = "incidents" if sev == "ALL" else f"{sev} incidents"
    if not items:
        return f"There are no active {label} right now."
    n = len(items)
    parts = [f"{n} active {label[:-1] if n == 1 else label}."]
    for i in items:
        parts.append(
            f"{i['severity']}, {i['service']}: {i['summary']}, "
            f"started {_minutes_phrase(i['started_min_ago'])} ago, {i['status']}."
        )
    return " ".join(parts)


@mcp.tool()
def get_service_health(service: str) -> str:
    """Use when the user asks how a specific service is doing, e.g. "how is the
    payments service doing?". `service` is the service name. Returns current health
    and the most likely cause based on recent changes, or says the cause is unknown."""
    key = _norm_service(service)
    svc = SERVICES.get(key)
    if not svc:
        known = ", ".join(SERVICES)
        return f"I don't have data for a service called {service}. I can check {known}."
    if svc["status"] == "healthy":
        return f"{key.capitalize()} is healthy. {svc['detail'].capitalize()}."
    msg = f"{key.capitalize()} is {svc['status']}: {svc['detail']}."
    changes = sorted(svc["recent_changes"], key=lambda c: c["min_ago"])
    if changes:
        c = changes[0]
        msg += (
            f" Most recent change was a {c['what']}, {_minutes_phrase(c['min_ago'])} ago. "
            "That is a likely cause, but I can't confirm it."
        )
    else:
        msg += " I don't see any recent changes, so I can't name a cause."
    return msg


@mcp.tool()
def log_and_draft_rca(action: str, incident_id: str = "INC-1042", entry: str = "") -> str:
    """Two modes. action="log": save a timestamped note to the incident timeline, used
    for things like "log that I restarted the node pool" (put the note in `entry`).
    action="draft": when the incident is over, turn the logged timeline into a
    structured RCA draft (impact, timeline, root cause, actions).
    `incident_id` defaults to the main active incident, INC-1042."""
    action = action.lower().strip()
    timeline = _load_timeline()
    entries = timeline.setdefault(incident_id, [])

    if action == "log":
        if not entry.strip():
            return "I didn't catch what to log. What should I add to the timeline?"
        stamp = NOW().strftime("%H:%M UTC")
        entries.append({"time": NOW().isoformat(timespec="seconds"), "entry": entry.strip()})
        _save_timeline(timeline)
        return f"Logged at {stamp}: {entry.strip()}."

    if action == "draft":
        if not entries:
            return f"There is nothing logged for {incident_id} yet, so I can't draft an RCA."
        inc = next((i for i in INCIDENTS if i["id"] == incident_id), None)
        svc = SERVICES.get(inc["service"]) if inc else None
        suspected = (
            sorted(svc["recent_changes"], key=lambda c: c["min_ago"])[0]["what"]
            if svc and svc["recent_changes"] else None
        )
        lines = [f"# RCA draft: {incident_id}", ""]
        lines += ["## Impact",
                  f"{inc['severity']} on {inc['service']}: {inc['summary']}." if inc
                  else "Not recorded.", ""]
        lines += ["## Timeline (UTC)"]
        for e in entries:
            t = datetime.fromisoformat(e["time"]).strftime("%H:%M")
            lines.append(f"- {t} {e['entry']}")
        lines += ["", "## Root cause",
                  f"Suspected: {suspected}. Not confirmed, needs review." if suspected
                  else "Not identified in the logged data. Needs review.", ""]
        lines += ["## Actions taken"] + [f"- {e['entry']}" for e in entries]
        lines += ["", "## Follow-ups", "- To be agreed in the post-incident review."]
        out = DATA_DIR / f"rca_{incident_id}.md"
        out.write_text("\n".join(lines))
        return (
            f"RCA draft for {incident_id} is ready with {len(entries)} timeline "
            f"entr{'y' if len(entries) == 1 else 'ies'}. "
            + (f"Root cause is marked as suspected: {suspected}." if suspected
               else "Root cause is not identified yet.")
            + f" Saved to {out.name}."
        )

    return 'I can either "log" a note or "draft" the RCA. Which one do you want?'


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
