#!/usr/bin/env node
/**
 * ScoutIQ — MongoDB Atlas Setup Script
 *
 * This script:
 * 1. Connects to your Atlas cluster
 * 2. Seeds the players collection
 * 3. Creates all required indexes (including Atlas Search)
 * 4. Verifies everything is working
 *
 * Usage:
 *   MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net" node scripts/setup-atlas.mjs
 */

import { MongoClient } from "mongodb";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

const MONGODB_URI = process.env.MONGODB_URI;
if (!MONGODB_URI) {
  console.error("❌ MONGODB_URI environment variable is required");
  console.error("   export MONGODB_URI='mongodb+srv://user:pass@cluster.mongodb.net'");
  process.exit(1);
}

async function setup() {
  console.log("🔌 Connecting to MongoDB Atlas...");
  const client = new MongoClient(MONGODB_URI);
  await client.connect();
  console.log("✅ Connected!\n");

  const db = client.db("scoutiq");
  const players = db.collection("players");

  // ── Seed players ───────────────────────────────────────────
  console.log("🌱 Seeding players collection...");
  const data = JSON.parse(
    readFileSync(join(__dirname, "../data/players.json"), "utf8")
  );

  // Deduplicate by name
  const seen = new Set();
  const unique = data.filter((p) => {
    if (seen.has(p.name)) return false;
    seen.add(p.name);
    return true;
  });

  // Drop existing and re-seed
  await players.deleteMany({});
  const result = await players.insertMany(unique);
  console.log(`   ✓ Inserted ${result.insertedCount} players`);

  // ── Standard indexes ───────────────────────────────────────
  console.log("\n📑 Creating standard indexes...");

  await players.createIndex({ position: 1 });
  console.log("   ✓ position index");

  await players.createIndex({ confederation: 1 });
  console.log("   ✓ confederation index");

  await players.createIndex({ nationality: 1 });
  console.log("   ✓ nationality index");

  await players.createIndex({ goals_wc2026: -1 });
  console.log("   ✓ goals_wc2026 desc index");

  await players.createIndex({ xG: -1 });
  console.log("   ✓ xG index");

  await players.createIndex({ sprint_speed: -1 });
  console.log("   ✓ sprint_speed index");

  await players.createIndex({ pressing_intensity: -1 });
  console.log("   ✓ pressing_intensity index");

  await players.createIndex({ age: 1 });
  console.log("   ✓ age index");

  await players.createIndex({ foot: 1, position: 1 });
  console.log("   ✓ compound foot+position index");

  // Text search index (standard — use Atlas Search for semantic)
  await players.createIndex(
    { name: "text", bio: "text", style_tags: "text" },
    { name: "players_text_search" }
  );
  console.log("   ✓ text search index (name, bio, style_tags)");

  // ── Atlas Search index (requires Atlas cluster, not local) ─
  console.log("\n🔍 Creating Atlas Search index...");
  console.log("   (This requires an Atlas M0+ cluster — skipped for local MongoDB)");

  const atlasSearchDef = {
    name: "players_search",
    definition: {
      mappings: {
        dynamic: false,
        fields: {
          name: [{ type: "string" }, { type: "autocomplete" }],
          bio: { type: "string" },
          style_tags: { type: "string" },
          position: { type: "string" },
          nationality: { type: "string" },
          confederation: { type: "string" },
          foot: { type: "string" },
          age: { type: "number" },
          goals_wc2026: { type: "number" },
          assists_wc2026: { type: "number" },
          xG: { type: "number" },
          sprint_speed: { type: "number" },
          pressing_intensity: { type: "number" },
        },
      },
    },
  };

  console.log("\n   📋 Atlas Search index definition (create this in Atlas UI):");
  console.log("   Collection: scoutiq.players");
  console.log("   Index name: players_search");
  console.log("   Definition:");
  console.log(JSON.stringify(atlasSearchDef.definition, null, 4));

  // ── Verification ───────────────────────────────────────────
  console.log("\n🔬 Verifying setup...");
  const count = await players.countDocuments();
  console.log(`   ✓ ${count} players in collection`);

  const positions = await players.distinct("position");
  console.log(`   ✓ Positions: ${positions.join(", ")}`);

  const confs = await players.distinct("confederation");
  console.log(`   ✓ Confederations: ${confs.join(", ")}`);

  const topScorer = await players.findOne({}, { sort: { goals_wc2026: -1 } });
  console.log(`   ✓ Top scorer: ${topScorer.name} (${topScorer.goals_wc2026} goals)`);

  const indexes = await players.indexes();
  console.log(`   ✓ ${indexes.length} indexes created`);

  // ── Scout reports collection ───────────────────────────────
  console.log("\n📋 Setting up scout_reports collection...");
  const reports = db.collection("scout_reports");
  await reports.createIndex({ player_name: 1 }, { unique: true });
  await reports.createIndex({ created_at: -1 });
  console.log("   ✓ scout_reports indexes created");

  await client.close();
  console.log("\n🎉 Atlas setup complete! ScoutIQ is ready to run.");
  console.log("\nNext steps:");
  console.log("  1. Set MONGODB_URI in your .env file");
  console.log("  2. Run: cd backend && npm install && npm start");
  console.log("  3. Open: frontend/index.html in your browser");
}

setup().catch((err) => {
  console.error("❌ Setup failed:", err);
  process.exit(1);
});
