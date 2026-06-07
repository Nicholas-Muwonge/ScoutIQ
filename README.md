# ScoutIQ - An AI Football Scout for World Cup 2026

  ## What is ScoutIQ?

ScoutIQ is an **AI-powered football scouting agent** that goes far beyond answering questions to *thinking*, *quering a live database* and *taking action* on your behalf.

Ask it to:
- **Find players** by any combination of attributes: *"Left-footed strikers under 24 who press hard"*
- **Build lineups**: *"Give me a 4-3-3 optimized to beat a low block"*
- **Compare players**: *"Mbappé vs Haaland at this World Cup - who would you sign?"*
- **Generate & save scout reports**: *"Give me a full scouting report for Lamine Yamal"* - the report is written to MongoDB automatically

---

## Architecture

```
User (Natural Language)
        │
        ▼
 Google Cloud Agent Builder
    + Gemini 
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
##  Quick Start (Local)

### Prerequisites
- Node.js 20+
- MongoDB or MongoDB Atlas account
- Gemini API key

### 1. Clone & install
```bash
git clone https://github.com/.../scoutiq
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

## Docker (Full Stack)

```bash
# Start everything (MongoDB + backend + frontend)
docker-compose up --build

# Open http://localhost:8080
```

---

## Deploy to Google Cloud Run

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


## Tech Stack

| Layer | Technology |
|---|---|
| AI Model | Claude Sonnet 4 (via Anthropic API) |
| Orchestration | Google Cloud Agent Builder |
| Database | MongoDB 7.0 / Atlas |
| MCP Integration | MongoDB MCP Server (4 tools) |
| Backend | Node.js 20, Express, MongoDB Node driver |
| Frontend | Vanilla HTML/CSS/JS  |
| Deployment | Google Cloud Run + Docker |


## Project Structure

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


