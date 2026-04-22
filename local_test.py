"""
Local test harness: hammer the bot with rapid-fire questions to verify
key rotation recovers gracefully from 429 rate limits.
"""
import asyncio
import os
import sys
import time

os.environ.setdefault("DISCORD_BOT_TOKEN", "dummy-for-import-only")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot


QUESTIONS = [
    "What are the battery container attachment requirements?",
    "What is the max restrictor diameter for IC?",
    "Tell me about the TSAL",
    "Kill switch requirements?",
    "What chassis tubes are required?",
    "IMD function?",
    "Accumulator isolation relay specs",
    "Firewall requirements",
    "What is T.7.6?",
    "EV.5.3 requirements",
]


async def run_one(question: str, i: int):
    """Run the full /rule pipeline once, return (ok, seconds, preview)."""
    t0 = time.time()
    try:
        rule_codes = bot.extract_rule_codes(question)
        keywords, corrections = bot.extract_keywords_fuzzy(question)

        chunks = []
        codes = []
        if rule_codes:
            for code in rule_codes:
                chunks.extend(bot.lookup_rule_code(code))

        expanded = []
        if not chunks:
            expanded = await bot.expand_query(question)

        all_kw = list(set(keywords + expanded))
        if not chunks:
            chunks, codes = bot.find_relevant_sections(all_kw, max_sections=5)

        if not chunks:
            return False, time.time() - t0, "no matching rules"

        answer = await bot.ask_gemini(question, chunks)
        return True, time.time() - t0, answer[:120].replace("\n", " ")
    except Exception as e:
        return False, time.time() - t0, f"EXCEPTION: {e}"


async def main():
    print(f"API keys loaded: {len(bot.API_KEYS)}")
    for k in bot.API_KEYS:
        print(f"  key ...{k[-6:]}")
    print()
    print(f"Hammering {len(QUESTIONS)} questions back-to-back (2 Gemini calls each = {len(QUESTIONS)*2} API hits)")
    print("=" * 70)

    results = []
    for i, q in enumerate(QUESTIONS, 1):
        ok, dt, preview = await run_one(q, i)
        status = "OK " if ok else "FAIL"
        print(f"[{i:2d}/{len(QUESTIONS)}] {status} ({dt:5.1f}s) {q}")
        print(f"         -> {preview}")
        results.append((ok, dt))
        # Do NOT sleep between queries — we want to prove rotation recovers

    print()
    print("=" * 70)
    passed = sum(1 for ok, _ in results if ok)
    total_time = sum(dt for _, dt in results)
    print(f"Passed: {passed}/{len(results)}  |  total elapsed: {total_time:.1f}s")
    print(f"Cooldowns at end: {len(bot._key_cooldowns)} keys marked")


if __name__ == "__main__":
    asyncio.run(main())
