#!/usr/bin/env python3
"""
ScoutIQ Backend — FastAPI agent server
Wraps the Gemini-powered scouting agent and exposes a chat API.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from pydantic import BaseModel
    import pymongo  # type: ignore
    MongoClient = pymongo.MongoClient
    DESCENDING = pymongo.DESCENDING
    # Import google.generativeai dynamically and silence static analyzers if it's not available
    try:
        import google.generativeai as genai  # type: ignore
    except Exception:
        genai = None
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "fastapi", "uvicorn[standard]", "pymongo",
        "google-generativeai", "pydantic", "--break-system-packages", "-q"
    ])
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from pydantic import BaseModel
    import pymongo  # type: ignore
    MongoClient = pymongo.MongoClient
    DESCENDING = pymongo.DESCENDING
    try:
        import google.generativeai as genai  # type: ignore
    except Exception:
        genai = None

# Provide type-only imports to help static analyzers / editors that check imports without executing the installer
if TYPE_CHECKING:
    from pymongo import MongoClient, DESCENDING  # type: ignore

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URI   = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")
DB_NAME     = "scoutiq"

app = FastAPI(title="ScoutIQ API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB ────────────────────────────────────────────────────────────────────────
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# ── Gemini ────────────────────────────────────────────────────────────────────
if GEMINI_KEY and genai:
    genai.configure(api_key=GEMINI_KEY)

# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []

class ChatResponse(BaseModel):
    response: str
    data: dict | None = None
    action: str | None = None

# ── MongoDB Tool Functions (the MCP-equivalent layer) ─────────────────────────

def find_players(filters: dict = {}, sort_by: str = "overall_rating",
                 limit: int = 10, projection: dict = None) -> list[dict]:
    """Query the players collection with flexible filters."""
    proj = projection or {
        "name": 1, "nationality": 1, "position": 1, "age": 1,
        "foot": 1, "height_cm": 1, "club": 1, "confederation": 1,
        "attributes": 1, "overall_rating": 1, "style_tags": 1,
        "description": 1, "_id": 0
    }
    results = list(
        db["players"].find(filters, proj)
        .sort(sort_by, DESCENDING)
        .limit(limit)
    )
    return results


def search_players_text(query: str, limit: int = 8) -> list[dict]:
    """Full-text search across player descriptions and style tags."""
    # Use regex search across multiple fields (Atlas Search in production)
    words = query.lower().split()
    conditions = []
    for word in words:
        pattern = re.compile(word, re.IGNORECASE)
        conditions.append({
            "$or": [
                {"description": pattern},
                {"style_text": pattern},
                {"name": pattern},
                {"nationality": pattern},
                {"position": pattern},
                {"confederation": pattern},
            ]
        })
    mongo_filter = {"$and": conditions} if conditions else {}
    return find_players(mongo_filter, limit=limit)


def get_player_stats(player_name: str) -> list[dict]:
    """Retrieve match statistics for a player."""
    return list(db["match_stats"].find(
        {"player_name": {"$regex": player_name, "$options": "i"}},
        {"_id": 0}
    ))


def aggregate_top_scorers(min_matches: int = 8, limit: int = 10) -> list[dict]:
    """Aggregate pipeline: top scorers with goals-per-match ratio."""
    pipeline = [
        {"$match": {"matches": {"$gte": min_matches}}},
        {"$group": {
            "_id": "$player_name",
            "total_goals": {"$sum": "$goals"},
            "total_assists": {"$sum": "$assists"},
            "total_matches": {"$sum": "$matches"},
            "avg_xG": {"$avg": "$xG"}
        }},
        {"$addFields": {
            "goals_per_match": {"$divide": ["$total_goals", "$total_matches"]},
            "goal_contributions": {"$add": ["$total_goals", "$total_assists"]}
        }},
        {"$sort": {"total_goals": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "player": "$_id",
                      "total_goals": 1, "total_assists": 1,
                      "total_matches": 1, "goals_per_match": 1,
                      "goal_contributions": 1, "avg_xG": 1}}
    ]
    return list(db["match_stats"].aggregate(pipeline))


def build_lineup(formation: str = "4-3-3", style: str = "") -> dict:
    """Build an optimal lineup for a given formation."""
    formation_map = {
        "4-3-3":  {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CDM": 1, "CM": 2, "LW": 1, "RW": 1, "ST": 1},
        "4-2-3-1":{"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CDM": 2, "CAM": 1, "LW": 1, "RW": 1, "ST": 1},
        "3-5-2":  {"GK": 1, "CB": 3, "LB": 1, "RB": 1, "CM": 2, "CAM": 1, "ST": 2},
        "4-4-2":  {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CM": 4, "ST": 2},
        "5-3-2":  {"GK": 1, "CB": 3, "LB": 1, "RB": 1, "CM": 3, "ST": 2},
    }
    slots = formation_map.get(formation, formation_map["4-3-3"])
    lineup = {"formation": formation, "players": {}, "bench": []}

    used_players = set()
    for pos, count in slots.items():
        # Map position variants
        pos_filter: Any = pos
        if pos in ("LW", "RW"):
            pos_filter = {"$in": ["LW", "RW", "W"]}
        elif pos in ("LB", "RB"):
            pos_filter = {"$in": ["LB", "RB", "FB"]}
        elif pos == "CDM":
            pos_filter = {"$in": ["CDM", "DM"]}
        elif pos == "CAM":
            pos_filter = {"$in": ["CAM", "AM"]}

        candidates = find_players(
            {"position": pos_filter if isinstance(pos_filter, dict) else pos,
             "name": {"$nin": list(used_players)}},
            sort_by="overall_rating",
            limit=count * 3
        )
        if isinstance(pos_filter, dict):
            candidates = find_players(
                {"position": {"$in": ["LW", "RW", "W", "LB", "RB", "FB", "CDM", "DM", "CAM", "AM", pos]},
                 "name": {"$nin": list(used_players)}},
                sort_by="overall_rating",
                limit=count * 4
            )
            candidates = [p for p in candidates if p.get("position") in
                         ["LW","RW","W","LB","RB","FB","CDM","DM","CAM","AM", pos]][:count*2]

        selected = candidates[:count]
        for p in selected:
            used_players.add(p["name"])
        lineup["players"][pos] = selected

    return lineup


def save_scout_report(player_name: str, report_text: str,
                      tags: list[str] = []) -> dict:
    """Save an AI-generated scouting report back to MongoDB."""
    report = {
        "player_name": player_name,
        "report": report_text,
        "tags": tags,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "ScoutIQ Agent"
    }
    result = db["scout_reports"].insert_one(report)
    return {"inserted_id": str(result.inserted_id), "player_name": player_name}


def get_scout_reports(player_name: str = None) -> list[dict]:
    """Retrieve saved scouting reports."""
    query = {}
    if player_name:
        query["player_name"] = {"$regex": player_name, "$options": "i"}
    return list(db["scout_reports"].find(query, {"_id": 0})
                .sort("created_at", DESCENDING).limit(20))


def compare_players(names: list[str]) -> list[dict]:
    """Fetch multiple players for comparison."""
    pattern = {"$in": [re.compile(n, re.IGNORECASE) for n in names]}
    return find_players({"name": pattern}, limit=len(names))


# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are ScoutIQ, an elite AI football scout for the 2026 FIFA World Cup.
You have deep knowledge of world football and access to a MongoDB database of player profiles, match statistics, and scouting reports.

Your personality: confident, analytical, passionate about football. You give expert opinions backed by data. You use football terminology naturally.

You can perform these actions by responding with JSON commands:

**PLAYER SEARCH**: {"action": "search", "query": "...", "filters": {...}}
  - filters can include: position, nationality, confederation, age, foot
  - Examples: {"action":"search","query":"explosive left-footed winger","filters":{"confederation":"UEFA"}}

**GET STATS**: {"action": "stats", "player": "Player Name"}

**TOP SCORERS**: {"action": "top_scorers", "min_matches": 8}

**BUILD LINEUP**: {"action": "lineup", "formation": "4-3-3", "style": "pressing"}

**SCOUT REPORT**: {"action": "scout_report", "player": "Player Name"}
  - This searches for the player, gets their stats, and writes + SAVES a full scouting report to the database

**COMPARE**: {"action": "compare", "players": ["Name1", "Name2"]}

**GET REPORTS**: {"action": "get_reports", "player": "optional filter"}

RULES:
1. Always respond with a friendly analysis PLUS one or more JSON commands when data is needed
2. After getting data back, provide rich football analysis - not just lists
3. For scout reports, write them in proper scouting format: Overview, Technical Qualities, Physical Profile, Tactical Fit, Weaknesses, Recommendation
4. When building lineups, explain WHY each player was chosen
5. Format JSON commands on their own line wrapped in ```json blocks
6. Be specific about player qualities - mention actual attributes and statistics

Start by greeting the user and suggesting what they can ask."""

# ── Agent Logic ───────────────────────────────────────────────────────────────

def execute_action(action_data: dict) -> tuple[str, dict | None]:
    """Execute a MongoDB tool call and return formatted results."""
    action = action_data.get("action")

    if action == "search":
        query = action_data.get("query", "")
        filters = action_data.get("filters", {})
        if query:
            players = search_players_text(query)
            # Also apply structured filters
            if filters:
                filtered = []
                for p in players:
                    match = True
                    if "position" in filters and p.get("position") != filters["position"]:
                        match = False
                    if "confederation" in filters and p.get("confederation") != filters["confederation"]:
                        match = False
                    if "nationality" in filters and filters["nationality"].lower() not in p.get("nationality","").lower():
                        match = False
                    if match:
                        filtered.append(p)
                players = filtered if filtered else players
        else:
            players = find_players(filters)
        return f"Found {len(players)} players:\n" + json.dumps(players, indent=2), {"type": "players", "data": players}

    elif action == "stats":
        player = action_data.get("player", "")
        stats = get_player_stats(player)
        player_data = find_players({"name": re.compile(player, re.IGNORECASE)}, limit=1)
        return f"Stats for {player}:\n" + json.dumps({"player": player_data, "stats": stats}, indent=2), \
               {"type": "stats", "data": {"player": player_data[0] if player_data else {}, "stats": stats}}

    elif action == "top_scorers":
        min_matches = action_data.get("min_matches", 8)
        scorers = aggregate_top_scorers(min_matches)
        return "Top scorers:\n" + json.dumps(scorers, indent=2), {"type": "top_scorers", "data": scorers}

    elif action == "lineup":
        formation = action_data.get("formation", "4-3-3")
        style = action_data.get("style", "")
        lineup = build_lineup(formation, style)
        return f"{formation} lineup:\n" + json.dumps(lineup, indent=2), {"type": "lineup", "data": lineup}

    elif action == "scout_report":
        player_name = action_data.get("player", "")
        players = find_players({"name": re.compile(player_name, re.IGNORECASE)}, limit=1)
        stats = get_player_stats(player_name)
        return f"Player data for report:\n" + json.dumps({"player": players, "stats": stats}, indent=2), \
               {"type": "scout_report_data", "player": player_name,
                "data": {"player": players[0] if players else {}, "stats": stats}}

    elif action == "compare":
        names = action_data.get("players", [])
        players = compare_players(names)
        return f"Comparison data:\n" + json.dumps(players, indent=2), {"type": "compare", "data": players}

    elif action == "get_reports":
        player = action_data.get("player")
        reports = get_scout_reports(player)
        return f"Scouting reports:\n" + json.dumps(reports, indent=2), {"type": "reports", "data": reports}

    return "Unknown action", None


def extract_json_actions(text: str) -> list[dict]:
    """Parse JSON action blocks from model response."""
    actions = []
    # Match ```json blocks
    blocks = re.findall(r"```json\s*([\s\S]*?)```", text, re.IGNORECASE)
    for block in blocks:
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict) and "action" in data:
                actions.append(data)
        except Exception:
            pass
    # Also look for bare JSON with action key
    bare = re.findall(r'\{"action":\s*"[^"]+".+?\}', text)
    for b in bare:
        try:
            data = json.loads(b)
            if data not in actions:
                actions.append(data)
        except Exception:
            pass
    return actions


async def run_agent(message: str, history: list[dict]) -> tuple[str, dict | None]:
    """Multi-step agent loop using Gemini."""
    if not GEMINI_KEY or genai is None:
        # Demo mode without Gemini or when the Gemini client isn't available
        return demo_response(message)

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT
    )

    # Build chat history
    chat_history = []
    for h in history[-10:]:  # Last 10 turns
        role = "user" if h["role"] == "user" else "model"
        chat_history.append({"role": role, "parts": [h["content"]]})

    chat = model.start_chat(history=chat_history)

    # Step 1: Initial response with possible actions
    response = chat.send_message(message)
    response_text = response.text
    actions = extract_json_actions(response_text)

    tool_results = []
    response_data = None

    # Step 2: Execute each action
    for action_data in actions:
        tool_result, data = execute_action(action_data)
        tool_results.append(tool_result)
        if data:
            response_data = data

    # Step 3: If there were tool calls, send results back for analysis
    if tool_results:
        results_msg = "Here is the data from the database:\n\n" + "\n\n---\n\n".join(tool_results)
        results_msg += "\n\nNow provide your expert analysis and insights based on this data. Do NOT repeat any JSON commands in this response."

        final_response = chat.send_message(results_msg)
        final_text = final_response.text

        # If this was a scout report, save it
        if response_data and response_data.get("type") == "scout_report_data":
            player_name = response_data.get("player", "Unknown")
            save_result = save_scout_report(
                player_name,
                final_text,
                tags=["auto-generated", "2026-world-cup"]
            )
            response_data["saved"] = save_result

        return final_text, response_data

    return response_text, response_data


def demo_response(message: str) -> tuple[str, dict | None]:
    """Demo responses when no Gemini key is provided."""
    msg = message.lower()

    if any(w in msg for w in ["striker", "forward", "goal", "shoot"]):
        players = find_players({"position": "ST"}, limit=5)
        return (
            f"🎯 Here are the top strikers for the 2026 World Cup:\n\n" +
            "\n".join([f"**{p['name']}** ({p['nationality']}) — OVR {p['overall_rating']} | {', '.join(p['style_tags'][:2])}" for p in players]) +
            "\n\n*Connect a Gemini API key for full AI analysis.*",
            {"type": "players", "data": players}
        )
    elif any(w in msg for w in ["lineup", "formation", "team", "squad"]):
        lineup = build_lineup("4-3-3")
        return (
            "⚽ Here's an optimal 4-3-3 lineup built from World Cup 2026 players!\n\n*Connect a Gemini API key for AI-powered tactical analysis.*",
            {"type": "lineup", "data": lineup}
        )
    elif any(w in msg for w in ["stat", "score", "goals"]):
        scorers = aggregate_top_scorers()
        return (
            "📊 Top scorers from World Cup 2026 qualifying:\n\n" +
            "\n".join([f"**{s['player']}** — {s['total_goals']}G / {s['total_assists']}A in {s['total_matches']} matches" for s in scorers[:5]]) +
            "\n\n*Connect a Gemini API key for full AI analysis.*",
            {"type": "top_scorers", "data": scorers}
        )
    else:
        players = search_players_text(message, limit=5)
        if players:
            return (
                f"🔍 Found {len(players)} matching players:\n\n" +
                "\n".join([f"**{p['name']}** ({p['nationality']}, {p['position']}) — {p['description'][:80]}..." for p in players]) +
                "\n\n*Connect a Gemini API key for full AI-powered scouting.*",
                {"type": "players", "data": players}
            )
        return (
            "👋 Welcome to **ScoutIQ** — your AI Football Scout for the 2026 World Cup!\n\nTry asking me:\n- *'Find me the best strikers in CONCACAF'*\n- *'Build a 4-3-3 lineup'*\n- *'Who are the top scorers?'*\n- *'Scout report on Mbappé'*\n\n*Connect a Gemini API key for full AI-powered analysis.*",
            None
        )

# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "db": DB_NAME}


@app.get("/api/players")
def get_players(position: str = None, confederation: str = None, limit: int = 20):
    filters = {}
    if position:
        filters["position"] = position
    if confederation:
        filters["confederation"] = confederation
    return {"players": find_players(filters, limit=limit)}


@app.get("/api/stats/top-scorers")
def top_scorers():
    return {"scorers": aggregate_top_scorers()}


@app.get("/api/reports")
def list_reports(player: str = None):
    return {"reports": get_scout_reports(player)}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        response_text, data = await run_agent(req.message, req.history)
        return ChatResponse(
            response=response_text,
            data=data,
            action=data.get("type") if data else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Serve frontend ────────────────────────────────────────────────────────────
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(frontend_dir / "index.html"))

    @app.get("/{path:path}")
    def catch_all(path: str):
        f = frontend_dir / path
        if f.exists():
            return FileResponse(str(f))
        return FileResponse(str(frontend_dir / "index.html"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 ScoutIQ API starting on http://localhost:{port}")
    print(f"🔗 MongoDB: {MONGO_URI[:40]}...")
    print(f"🤖 Gemini: {'configured' if GEMINI_KEY else 'demo mode (set GEMINI_API_KEY)'}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
