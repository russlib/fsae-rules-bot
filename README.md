# FSAE Rules Discord Bot

Discord bot that answers FSAE 2026 rules questions using keyword search + Gemini Flash.

## Status: Built, needs Discord token to deploy

## Commands

| Command | Description |
|---------|-------------|
| `/rule <question>` | Ask a natural language question — bot finds relevant sections, sends to Gemini Flash, returns answer with rule citations |
| `/rulesearch <term>` | Raw keyword search — returns matching lines from the rulebook |

## How it works

1. On `/rule`, bot searches the extracted `FSAE_Rules_2026_V1.md` for relevant sections by keyword
2. Sends matched sections + question to Gemini 2.0 Flash
3. Gemini returns a concise answer with rule number citations
4. Bot posts to Discord (respects 2000 char limit)

## Setup

```bash
# 1. Create Discord bot at https://discord.com/developers/applications
#    - New Application -> Bot -> Reset Token -> Copy
#    - OAuth2 -> URL Generator -> bot + applications.commands -> Send Messages
#    - Use generated URL to invite bot to your server

# 2. Set environment variables
export DISCORD_BOT_TOKEN='your-token-here'
export GOOGLE_API_KEY='your-key-here'   # already set on HomePC

# 3. Install deps
pip install "discord.py>=2.3" google-genai

# 4. Run
python bot.py
```

## Architecture

- **Rules source:** `MegaVault/Areas/FSAE/FSAE_Rules_2026_V1.md` (6,898 lines)
- **Section index:** Built on startup — maps rule codes (EV.5, F.10, etc.) to line ranges
- **Search:** Keyword scoring per section, top 5 sent to Gemini
- **LLM:** Gemini 2.0 Flash (free tier: 15 RPM, 1M tokens/min)
- **Cost:** ~$0.01 per 100 queries

## Next steps

- [ ] Get Discord bot token and deploy
- [ ] Test with team members
- [ ] Consider hosting on a free VM (Railway, Render) for 24/7 uptime
