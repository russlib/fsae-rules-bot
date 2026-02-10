# FSAE Rules Discord Bot

Discord bot that answers FSAE 2026 rules questions using keyword search + Gemini Flash.

## Status: Built, needs Discord token to deploy

## Commands

| Command | Description |
|---------|-------------|
| `/rule <question>` | Ask a natural language question — bot finds relevant sections, sends to Gemini Flash, returns answer with rule citations |
| `/rulesearch <term>` | Raw keyword search — returns matching lines from the rulebook |

## Features

### 🔤 Fuzzy Matching for Typos
Automatically corrects common typos:
- `battrey` → `battery`
- `restrctor` → `restrictor`
- `chasis` → `chassis`

Shows corrections in the response so you know what was searched.

### 🔍 Query Expansion via Gemini
Before searching, asks Gemini to suggest FSAE-specific terminology:
- "battery box" → also searches "tractive system", "accumulator", "container"
- "kill switch" → also searches "shutdown circuit", "GLVMS", "cockpit switch"

This helps find relevant rules even when your wording differs from the rulebook.

### 📚 "Also Check" Suggestions
Every answer includes related rule sections you might want to review:
```
**Also check:** F.10.4 (Holes and Openings), EV.6.1 (Covers), T.8.2 (Critical Fasteners)
```

## How it works

1. Extract keywords from your question
2. Fuzzy-correct any typos against the rulebook vocabulary
3. Expand query with FSAE terminology via Gemini
4. Score and retrieve top 5 relevant rule sections
5. Send to Gemini Flash for answer synthesis with citations
6. Return answer + "Also check" suggestions

## Setup

```bash
# 1. Create Discord bot at https://discord.com/developers/applications
#    - New Application -> Bot -> Reset Token -> Copy
#    - OAuth2 -> URL Generator -> bot + applications.commands -> Send Messages
#    - Use generated URL to invite bot to your server

# 2. Set environment variables
export DISCORD_BOT_TOKEN='your-token-here'
export GOOGLE_API_KEY='your-key-here'

# 3. Install deps
pip install "discord.py>=2.3" google-genai rapidfuzz

# 4. Run
python bot.py
```

## Architecture

- **Rules source:** `FSAE_Rules_2026_V1.md` (6,898 lines)
- **Section index:** Built on startup — maps rule codes (EV.5, F.10, etc.) to line ranges
- **Vocabulary:** ~3,000 unique words extracted for fuzzy matching
- **Search:** Keyword scoring per section, top 5 sent to Gemini
- **LLM:** Gemini 2.0 Flash Lite
- **Cost:** ~$0.01 per 100 queries

## Dependencies

- `discord.py>=2.3` — Discord API
- `google-genai` — Gemini API client
- `rapidfuzz` — Fast fuzzy string matching
