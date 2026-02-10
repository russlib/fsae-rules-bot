"""
FSAE Rules Discord Bot
Searches FSAE 2026 rulebook and answers questions using Gemini Flash.

Usage:
  /rule <question>  - Ask about any FSAE rule
  /rulesearch <term> - Raw keyword search, returns matching lines

Requires:
  DISCORD_BOT_TOKEN  - Discord bot token
  GOOGLE_API_KEY     - Gemini API key
"""

import os
import re
import discord
from discord import app_commands
from google import genai

# Load .env file if present
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))

# --- Config ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(SCRIPT_DIR, "FSAE_Rules_2026_V1.md")

DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

# --- Load rules into memory ---
def load_rules(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

RULES_TEXT = load_rules(RULES_PATH)
RULES_LINES = RULES_TEXT.splitlines()

# --- Section index for fast lookup ---
# Maps section codes like "EV.5" to (start_line, end_line) in RULES_LINES
SECTION_INDEX = {}

def build_section_index():
    """Build an index of section codes to line ranges."""
    # Match heading lines: ## EV.5 ENERGY STORAGE or raw lines like EV.5.3.1
    heading_pat = re.compile(r'^#{1,4}\s+([A-Z]{1,2}\.\d{1,2}(?:\.\d{1,2})*)\s')

    sections = []  # (line_num, code)
    for i, line in enumerate(RULES_LINES):
        m = heading_pat.match(line)
        if m:
            sections.append((i, m.group(1)))

    # Set end of each section to start of next
    for idx, (start, code) in enumerate(sections):
        end = sections[idx + 1][0] if idx + 1 < len(sections) else len(RULES_LINES)
        SECTION_INDEX[code] = (start, end)

build_section_index()

# --- Search functions ---
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "of", "in", "to",
    "for", "with", "on", "at", "from", "by", "about", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out", "off",
    "up", "down", "and", "but", "or", "nor", "not", "no", "so", "if", "then",
    "than", "too", "very", "just", "that", "this", "these", "those", "it",
    "its", "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
    "them", "what", "which", "who", "whom", "how", "when", "where", "why",
    "all", "each", "every", "any", "few", "more", "most", "some", "such",
    "only", "own", "same", "other", "there", "here", "also", "need", "go",
    "get", "many", "much", "make",
}


def extract_keywords(query):
    """Extract meaningful keywords from a query, filtering stop words."""
    words = re.findall(r'[a-z0-9]+', query.lower())
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    return keywords if keywords else words  # fallback to all words if everything filtered


def keyword_search(query, context_lines=3, max_results=15):
    """Search rules by keywords. Returns list of (line_num, text) tuples."""
    keywords = extract_keywords(query)
    results = []
    seen_ranges = set()

    for i, line in enumerate(RULES_LINES):
        lower = line.lower()
        if all(w in lower for w in keywords):
            # Avoid overlapping results
            range_key = i // (context_lines * 2)
            if range_key in seen_ranges:
                continue
            seen_ranges.add(range_key)

            start = max(0, i - context_lines)
            end = min(len(RULES_LINES), i + context_lines + 1)
            chunk = "\n".join(RULES_LINES[start:end])
            results.append((i + 1, chunk))

            if len(results) >= max_results:
                break

    return results


def find_relevant_sections(query, max_sections=5):
    """Find the most relevant sections for a query using keyword matching."""
    keywords = extract_keywords(query)

    # Score each section by keyword hits (only meaningful words)
    scores = {}
    for code, (start, end) in SECTION_INDEX.items():
        section_text = "\n".join(RULES_LINES[start:end]).lower()
        score = sum(section_text.count(w) for w in keywords)
        if score > 0:
            scores[code] = score

    # Sort by score descending, return top N
    top = sorted(scores.items(), key=lambda x: -x[1])[:max_sections]

    # Collect the text
    chunks = []
    for code, score in top:
        start, end = SECTION_INDEX[code]
        text = "\n".join(RULES_LINES[start:end])
        chunks.append(text)

    return chunks


# --- Gemini client ---
client = genai.Client(api_key=GOOGLE_API_KEY)

SYSTEM_PROMPT = """You are an FSAE Rules expert bot. You answer questions about the Formula SAE 2026 Rules.

Rules:
- Always cite the specific rule number (e.g., EV.5.3.1, F.10.2.3)
- Quote the exact rule text when relevant
- Be concise — Discord has a 2000 char limit
- If the provided context doesn't contain the answer, say so
- If a rule references another rule, mention the cross-reference"""


async def ask_gemini(question, context_chunks):
    """Send question + relevant rule sections to Gemini Flash."""
    context = "\n\n---\n\n".join(context_chunks)

    # Trim context if too long (keep under ~30k chars for speed)
    if len(context) > 30000:
        context = context[:30000] + "\n\n[...truncated]"

    prompt = f"""Based on the following FSAE 2026 Rules sections, answer this question:

**Question:** {question}

**Rules Context:**
{context}"""

    response = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=1800,
        ),
    )

    return response.text


# --- Discord bot ---
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


@tree.command(name="rule", description="Ask a question about FSAE 2026 rules")
@app_commands.describe(question="Your question about FSAE rules")
async def rule_command(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)

    try:
        # Find relevant sections
        chunks = find_relevant_sections(question)

        if not chunks:
            # Fallback: try broader search
            results = keyword_search(question, context_lines=5, max_results=5)
            chunks = [text for _, text in results]

        if not chunks:
            await interaction.followup.send(
                f"No matching rules found for: **{question}**\n"
                "Try rephrasing or using specific terms like 'battery container', 'restrictor', 'endurance'."
            )
            return

        answer = await ask_gemini(question, chunks)

        # Discord 2000 char limit
        if len(answer) > 1950:
            answer = answer[:1950] + "\n\n*[truncated]*"

        await interaction.followup.send(f"**Q:** {question}\n\n{answer}")

    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


@tree.command(name="rulesearch", description="Search FSAE rules by keyword")
@app_commands.describe(term="Keywords to search for")
async def search_command(interaction: discord.Interaction, term: str):
    await interaction.response.defer(thinking=True)

    results = keyword_search(term, context_lines=1, max_results=8)

    if not results:
        await interaction.followup.send(f"No results for: **{term}**")
        return

    output = f"**Search: {term}** ({len(results)} results)\n\n"
    for line_num, text in results:
        # Clean up for Discord
        clean = text.strip().replace("[[#", "").replace("]]", "")
        entry = f"**Line {line_num}:**\n```\n{clean}\n```\n"
        if len(output) + len(entry) > 1900:
            output += "*[more results truncated]*"
            break
        output += entry

    await interaction.followup.send(output)


@bot.event
async def on_ready():
    await tree.sync()
    print(f"FSAE Rules Bot online as {bot.user}")
    print(f"Loaded {len(RULES_LINES)} lines, {len(SECTION_INDEX)} sections indexed")


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: Set DISCORD_BOT_TOKEN environment variable")
        print("  1. Go to https://discord.com/developers/applications")
        print("  2. Create a new application -> Bot -> Copy token")
        print("  3. export DISCORD_BOT_TOKEN='your-token-here'")
        exit(1)

    if not GOOGLE_API_KEY:
        print("ERROR: Set GOOGLE_API_KEY environment variable")
        exit(1)

    print(f"Rules file: {RULES_PATH}")
    print(f"Sections indexed: {len(SECTION_INDEX)}")
    bot.run(DISCORD_TOKEN)
