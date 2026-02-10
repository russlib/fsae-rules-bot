"""
FSAE Rules Discord Bot
Searches FSAE 2026 rulebook and answers questions using Gemini Flash.

Usage:
  /rule <question>  - Ask about any FSAE rule
  /rulesearch <term> - Raw keyword search, returns matching lines

Requires:
  DISCORD_BOT_TOKEN  - Discord bot token
  GOOGLE_API_KEY     - Gemini API key

Features:
  - Fuzzy matching for typos (rapidfuzz)
  - Query expansion via Gemini for better terminology matching
  - "Also check" suggestions for related rules
"""

import os
import re
import discord
from discord import app_commands
from google import genai
from rapidfuzz import fuzz, process

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
    heading_pat = re.compile(r'^#{1,4}\s+([A-Z]{1,2}\.\d{1,2}(?:\.\d{1,2})*)\s')

    sections = []
    for i, line in enumerate(RULES_LINES):
        m = heading_pat.match(line)
        if m:
            sections.append((i, m.group(1)))

    for idx, (start, code) in enumerate(sections):
        end = sections[idx + 1][0] if idx + 1 < len(sections) else len(RULES_LINES)
        SECTION_INDEX[code] = (start, end)

build_section_index()

# --- Build vocabulary for fuzzy matching ---
def build_vocabulary():
    """Extract unique meaningful words from the rulebook for fuzzy matching."""
    words = set()
    for line in RULES_LINES:
        # Extract words (letters and numbers)
        found = re.findall(r'[a-zA-Z]{3,}', line)
        words.update(w.lower() for w in found)
    return list(words)

VOCABULARY = build_vocabulary()
print(f"Vocabulary size: {len(VOCABULARY)} unique words")

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
    return keywords if keywords else words


def fuzzy_correct_keyword(word, threshold=80):
    """
    Find the best matching word in vocabulary using fuzzy matching.
    Returns the corrected word if a good match is found, otherwise original.
    """
    if word in VOCABULARY:
        return word  # Exact match
    
    # Find best fuzzy match
    result = process.extractOne(word, VOCABULARY, scorer=fuzz.ratio)
    if result and result[1] >= threshold:
        return result[0]
    return word


def extract_keywords_fuzzy(query):
    """Extract keywords with fuzzy correction for typos."""
    raw_keywords = extract_keywords(query)
    corrected = []
    corrections = {}
    
    for word in raw_keywords:
        corrected_word = fuzzy_correct_keyword(word)
        corrected.append(corrected_word)
        if corrected_word != word:
            corrections[word] = corrected_word
    
    return corrected, corrections


def keyword_search(query, context_lines=3, max_results=15, use_fuzzy=True):
    """Search rules by keywords. Returns list of (line_num, text) tuples."""
    if use_fuzzy:
        keywords, _ = extract_keywords_fuzzy(query)
    else:
        keywords = extract_keywords(query)
    
    results = []
    seen_ranges = set()

    for i, line in enumerate(RULES_LINES):
        lower = line.lower()
        if all(w in lower for w in keywords):
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


def find_relevant_sections(keywords, max_sections=5):
    """Find the most relevant sections for given keywords."""
    scores = {}
    for code, (start, end) in SECTION_INDEX.items():
        section_text = "\n".join(RULES_LINES[start:end]).lower()
        score = sum(section_text.count(w) for w in keywords)
        if score > 0:
            scores[code] = score

    top = sorted(scores.items(), key=lambda x: -x[1])[:max_sections]

    chunks = []
    codes = []
    for code, score in top:
        start, end = SECTION_INDEX[code]
        text = "\n".join(RULES_LINES[start:end])
        chunks.append(text)
        codes.append(code)

    return chunks, codes


# --- Gemini client ---
client = genai.Client(api_key=GOOGLE_API_KEY)

SYSTEM_PROMPT = """You are an FSAE Rules expert bot. You answer questions about the Formula SAE 2026 Rules.

Rules:
- Always cite the specific rule number (e.g., EV.5.3.1, F.10.2.3)
- Quote the exact rule text when relevant
- Be concise — Discord has a 2000 char limit
- If there's no explicit rule with a specific number/limit, explain what implicit constraints exist (e.g., "There's no max width specified, but aero must be within tire width per T.7.6")
- If the context genuinely doesn't help, say so and suggest what terms to search
- If a rule references another rule, mention the cross-reference

At the end, add a **Follow-up** section with 1-3 copyable prompts for related rules:
```
**Follow-up prompts:**
• `/rule What is T.7.6?`
• `/rule What are the chassis tube requirements?`
```
Only suggest follow-ups that would genuinely help understand the topic better."""


async def expand_query(question):
    """Use Gemini to expand the query with FSAE-specific terminology."""
    import asyncio
    
    expansion_prompt = f"""Given this question about FSAE (Formula SAE) rules, suggest 3-5 specific technical terms 
that would appear in the official FSAE rulebook. Return ONLY the terms, comma-separated, no explanation.

Common FSAE terminology includes: Tractive System, Accumulator, GLV (Grounded Low Voltage), 
TSAL (Tractive System Active Light), IMD (Insulation Monitoring Device), HVD (High Voltage Disconnect),
BSPD (Brake System Plausibility Device), Primary Structure, Major Structure, SES (Structural Equivalency Spreadsheet),
Critical Fastener, Firewall, Attenuator, etc.

Question: {question}

Terms:"""

    def sync_call():
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=expansion_prompt,
            config=genai.types.GenerateContentConfig(
                max_output_tokens=100,
            ),
        )
        terms = [t.strip().lower() for t in response.text.split(",")]
        return [t for t in terms if len(t) > 2][:5]

    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_call)
    except Exception:
        return []


async def ask_gemini(question, context_chunks):
    """Send question + relevant rule sections to Gemini Flash."""
    import asyncio
    
    context = "\n\n---\n\n".join(context_chunks)

    if len(context) > 30000:
        context = context[:30000] + "\n\n[...truncated]"

    prompt = f"""Based on the following FSAE 2026 Rules sections, answer this question:

**Question:** {question}

**Rules Context:**
{context}"""

    # Run sync Gemini call in thread pool to not block event loop
    def sync_call():
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1800,
            ),
        )
        return response.text
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_call)


# --- Discord bot ---
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


@tree.command(name="rule", description="Ask a question about FSAE 2026 rules")
@app_commands.describe(question="Your question about FSAE rules")
async def rule_command(interaction: discord.Interaction, question: str):
    print(f"[RULE] Received question: {question}", flush=True)
    await interaction.response.defer(thinking=True)
    print(f"[RULE] Deferred response", flush=True)

    try:
        print(f"[RULE] Starting processing...", flush=True)
        # Step 1: Extract keywords with fuzzy correction
        keywords, corrections = extract_keywords_fuzzy(question)
        print(f"[RULE] Keywords: {keywords}", flush=True)
        
        # Step 2: Expand query with FSAE terminology
        print(f"[RULE] Expanding query...", flush=True)
        expanded_terms = await expand_query(question)
        print(f"[RULE] Expanded terms: {expanded_terms}", flush=True)
        all_keywords = list(set(keywords + expanded_terms))
        
        # Step 3: Find relevant sections
        print(f"[RULE] Finding sections...", flush=True)
        chunks, codes = find_relevant_sections(all_keywords)
        print(f"[RULE] Found {len(chunks)} chunks", flush=True)

        if not chunks:
            # Fallback: try broader search with just fuzzy-corrected keywords
            results = keyword_search(question, context_lines=5, max_results=5)
            chunks = [text for _, text in results]
            codes = []

        if not chunks:
            # Build helpful error message
            correction_note = ""
            if corrections:
                fixes = [f"'{k}' → '{v}'" for k, v in corrections.items()]
                correction_note = f"\n(Typo corrections attempted: {', '.join(fixes)})"
            
            await interaction.followup.send(
                f"No matching rules found for: **{question}**{correction_note}\n"
                "Try rephrasing or using specific terms like 'tractive system', 'accumulator', 'GLV', 'TSAL'."
            )
            return

        # Step 4: Get answer from Gemini (includes "Also check" suggestions)
        print(f"[RULE] Calling Gemini...", flush=True)
        answer = await ask_gemini(question, chunks)
        print(f"[RULE] Got answer: {len(answer)} chars", flush=True)

        # Build response with metadata
        response_parts = []
        
        # Show typo corrections if any
        if corrections:
            fixes = [f"`{k}` → `{v}`" for k, v in corrections.items()]
            response_parts.append(f"📝 *Corrected: {', '.join(fixes)}*")
        
        # Show expanded terms if any
        if expanded_terms:
            response_parts.append(f"🔍 *Also searched: {', '.join(expanded_terms)}*")
        
        response_parts.append(f"**Q:** {question}\n")
        response_parts.append(answer)
        
        full_response = "\n".join(response_parts)

        # Discord 2000 char limit
        if len(full_response) > 1950:
            full_response = full_response[:1950] + "\n\n*[truncated]*"

        await interaction.followup.send(full_response)

    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


@tree.command(name="rulesearch", description="Search FSAE rules by keyword")
@app_commands.describe(term="Keywords to search for")
async def search_command(interaction: discord.Interaction, term: str):
    await interaction.response.defer(thinking=True)

    # Apply fuzzy correction
    keywords, corrections = extract_keywords_fuzzy(term)
    
    results = keyword_search(term, context_lines=1, max_results=8, use_fuzzy=True)

    if not results:
        correction_note = ""
        if corrections:
            fixes = [f"'{k}' → '{v}'" for k, v in corrections.items()]
            correction_note = f"\n(Tried corrections: {', '.join(fixes)})"
        await interaction.followup.send(f"No results for: **{term}**{correction_note}")
        return

    output = f"**Search: {term}** ({len(results)} results)\n"
    if corrections:
        fixes = [f"`{k}` → `{v}`" for k, v in corrections.items()]
        output += f"📝 *Corrected: {', '.join(fixes)}*\n"
    output += "\n"
    
    for line_num, text in results:
        clean = text.strip().replace("[[#", "").replace("]]", "")
        entry = f"**Line {line_num}:**\n```\n{clean}\n```\n"
        if len(output) + len(entry) > 1900:
            output += "*[more results truncated]*"
            break
        output += entry

    await interaction.followup.send(output)


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    print(f"Command error: {error}")
    import traceback
    traceback.print_exception(type(error), error, error.__traceback__)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"Error: {error}")
        else:
            await interaction.response.send_message(f"Error: {error}", ephemeral=True)
    except Exception as e:
        print(f"Failed to send error message: {e}")


@bot.event
async def on_ready():
    try:
        print(f"on_ready triggered for {bot.user}")
        guild = discord.Object(id=1465062503254982981)
        
        # Sync to guild only (faster than global)
        print(f"Syncing commands to guild {guild.id}...")
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        
        print(f"FSAE Rules Bot online as {bot.user}")
        print(f"Loaded {len(RULES_LINES)} lines, {len(SECTION_INDEX)} sections indexed")
        print(f"Commands synced to guild {guild.id}")
    except Exception as e:
        print(f"ERROR in on_ready: {e}")
        import traceback
        traceback.print_exc()


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
