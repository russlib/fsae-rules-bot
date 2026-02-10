#!/usr/bin/env python3
"""
CLI wrapper for FSAE rules queries.
Usage: python query.py "What are the battery container requirements?"
"""

import sys
import os
import re

# Reuse logic from bot.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(SCRIPT_DIR, "FSAE_Rules_2026_V1.md")

# --- Load rules ---
with open(RULES_PATH, "r", encoding="utf-8", errors="replace") as f:
    RULES_TEXT = f.read()
RULES_LINES = RULES_TEXT.splitlines()

# --- Section index ---
SECTION_INDEX = {}

def build_section_index():
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

# --- Search ---
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
    words = re.findall(r'[a-z0-9]+', query.lower())
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    return keywords if keywords else words

def find_relevant_sections(query, max_sections=5):
    keywords = extract_keywords(query)
    scores = {}
    for code, (start, end) in SECTION_INDEX.items():
        section_text = "\n".join(RULES_LINES[start:end]).lower()
        score = sum(section_text.count(w) for w in keywords)
        if score > 0:
            scores[code] = score
    top = sorted(scores.items(), key=lambda x: -x[1])[:max_sections]
    chunks = []
    for code, score in top:
        start, end = SECTION_INDEX[code]
        text = "\n".join(RULES_LINES[start:end])
        chunks.append(text)
    return chunks

def keyword_search(query, context_lines=3, max_results=15):
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

# --- Main ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python query.py 'your question'")
        sys.exit(1)
    
    question = " ".join(sys.argv[1:])
    
    # Find relevant sections
    chunks = find_relevant_sections(question)
    
    if not chunks:
        results = keyword_search(question, context_lines=5, max_results=5)
        chunks = [text for _, text in results]
    
    if not chunks:
        print(f"No matching rules found for: {question}")
        sys.exit(1)
    
    # Output context for Gemini
    context = "\n\n---\n\n".join(chunks)
    
    # Trim if too long
    if len(context) > 30000:
        context = context[:30000] + "\n\n[...truncated]"
    
    print(f"QUESTION: {question}")
    print("\n" + "="*60 + "\n")
    print("RELEVANT RULES CONTEXT:")
    print(context)
