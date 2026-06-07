#!/usr/bin/env python3
"""
ScoutIQ - MongoDB Atlas Setup & Seeding Script
Run this once to initialize your database with World Cup 2026 player data.
"""

import json
import os
import sys
from pathlib import Path

try:
    from pymongo import MongoClient
    from pymongo.operations import SearchIndexModel
except ImportError:
    print("Installing pymongo...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymongo", "--break-system-packages", "-q"])
    from pymongo import MongoClient
    from pymongo.operations import SearchIndexModel

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "scoutiq"

def load_json(path):
    with open(path) as f:
        return json.load(f)

def seed_database():
    print("🔗 Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    data_dir = Path(__file__).parent.parent / "data"

    # ── Players ──────────────────────────────────────────────────
    print("⚽ Seeding players collection...")
    players_col = db["players"]
    players_col.drop()
    players = load_json(data_dir / "players.json")

    # Add computed search fields
    for p in players:
        attrs = p.get("attributes", {})
        p["overall_rating"] = round(
            attrs.get("pace", 0) * 0.15 +
            attrs.get("shooting", 0) * 0.20 +
            attrs.get("passing", 0) * 0.15 +
            attrs.get("dribbling", 0) * 0.20 +
            attrs.get("defending", 0) * 0.15 +
            attrs.get("physical", 0) * 0.15
        )
        p["style_text"] = " ".join(p.get("style_tags", []))
        p["search_text"] = f"{p['name']} {p['nationality']} {p['position']} {p['club']} {p['style_text']} {p['description']}"

    result = players_col.insert_many(players)
    print(f"   ✅ Inserted {len(result.inserted_ids)} players")

    # ── Match Stats ───────────────────────────────────────────────
    print("📊 Seeding match_stats collection...")
    stats_col = db["match_stats"]
    stats_col.drop()
    stats = load_json(data_dir / "match_stats.json")
    result = stats_col.insert_many(stats)
    print(f"   ✅ Inserted {len(result.inserted_ids)} stat records")

    # ── Scout Reports (empty, filled by agent) ────────────────────
    print("📋 Creating scout_reports collection...")
    if "scout_reports" not in db.list_collection_names():
        db.create_collection("scout_reports")
    print("   ✅ scout_reports collection ready")

    # ── Indexes ───────────────────────────────────────────────────
    print("🔍 Creating indexes...")

    players_col.create_index("name")
    players_col.create_index("position")
    players_col.create_index("nationality")
    players_col.create_index("confederation")
    players_col.create_index("age")
    players_col.create_index("overall_rating")
    players_col.create_index([("position", 1), ("overall_rating", -1)])

    stats_col.create_index("player_name")
    stats_col.create_index("tournament")
    stats_col.create_index([("player_name", 1), ("tournament", 1)])

    db["scout_reports"].create_index("player_name")
    db["scout_reports"].create_index("created_at")

    print("   ✅ Indexes created")

    print("\n🎉 Database seeded successfully!")
    print(f"   Database: {DB_NAME}")
    print(f"   Players: {players_col.count_documents({})}")
    print(f"   Match stats: {stats_col.count_documents({})}")

    # Sample check
    sample = players_col.find_one({"position": "ST"}, {"name": 1, "overall_rating": 1})
    if sample:
        print(f"   Sample player: {sample['name']} (OVR {sample['overall_rating']})")

    client.close()
    return True

if __name__ == "__main__":
    try:
        seed_database()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
