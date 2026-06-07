# ⚽ ScoutIQ —An AI Football Scout for World Cup 2026

> **Google Cloud Rapid Agent Hackathon** · MongoDB Partner Track  
> Built with **Gemini  · **Google Cloud Agent Builder** · **MongoDB MCP**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MongoDB](https://img.shields.io/badge/MongoDB-7.0-green)](https://mongodb.com)
[![Node.js](https://img.shields.io/badge/Node.js-20-brightgreen)](https://nodejs.org)
[![Deployed on Cloud Run](https://img.shields.io/badge/Cloud%20Run-deployed-blue)](https://cloud.google.com/run)

---

## 🎯 What is ScoutIQ?

ScoutIQ is an **AI-powered football scouting agent** that goes far beyond answering questions — it *thinks*, *queries a live database* and *takes action* on your behalf.

Ask it to:
- **Find players** by any combination of attributes: *"Left-footed strikers under 24 who press hard"*
- **Build lineups**: *"Give me a 4-3-3 optimized to beat a low block"*
- **Compare players**: *"Mbappé vs Haaland at this World Cup — who would you sign?"*
- **Generate & save scout reports**: *"Give me a full scouting report for Lamine Yamal"* — the report is written to MongoDB automatically

---

## 🏗️ Architecture

```
User (Natural Language)
        │
        ▼
 Google Cloud Agent Builder
 + Gemini / Claude Sonnet
        │
        │ Tool calls via MCP
        ▼
 MongoDB MCP Server ──────► MongoDB Atlas
   • find_players              • players collection
   • aggregate_stats           • scout_reports collection
   • save_scout_report         • Atlas Search indexes
   • get_scout_reports         • Aggregation pipelines
        │
        ▼
 Structured Response → Frontend Chat UI
```

### Why this wins

| Criteria | ScoutIQ's approach |
|---|---|
| **Move beyond chat** | Agent runs multi-step MongoDB queries, builds lineups, saves reports |
| **Multi-step mission** | Plans position-by-position queries, reasons holistically, returns a decision |
| **Partner power** | 4 MongoDB MCP tools with real Atlas aggregation pipelines |
| **Real-world impact** | Scouts use this workflow today — AI just makes it 100x faster |

---

## 🚀 Quick Start (Local)

### Prerequisites
- Node.js 20+
- MongoDB (local) or MongoDB Atlas account (free tier works)
- Gemini API key

### 1. Clone & install
```bash
git clone https://github.com/yourusername/scoutiq
cd scoutiq
npm run install:backend
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env — add your GEMINI_API_KEY and MONGODB_URI
```

### 3. Seed the database
```bash
MONGODB_URI=mongodb://localhost:27017 node scripts/setup-atlas.mjs
```

### 4. Start the backend
```bash
npm start
# Backend running on http://localhost:3001
```

### 5. Open the frontend
```bash
open frontend/index.html
# Or serve with: npx serve frontend
```

---

## 🐳 Docker (Full Stack)

```bash
# Copy and fill your env file
cp .env.example .env

# Start everything (MongoDB + backend + frontend)
docker-compose up --build

# Open http://localhost:8080
```

---

## ☁️ Deploy to Google Cloud Run

```bash
# Set your GCP project
export GCP_PROJECT_ID=your-project-id

# Set MongoDB Atlas URI (required for Cloud Run)
export MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/scoutiq"

export GEMINI_API_KEY=your_key

# Deploy
bash scripts/deploy-gcp.sh
```

---

## 🔧 MongoDB MCP Integration

ScoutIQ uses **4 MongoDB tools** via the agent's MCP integration:

### `find_players`
```json
{
  "filter": { "position": "ST", "foot": "Left", "age": { "$lt": 25 } },
  "sort": { "xG": -1 },
  "limit": 5
}
```

### `aggregate_stats`
```json
{
  "pipeline": [
    { "$match": { "position": { "$in": ["LW", "RW"] } } },
    { "$addFields": { "goal_efficiency": { "$divide": ["$goals_wc2026", "$xG"] } } },
    { "$sort": { "goal_efficiency": -1 } },
    { "$limit": 5 }
  ],
  "description": "Wingers overperforming their xG"
}
```

### `save_scout_report`
```json
{
  "player_name": "Lamine Yamal",
  "report": {
    "summary": "Generational talent...",
    "strengths": ["Elite dribbling", "Vision", "Age trajectory"],
    "weaknesses": ["Aerial duels", "Consistency under pressure"],
    "tactical_fit": "Right wing in a 4-3-3 or 4-2-3-1",
    "recommendation": "Sign immediately",
    "scout_rating": 9.2
  }
}
```

### `get_scout_reports`
```json
{ "player_name": "Yamal", "limit": 5 }
```

---

## 📊 Database Schema

### `players` collection
```javascript
{
  name: "Lamine Yamal",
  nationality: "Spain",
  confederation: "UEFA",          // UEFA | CONMEBOL | CONCACAF | CAF | AFC | OFC
  position: "RW",                 // GK | CB | LB | RB | DM | CM | AM | LW | RW | ST
  age: 17,
  foot: "Left",                   // Left | Right
  height_cm: 176,
  market_value_m: 120,            // market value in millions €

  // World Cup 2026 stats
  goals_wc2026: 3,
  assists_wc2026: 6,
  matches_wc2026: 5,
  minutes_wc2026: 450,
  xG: 2.5,                        // expected goals
  xA: 5.3,                        // expected assists
  key_passes: 32,
  dribbles_completed: 28,
  aerial_wins_pct: 22,            // 0-100
  tackles_won: 10,

  // Scout metrics (0-100)
  sprint_speed: 91,
  pressing_intensity: 77,

  style_tags: ["creative", "dribbler", "wide forward", "direct"],
  bio: "Generational teenage talent..."
}
```

### `scout_reports` collection
```javascript
{
  player_name: "Lamine Yamal",
  report: {
    summary: "...",
    strengths: ["...", "..."],
    weaknesses: ["..."],
    tactical_fit: "...",
    recommendation: "Sign immediately",  // or Monitor closely | Pass | Loan candidate
    scout_rating: 9.2
  },
  created_at: ISODate("2026-06-10T..."),
  version: 1
}
```

---

## 🎬 Demo Scenarios

These 3 scenarios demonstrate the multi-step agent reasoning for judges:

**1. Semantic player search**
> *"Find me explosive wingers who can track back defensively"*

Agent: queries style_tags → filters by position + pressing_intensity → ranks by dribbles + sprint_speed → explains 5 results with stats

**2. Lineup builder**
> *"Build me the best possible 4-3-3 from all players at this World Cup"*

Agent: queries GK, CBs, FBs, DMs, CMs, wingers, and ST separately → reasons about balance → outputs a formation with tactical explanation

**3. Scout report with write-back**
> *"Generate a full scouting report for Jude Bellingham"*

Agent: fetches Bellingham's stats → runs percentile aggregation across all midfielders → writes structured report to MongoDB → confirms saved

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| AI Model | Claude Sonnet 4 (via Anthropic API) |
| Orchestration | Google Cloud Agent Builder |
| Database | MongoDB 7.0 / Atlas |
| MCP Integration | MongoDB MCP Server (4 tools) |
| Backend | Node.js 20, Express, MongoDB Node driver |
| Frontend | Vanilla HTML/CSS/JS (no framework — zero build step) |
| Deployment | Google Cloud Run + Docker |

---

## 📁 Project Structure

```
scoutiq/
├── backend/
│   ├── server.js          # Express server + agentic loop + MCP tools
│   ├── package.json
│   └── Dockerfile
├── frontend/
│   └── index.html         # Full SPA — chat, leaderboard, player DB, reports
├── data/
│   └── players.json       # 50+ World Cup 2026 player dataset
├── scripts/
│   ├── setup-atlas.mjs    # Atlas seeding + index creation
│   └── deploy-gcp.sh      # Cloud Run deployment
├── docker-compose.yml
├── nginx.conf
├── .env.example
└── README.md
```

---

## 📜 License

MIT — see [LICENSE](LICENSE)

---

*Built for the Google Cloud Rapid Agent Hackathon 2026 · MongoDB Partner Track*
