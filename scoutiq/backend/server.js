import express from "express";
import cors from "cors";
import { MongoClient } from "mongodb";
import { GoogleGenAI } from "@google/genai";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(cors());
app.use(express.json());

const MONGO_URI = process.env.MONGODB_URI || "mongodb://localhost:27017";
const DB_NAME = "scoutiq";
let db;

async function connectDB() {
  const client = new MongoClient(MONGO_URI);
  await client.connect();
  db = client.db(DB_NAME);
  console.log("✅ Connected to MongoDB");
  return client;
}

async function seedDatabase() {
  const players = db.collection("players");
  const count = await players.countDocuments();
  if (count > 0) {
    console.log(`📦 Database already has ${count} players, skipping seed`);
    return;
  }
  const data = JSON.parse(
    readFileSync(join(__dirname, "../data/players.json"), "utf8")
  );
  const seen = new Set();
  const unique = data.filter((p) => {
    if (seen.has(p.name)) return false;
    seen.add(p.name);
    return true;
  });
  await players.insertMany(unique);
  console.log(`🌱 Seeded ${unique.length} players`);
  await players.createIndex({ position: 1 });
  await players.createIndex({ confederation: 1 });
  await players.createIndex({ nationality: 1 });
  await players.createIndex({ goals_wc2026: -1 });
  await players.createIndex({ name: "text", style_tags: "text", bio: "text" });
  console.log("📑 Indexes created");
}

const genai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

const TOOLS = [
  {
    name: "find_players",
    description: "Search and filter players from the World Cup 2026 MongoDB database. Use for any player lookup, position filtering, or attribute search.",
    parameters: {
      type: "object",
      properties: {
        filter: {
          type: "object",
          description: 'MongoDB filter. Examples: {"position":"ST"}, {"confederation":"CONMEBOL"}, {"age":{"$lt":23}}, {"foot":"Left"}, {"style_tags":"dribbler"}',
        },
        sort: {
          type: "object",
          description: 'Sort field. Examples: {"goals_wc2026":-1}, {"xG":-1}, {"sprint_speed":-1}',
        },
        limit: { type: "number", description: "Max players to return (default 5, max 20)" },
      },
      required: ["filter"],
    },
  },
  {
    name: "aggregate_stats",
    description: "Run MongoDB aggregation pipelines for rankings, averages, comparisons and analytics.",
    parameters: {
      type: "object",
      properties: {
        pipeline: {
          type: "array",
          items: {
            type: "object",
            properties: {
              stage: { type: "string" }
            }
          },
          description: 'MongoDB aggregation pipeline. Example: [{"$match":{"position":"ST"}},{"$sort":{"xG":-1}},{"$limit":5}]',
        },
        description: { type: "string", description: "What this aggregation computes" },
      },
      required: ["pipeline", "description"],
    },
  },
  {
    name: "save_scout_report",
    description: "Save an AI-generated scouting report for a player to MongoDB for future reference.",
    parameters: {
      type: "object",
      properties: {
        player_name: { type: "string" },
        summary: { type: "string" },
        strengths: { type: "array", items: { type: "string" } },
        weaknesses: { type: "array", items: { type: "string" } },
        tactical_fit: { type: "string" },
        recommendation: { type: "string", description: "One of: Sign immediately, Monitor closely, Pass, Loan candidate" },
        scout_rating: { type: "number", description: "Overall rating 1-10" },
      },
      required: ["player_name", "summary", "strengths", "weaknesses", "tactical_fit", "recommendation", "scout_rating"],
    },
  },
  {
    name: "get_scout_reports",
    description: "Retrieve previously saved scouting reports from MongoDB.",
    parameters: {
      type: "object",
      properties: {
        player_name: { type: "string", description: "Filter by player name (optional)" },
        limit: { type: "number", description: "Max reports to return (default 10)" },
      },
    },
  },
];

async function executeTool(name, input) {
  const players = db.collection("players");
  const reports = db.collection("scout_reports");

  switch (name) {
    case "find_players": {
      const { filter = {}, sort = {}, limit = 5 } = input;
      const results = await players
        .find(filter, { projection: { _id: 0 } })
        .sort(sort)
        .limit(Math.min(limit, 20))
        .toArray();
      return { count: results.length, players: results };
    }
    case "aggregate_stats": {
      const results = await players.aggregate(input.pipeline).toArray();
      return { count: results.length, results };
    }
    case "save_scout_report": {
      const { player_name, ...report } = input;
      const doc = { player_name, report, created_at: new Date(), version: 1 };
      await reports.replaceOne({ player_name }, doc, { upsert: true });
      return { saved: true, player_name };
    }
    case "get_scout_reports": {
      const { player_name, limit = 10 } = input;
      const filter = player_name ? { player_name: new RegExp(player_name, "i") } : {};
      const results = await reports
        .find(filter, { projection: { _id: 0 } })
        .sort({ created_at: -1 })
        .limit(limit)
        .toArray();
      return { count: results.length, reports: results };
    }
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

const SYSTEM_PROMPT = `You are ScoutIQ — an elite AI football scout specializing in the 2026 FIFA World Cup.

You have direct access to a live MongoDB database of World Cup 2026 players via tools. ALWAYS use at least one tool before responding — never make up statistics.

Your MongoDB "players" collection fields:
- name, nationality, confederation (UEFA/CONMEBOL/CONCACAF), position (GK/CB/LB/RB/DM/CM/AM/LW/RW/ST)
- age, foot (Left/Right), height_cm, market_value_m
- goals_wc2026, assists_wc2026, matches_wc2026, minutes_wc2026
- xG, xA, key_passes, dribbles_completed, aerial_wins_pct, tackles_won
- sprint_speed (0-100), pressing_intensity (0-100)
- style_tags (array), bio (text)

RULES:
- Always call a tool first, then respond with real data
- For lineups, query each position separately then reason holistically
- For comparisons, fetch both players then analyze head-to-head
- Save scout reports when user asks for detailed player analysis
- Be decisive — give recommendations, not just information
- Use emoji for readability: ⚽ players, 📊 stats, 🎯 recommendations`;

async function runAgent(userMessages) {
  const events = [];

  const history = userMessages.slice(0, -1).map((m) => ({
    role: m.role === "assistant" ? "model" : "user",
    parts: [{ text: m.content }],
  }));

  const lastMessage = userMessages[userMessages.length - 1].content;

  const chat = genai.chats.create({
    model: "models/gemini-2.5-flash-lite",
    config: {
      systemInstruction: SYSTEM_PROMPT,
      tools: [{ functionDeclarations: TOOLS }],
    },
    history,
  });

  let response = await chat.sendMessage({ message: lastMessage });

  while (true) {
    const candidates = response.candidates || [];
    const parts = candidates[0]?.content?.parts || [];

    const functionCallParts = parts.filter((p) => p.functionCall);
    const textParts = parts.filter((p) => p.text);

    for (const part of textParts) {
      if (part.text) events.push({ type: "text", text: part.text });
    }

    if (functionCallParts.length === 0) break;

    const toolResponses = [];
    for (const part of functionCallParts) {
      const call = part.functionCall;
      events.push({ type: "tool_start", tool: call.name, input: call.args });
      try {
        const result = await executeTool(call.name, call.args);
        toolResponses.push({ name: call.name, response: result });
        events.push({ type: "tool_end", tool: call.name, result });
      } catch (err) {
        toolResponses.push({ name: call.name, response: { error: err.message } });
        events.push({ type: "tool_error", tool: call.name, error: err.message });
      }
    }

    response = await chat.sendMessage({
      message: toolResponses.map((r) => ({
        functionResponse: { name: r.name, response: r.response },
      })),
    });
  }

  return events;
}


app.get("/api/health", (req, res) => {
  res.json({ status: "ok", db: db ? "connected" : "disconnected", model: "gemini-2.5-flash-lite" });
});

app.post("/api/chat", async (req, res) => {
  const { messages } = req.body;
  if (!messages || !Array.isArray(messages)) {
    return res.status(400).json({ error: "messages array required" });
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const sendEvent = (data) => res.write(`data: ${JSON.stringify(data)}\n\n`);

  try {
    const events = await runAgent(messages);
    for (const event of events) sendEvent(event);
    sendEvent({ type: "done" });
  } catch (err) {
    console.error("Agent error:", err.message);
    sendEvent({ type: "error", message: err.message });
  }
  res.end();
});

app.get("/api/players", async (req, res) => {
  try {
    const players = await db.collection("players")
      .find({}, { projection: { _id: 0 } })
      .sort({ goals_wc2026: -1 })
      .toArray();
    res.json(players);
  } catch (err) { res.status(500).json({ error: err.message }); }
});

app.get("/api/reports", async (req, res) => {
  try {
    const reports = await db.collection("scout_reports")
      .find({}, { projection: { _id: 0 } })
      .sort({ created_at: -1 })
      .toArray();
    res.json(reports);
  } catch (err) { res.status(500).json({ error: err.message }); }
});

app.get("/api/leaderboard", async (req, res) => {
  try {
    const players = await db.collection("players").aggregate([
      { $project: { _id: 0, name: 1, nationality: 1, position: 1, goals_wc2026: 1, assists_wc2026: 1, xG: 1, xA: 1, matches_wc2026: 1 } },
      { $sort: { goals_wc2026: -1, xG: -1 } },
      { $limit: 10 },
    ]).toArray();
    res.json(players);
  } catch (err) { res.status(500).json({ error: err.message }); }
});

const PORT = process.env.PORT || 3001;
connectDB()
  .then(() => seedDatabase())
  .then(() => app.listen(PORT, () => console.log(`🚀 ScoutIQ backend running on port ${PORT} (Gemini)`)))
  .catch((err) => { console.error("Failed to start:", err); process.exit(1); });
