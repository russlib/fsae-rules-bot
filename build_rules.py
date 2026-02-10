"""
Build a clean, searchable markdown file from the raw FSAE rules pdftotext output.
Adds proper markdown headings, linkable TOC, and cross-references.
"""
import re
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(SCRIPT_DIR, "FSAE_Rules_2026_V1_raw.txt")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "FSAE_Rules_2026_V1.md")

with open(RAW_PATH, "r", encoding="utf-8", errors="replace") as f:
    raw = f.read()

lines = raw.splitlines()

# --- Phase 1: Strip page headers/footers and clean whitespace ---
cleaned = []
skip_next = False
for i, line in enumerate(lines):
    # Skip page footer lines
    if re.match(r'^Formula SAE.*Page \d+ of \d+', line.strip()):
        skip_next = True  # next line is "Version 1.0..."
        continue
    if skip_next and re.match(r'^Version 1\.0', line.strip()):
        skip_next = False
        continue
    skip_next = False

    # Strip leading whitespace but preserve content
    stripped = line.rstrip()
    # Remove excessive leading spaces (pdftotext artifact)
    stripped = re.sub(r'^    {2,}', '    ', stripped)
    cleaned.append(stripped)

# --- Phase 2: Identify and mark headings ---
# Major sections: "GR - GENERAL REGULATIONS", "EV - ELECTRIC VEHICLES"
major_pat = re.compile(r'^([A-Z]{1,2})\s*-\s*([A-Z][A-Z\s&/]+)$')
# Section headers: "EV.5 ENERGY STORAGE", "F.10 TRACTIVE BATTERY CONTAINER (EV ONLY)"
section_pat = re.compile(r'^([A-Z]{1,2}\.\d{1,2})\s+([A-Z][A-Z\s&/\-\(\)]+)$')
# Subsection headers: "EV.5.3 Maximum Voltage" (title case or all caps)
subsec_pat = re.compile(r'^([A-Z]{1,2}\.\d{1,2}\.\d{1,2})\s+([A-Z][A-Za-z\s&/\-\(\)]+)$')

output = []
heading_map = {}  # code -> heading text (for TOC linking)

# Skip TOC (pages 1-4, roughly first ~100 lines that are TOC)
in_toc = False
toc_end = 0
for i, line in enumerate(cleaned):
    if 'TABLE OF CONTENTS' in line:
        in_toc = True
    if in_toc and re.match(r'^[A-Z]{1,2}\s*-\s*[A-Z]', line) and i > 20:
        # First actual content section
        toc_end = i
        break
    if in_toc and re.match(r'^GR\.1\s', line) and i > 20:
        toc_end = i
        break

# Find actual content start (first major section)
content_start = 0
for i, line in enumerate(cleaned):
    if major_pat.match(line.strip()) and i > 10:
        content_start = i
        break

# Process content lines
i = content_start
while i < len(cleaned):
    line = cleaned[i].strip()

    # Skip empty lines
    if not line:
        output.append("")
        i += 1
        continue

    # Major section: # GR - GENERAL REGULATIONS
    m = major_pat.match(line)
    if m:
        code = m.group(1)
        title = line
        output.append(f"# {title}")
        heading_map[code] = title
        i += 1
        continue

    # Section header: ## EV.5 ENERGY STORAGE
    m = section_pat.match(line)
    if m:
        code = m.group(1)
        output.append(f"## {line}")
        heading_map[code] = line
        i += 1
        continue

    # Subsection header: ### EV.5.3 Maximum Voltage
    m = subsec_pat.match(line)
    if m:
        code = m.group(1)
        output.append(f"### {line}")
        heading_map[code] = line
        i += 1
        continue

    # Rule lines: bold the rule number
    rule_pat = re.compile(r'^([A-Z]{1,2}\.\d{1,2}\.\d{1,2}\.\d{1,2}(?:\.\d+)?)\s+(.*)')
    m = rule_pat.match(line)
    if m:
        code = m.group(1)
        rest = m.group(2)
        output.append(f"**{code}** {rest}")
        i += 1
        continue

    # Regular content line
    output.append(line)
    i += 1

# --- Phase 3: Build TOC with links ---
toc_lines = [
    "# FORMULA SAE Rules 2026",
    "",
    "Version 1.0 | 10 Sept 2025",
    "",
    "---",
    "",
    "# Table of Contents",
    "",
]

# Group sections by major code
major_sections = {
    "GR": "General Regulations",
    "AD": "Administrative Regulations",
    "PS": "Pre-Competition Submissions",
    "V": "Vehicle Requirements",
    "F": "Chassis and Structural",
    "T": "Technical Aspects",
    "VE": "Vehicle and Driver Equipment",
    "IC": "Internal Combustion Engine Vehicles",
    "EV": "Electric Vehicles",
    "IN": "Technical Inspection",
    "S": "Static Events",
    "D": "Dynamic Events",
}

for major_code, major_title in major_sections.items():
    # Find the major heading
    major_key = f"{major_code} - {major_title.upper()}"
    found_heading = None
    for code, heading in heading_map.items():
        if code == major_code:
            found_heading = heading
            break

    if found_heading:
        toc_lines.append(f"- **[[#{found_heading}|{major_code} - {major_title}]]**")
    else:
        toc_lines.append(f"- **{major_code} - {major_title}**")

    # Add subsections (XX.N level)
    sub_pat = re.compile(rf'^{re.escape(major_code)}\.\d{{1,2}}$')
    for code in sorted(heading_map.keys(), key=lambda c: [int(x) if x.isdigit() else x for x in re.split(r'[.]', c)]):
        if sub_pat.match(code):
            heading = heading_map[code]
            toc_lines.append(f"    - [[#{heading}|{code} {heading.split(' ', 1)[-1] if ' ' in heading else ''}]]")

toc_lines.extend(["", "---", ""])

# --- Phase 4: Linkify cross-references in body ---
# Pattern: rule codes like IC.9.2.2, T.1.8, EV.5.3.1 in body text
ref_pat = re.compile(r'(?<!\*\*)(?<!\[#)(?<!\|)(?<![A-Za-z])([A-Z]{1,2}\.\d{1,2}\.\d{1,2}(?:\.\d{1,2})*)(?![A-Za-z\d])(?!\]\])')

def replace_ref(match):
    code = match.group(1)
    # Try exact match
    if code in heading_map:
        return f"[[#{heading_map[code]}|{code}]]"
    # Try parent
    parts = code.split('.')
    for depth in range(len(parts) - 1, 1, -1):
        parent = '.'.join(parts[:depth])
        if parent in heading_map:
            return f"[[#{heading_map[parent]}|{code}]]"
    return code

final_output = []
for line in output:
    # Don't linkify headings or already-linked content
    if line.startswith('#') or '[[#' in line:
        final_output.append(line)
    else:
        final_output.append(ref_pat.sub(replace_ref, line))

# --- Write output ---
full_output = "\n".join(toc_lines + final_output)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(full_output)

# Stats
total_links = full_output.count("[[#")
heading_count = len(heading_map)
line_count = full_output.count("\n")
print(f"Headings indexed: {heading_count}")
print(f"Internal links: {total_links}")
print(f"Output lines: {line_count}")
print(f"Output: {OUTPUT_PATH}")
