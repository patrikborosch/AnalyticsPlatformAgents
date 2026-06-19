#!/usr/bin/env python3
"""
Skill Catalog Generator

Auto-generates docs/skill-catalog.md from skills/*/SKILL.md frontmatter.
Run manually by maintainers as needed (e.g., during release prep).
Contributors do NOT run this in feature PRs -- regenerating locally produces
diffs that conflict between concurrent PRs.

Usage:
    python generate_skill_catalog.py           # Generate catalog
    python generate_skill_catalog.py --check   # Verify catalog is in sync (ad-hoc)
"""

import os
import sys
import re
import yaml
from pathlib import Path

SKILLS_DIR = Path("skills")
CATALOG_PATH = Path("docs/skill-catalog.md")

CATALOG_HEADER = """<!--
  AUTO-GENERATED FILE - DO NOT EDIT MANUALLY

  This file is regenerated from skills/*/SKILL.md frontmatter.
  Maintainers refresh it manually via:

    python .github/scripts/generate_skill_catalog.py

  Contributors do NOT regenerate in feature PRs (it produces diffs that
  conflict between concurrent skill PRs).
-->

# Skill Catalog

This catalog lists all available skills-for-fabric with their purpose and triggers.

> **This file is auto-generated.** Do not edit manually.
>
> Maintainers refresh by running `python .github/scripts/generate_skill_catalog.py` from the repo root.

"""


def extract_frontmatter(skill_path: Path) -> dict:
    """Extract YAML frontmatter from SKILL.md"""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return None
    
    content = skill_md.read_text(encoding="utf-8")
    
    # Extract YAML frontmatter between --- markers
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return None
    
    try:
        frontmatter = yaml.safe_load(match.group(1))
        return frontmatter
    except yaml.YAMLError:
        return None


def extract_triggers(description: str) -> list:
    """Extract trigger phrases from description"""
    triggers = []
    
    # Look for "Triggers:" section in description
    match = re.search(r'Triggers?:\s*["\']?([^"\']+)["\']?\.?\s*$', description, re.IGNORECASE)
    if match:
        trigger_text = match.group(1)
        # Split by comma or "or"
        triggers = [t.strip().strip('"\'') for t in re.split(r',\s*|\s+or\s+', trigger_text)]
    
    return triggers[:5]  # Limit to 5 triggers for readability


def determine_skill_type(name: str, description: str) -> str:
    """Determine skill type from name and description"""
    name_lower = name.lower()
    desc_lower = description.lower()
    
    if "check-updates" in name_lower or "update" in name_lower:
        return "Utility"
    elif "monitoring" in name_lower or "diagnos" in desc_lower or "pressure" in desc_lower:
        return "Operations"
    elif "authoring" in name_lower or "ddl" in desc_lower or "create" in desc_lower:
        return "Authoring"
    elif "consumption" in name_lower or "query" in desc_lower or "explore" in desc_lower:
        return "Consumption"
    elif "e2e-" in name_lower or "end-to-end" in desc_lower:
        return "End-to-End"
    else:
        return "General"


def extract_purpose(description: str) -> str:
    """Extract short purpose from description (first sentence or up to 'Use when')"""
    # Remove "Triggers:" section
    desc = re.sub(r'\s*Triggers?:.*$', '', description, flags=re.IGNORECASE | re.DOTALL)
    
    # Take up to "Use when" or first sentence
    match = re.match(r'^(.*?)(?:\.\s*Use when|\. Use when|$)', desc, re.DOTALL)
    if match:
        purpose = match.group(1).strip()
        if not purpose.endswith('.'):
            purpose += '.'
        return purpose
    
    return desc[:200] + "..." if len(desc) > 200 else desc


def generate_catalog() -> str:
    """Generate the full catalog markdown"""
    skills = []
    
    # Scan all skill directories
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        
        frontmatter = extract_frontmatter(skill_dir)
        if not frontmatter:
            continue
        
        name = frontmatter.get("name", skill_dir.name)
        description = frontmatter.get("description", "")
        
        skills.append({
            "name": name,
            "dir": skill_dir.name,
            "description": description,
            "type": determine_skill_type(name, description),
            "purpose": extract_purpose(description),
            "triggers": extract_triggers(description),
        })
    
    # Generate markdown
    md = CATALOG_HEADER
    
    # Overview table
    md += "## Overview\n\n"
    md += "| Skill | Type | Purpose |\n"
    md += "|-------|------|---------|"
    
    for skill in skills:
        short_purpose = skill["purpose"][:60] + "..." if len(skill["purpose"]) > 60 else skill["purpose"]
        md += f"\n| [{skill['name']}](#{skill['name']}) | {skill['type']} | {short_purpose} |"
    
    md += "\n\n---\n\n"
    
    # Individual skill sections
    for skill in skills:
        md += f"## {skill['name']}\n\n"
        md += f"**Type:** {skill['type']}\n\n"
        md += f"**Purpose:** {skill['purpose']}\n\n"
        
        if skill["triggers"]:
            md += "**Triggers:**\n"
            for trigger in skill["triggers"]:
                md += f"- \"{trigger}\"\n"
            md += "\n"
        
        md += f"**Location:** `skills/{skill['dir']}/`\n\n"
        md += "---\n\n"
    
    # Category tables
    md += "## Skill Categories\n\n"
    md += "### By Type\n\n"
    md += "| Type | Skills |\n"
    md += "|------|--------|\n"
    
    types = {}
    for skill in skills:
        t = skill["type"]
        if t not in types:
            types[t] = []
        types[t].append(skill["name"])
    
    for t, names in sorted(types.items()):
        md += f"| {t} | {', '.join(names)} |\n"
    
    md += "\n---\n\n"
    md += "## Next Steps\n\n"
    md += "- [Skill Authoring Guide](skill-authoring-guide.md) — Create a new skill\n"
    md += "- [Architecture Overview](architecture-overview.md) — Understand the repo structure\n"
    
    return md


def main():
    check_mode = "--check" in sys.argv
    
    new_catalog = generate_catalog()
    
    if check_mode:
        # Check if catalog matches the freshly-generated content exactly.
        # The header no longer carries a timestamp (removed in PR #306 to stop
        # noise commits + churn), so a direct strip+compare is sufficient.
        if CATALOG_PATH.exists():
            existing = CATALOG_PATH.read_text(encoding="utf-8")
            if existing.strip() == new_catalog.strip():
                print("✅ Skill catalog is up to date")
                sys.exit(0)
            else:
                print("❌ Skill catalog is out of date!")
                print("   Run: python .github/scripts/generate_skill_catalog.py")
                sys.exit(1)
        else:
            print("❌ Skill catalog does not exist!")
            sys.exit(1)
    else:
        # Generate mode
        CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CATALOG_PATH.write_text(new_catalog, encoding="utf-8")
        print(f"✅ Generated {CATALOG_PATH}")
        
        # Count skills
        skill_count = len(list(SKILLS_DIR.glob("*/SKILL.md")))
        print(f"   {skill_count} skills cataloged")


if __name__ == "__main__":
    main()
