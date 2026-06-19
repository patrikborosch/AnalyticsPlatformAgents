"""
Shared skill validation helpers used by the quality checker and pytest.
"""

import math
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Set, Tuple

import yaml


STOP_WORDS = {
    "the",
    "and",
    "for",
    "from",
    "with",
    "this",
    "that",
    "when",
    "user",
    "use",
    "using",
}

DEFAULT_AMBIGUOUS_PATTERNS = [
    ("run sql", ["run sql", "execute sql", "sql query", "query"]),
    ("show tables", ["show tables", "list tables", "show me the tables", "what tables"]),
    ("explore data", ["explore data", "explore", "query the data", "query data"]),
    ("describe schema", ["describe schema", "describe", "schema", "describe columns"]),
    ("query", ["query", "run query", "execute query"]),
]

# Trigger-overlap detector parameters (Sensei-inspired anti-trigger heuristic).
TRIGGER_OVERLAP_DEFAULT_THRESHOLD = 0.5
TRIGGER_OVERLAP_MIN_SET_SIZE = 3

GENERAL_NAMING_PATTERNS = [
    r"^[a-z]+-authoring-[a-z]+$",
    r"^[a-z]+-consumption-[a-z]+$",
    r"^[a-z]+-operations-[a-z]+$",
    r"^e2e-[a-z-]+$",
    r"^[a-z-]+$",
]

RECOMMENDED_NAMING_PATTERNS = [
    r"^[a-z]+-authoring-[a-z]+$",
    r"^[a-z]+-consumption-[a-z]+$",
    r"^[a-z]+-operations-[a-z]+$",
    r"^e2e-[a-z-]+$",
]

HIGH_CONFIDENCE_MOJIBAKE_MARKERS = (
    "\u0393\u00c7\u00f6",  # ΓÇö
    "\u0393\u00c7\u00f4",  # ΓÇô
    "\u0393\u00c7\u00a3",  # ΓÇ£
    "\u0393\u00c7\u00a5",  # ΓÇ¥
    "\u0393\u00e5\u00c6",  # ΓåÆ
    "\u0393\u00e5\u00f6",  # Γåö
    "\u0393\u00dc\u00e1\u2229\u2555\u00c5",  # ΓÜá∩╕Å
    "\u252c\u00ba",  # ┬º
    "\u251c\u00f9",  # ├ù
)

COMMON_INFRA_RULES = (
    {
        "name": "auth_token_guidance",
        "description": "generic authentication or token-acquisition guidance",
        "trigger_patterns": (
            r"\baz login\b",
            r"get-access-token",
            r"token acquisition",
            r"ActiveDirectoryDefault uses az session",
            r"Authentication & Token Acquisition",
        ),
        "required_reference_groups": (
            {
                "label": "COMMON-CORE authentication guidance",
                "patterns": (
                    r"COMMON-CORE\.md#authentication--token-acquisition",
                    r"COMMON-CORE\.md[^\n]*(authentication|token audiences?)",
                ),
            },
            {
                "label": "COMMON-CLI authentication guidance",
                "patterns": (
                    r"COMMON-CLI\.md#authentication-recipes",
                    r"COMMON-CLI\.md[^\n]*(az login|token acquisition|auth)",
                ),
            },
        ),
    },
    {
        "name": "sqlcmd_tooling_guidance",
        "description": "generic sqlcmd install or verification guidance",
        "trigger_patterns": (
            r"winget install sqlcmd",
            r"brew install sqlcmd",
            r"apt(?:-get)? install sqlcmd",
            r"\bsqlcmd --version\b",
            r"`sqlcmd` not found",
            r"Install Go version:\s*`?winget install sqlcmd",
        ),
        "required_reference_groups": (
            {
                "label": "COMMON-CLI SQL tooling guidance",
                "patterns": (
                    r"COMMON-CLI\.md#sql--tds-data-plane-access",
                    r"COMMON-CLI\.md#tool-selection-rationale",
                    r"COMMON-CLI\.md[^\n]*sqlcmd",
                ),
            },
        ),
    },
)


def _extract_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1])
        body = parts[2]
        return frontmatter if frontmatter else {}, body
    except yaml.YAMLError:
        return {}, content


def _normalize_description(description: Any) -> str:
    """Normalize a frontmatter description to a trimmed string."""
    if isinstance(description, str):
        return description.strip()
    return str(description).strip() if description else ""


def _extract_triggers(description: str) -> Set[str]:
    """Extract trigger phrases from a skill description."""
    triggers: Set[str] = set()

    quoted = re.findall(r'"([^"]+)"', description)
    triggers.update(quoted)

    trigger_match = re.search(r"Triggers?:\s*(.+?)(?:\.|$)", description, re.IGNORECASE)
    if trigger_match:
        trigger_text = trigger_match.group(1)
        for phrase in trigger_text.split(","):
            phrase = phrase.strip().strip("\"'")
            if phrase and len(phrase) > 3:
                triggers.add(phrase.lower())

    wants_match = re.search(
        r"when the user wants to[:\s]+(.+?)(?:Triggers|$)",
        description,
        re.IGNORECASE | re.DOTALL,
    )
    if wants_match:
        items = re.findall(r"\((\d+)\)\s*([^(]+)", wants_match.group(1))
        for _, item in items:
            item = item.strip().rstrip(",.")
            if item and len(item) > 3:
                triggers.add(item.lower())

    return triggers


def _calculate_similarity(desc1: str, desc2: str) -> float:
    """Calculate Jaccard similarity between two descriptions."""
    words1 = set(re.findall(r"\b\w{3,}\b", desc1.lower()))
    words2 = set(re.findall(r"\b\w{3,}\b", desc2.lower()))

    words1 -= STOP_WORDS
    words2 -= STOP_WORDS

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union) if union else 0.0


def _build_skill_metadata(skill_path: Path, frontmatter: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the cross-skill metadata stored by the quality checker."""
    description = _normalize_description(frontmatter.get("description", ""))
    return {
        "description": description,
        "triggers": _extract_triggers(description),
        "path": str(skill_path),
    }


def load_skill_document(skill_path: Path) -> Dict[str, Any]:
    """Load a skill markdown file and return parsed content plus metadata."""
    content = skill_path.read_text(encoding="utf-8")
    frontmatter, body = _extract_frontmatter(content)
    return {
        "content": content,
        "body": body,
        "frontmatter": frontmatter,
        **_build_skill_metadata(skill_path, frontmatter),
    }


def analyze_naming_convention(skill_name: str) -> Dict[str, bool]:
    """Return naming-convention signals for a skill name."""
    if skill_name == "check-updates":
        return {
            "matches_general_pattern": True,
            "matches_recommended_pattern": True,
        }

    return {
        "matches_general_pattern": any(re.match(pattern, skill_name) for pattern in GENERAL_NAMING_PATTERNS),
        "matches_recommended_pattern": any(
            re.match(pattern, skill_name) for pattern in RECOMMENDED_NAMING_PATTERNS
        ),
    }


def detect_encoding_corruption(content: str) -> Sequence[str]:
    """Return high-confidence mojibake markers found in text."""
    return [marker for marker in HIGH_CONFIDENCE_MOJIBAKE_MARKERS if marker in content]


def analyze_structural_compliance(content: str, frontmatter: Mapping[str, Any], skill_name: str) -> Dict[str, Any]:
    """Return structural compliance signals for a skill document."""
    checks = {
        "has_frontmatter": bool(frontmatter),
        "has_name": "name" in frontmatter,
        "has_description": "description" in frontmatter,
        "has_update_notice": False,
        "has_must_prefer_avoid": False,
        "has_examples": False,
        "has_triggers_field": False,
        "code_blocks_tagged": True,
        "untagged_code_blocks": 0,
    }

    description_text = _normalize_description(frontmatter.get("description", ""))
    # Skill routers index on the explicit ``Triggers:`` field in the description.
    # ``check_description_quality``'s loose word-match ("description mentions
    # 'trigger' anywhere") accepts a far broader range, so we keep a dedicated
    # structural check for the field itself.
    checks["has_triggers_field"] = bool(re.search(r"Triggers?:\s*", description_text, re.IGNORECASE))

    if skill_name == "check-updates":
        checks["has_update_notice"] = True
    else:
        update_patterns = [
            r">\s*\*\*Update Check",
            r">\s*Update Check",
            r"check-updates",
        ]
        for pattern in update_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                checks["has_update_notice"] = True
                break

    mpa_patterns = [
        r"###?\s*(MUST|Must)\s*(DO)?",
        r"###?\s*(PREFER|Prefer)",
        r"###?\s*(AVOID|Avoid)",
        r"###?\s*Gotchas",
        r"###?\s*Rules",
    ]
    checks["has_must_prefer_avoid"] = sum(1 for pattern in mpa_patterns if re.search(pattern, content)) >= 2

    example_patterns = [
        r"###?\s*Example",
        r"```\w+\n[^`]+\n```",
        r'User:\s*"',
    ]
    checks["has_examples"] = any(re.search(pattern, content) for pattern in example_patterns)

    code_blocks = re.findall(r"^```(\w*)\s*$", content, re.MULTILINE)
    opening_fences = code_blocks[::2]
    untagged = sum(1 for language in opening_fences if not language)
    checks["untagged_code_blocks"] = untagged
    checks["code_blocks_tagged"] = untagged == 0

    return checks


def analyze_common_infra_compliance(content: str) -> Dict[str, Any]:
    """Return whether shared auth/tooling guidance is properly rooted in common docs."""
    issues = []
    flags = re.IGNORECASE | re.MULTILINE

    for rule in COMMON_INFRA_RULES:
        if not any(re.search(pattern, content, flags) for pattern in rule["trigger_patterns"]):
            continue

        missing_references = [
            reference_group["label"]
            for reference_group in rule["required_reference_groups"]
            if not any(re.search(pattern, content, flags) for pattern in reference_group["patterns"])
        ]

        if missing_references:
            issues.append(
                {
                    "rule": rule["name"],
                    "message": (
                        f"Defines {rule['description']} without shared references to "
                        f"{', '.join(missing_references)}"
                    ),
                    "missing_references": missing_references,
                }
            )

    return {
        "has_issues": bool(issues),
        "issues": issues,
    }


def find_semantic_conflicts(
    all_skills: Mapping[str, Mapping[str, Any]],
    similarity_threshold: float = 0.3,
) -> Sequence[Dict[str, Any]]:
    """Find pairs of skills whose descriptions overlap enough to cause ambiguity."""
    conflicts = []
    skill_names = list(all_skills.keys())

    for index, skill1 in enumerate(skill_names):
        for skill2 in skill_names[index + 1 :]:
            if skill1 == "check-updates" or skill2 == "check-updates":
                continue

            desc1 = all_skills[skill1].get("description", "")
            desc2 = all_skills[skill2].get("description", "")
            similarity = _calculate_similarity(desc1, desc2)

            if similarity >= similarity_threshold:
                conflicts.append(
                    {
                        "skill1": skill1,
                        "skill2": skill2,
                        "similarity": round(similarity, 2),
                        "reason": f"{int(similarity * 100)}% description overlap - may cause ambiguous skill routing",
                    }
                )

    return conflicts


def build_similarity_matrix(all_skills: Mapping[str, Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Build a Jaccard similarity matrix between all non-utility skills."""
    skill_names = [skill_name for skill_name in all_skills.keys() if skill_name != "check-updates"]
    if len(skill_names) < 2:
        return None

    matrix = []
    for row_index, skill1 in enumerate(skill_names):
        row = []
        desc1 = all_skills[skill1].get("description", "")

        for column_index, skill2 in enumerate(skill_names):
            if row_index == column_index:
                row.append(1.0)
            elif column_index < row_index:
                row.append(matrix[column_index][row_index])
            else:
                desc2 = all_skills[skill2].get("description", "")
                row.append(round(_calculate_similarity(desc1, desc2), 2))

        matrix.append(row)

    return {"skills": skill_names, "matrix": matrix}


def find_duplicate_triggers(
    all_skills: Mapping[str, Mapping[str, Any]],
    min_trigger_length: int = 5,
) -> Sequence[Dict[str, Any]]:
    """Find duplicate trigger phrases shared across multiple skills."""
    trigger_to_skills: Dict[str, Set[str]] = {}

    for skill_name, skill_data in all_skills.items():
        if skill_name == "check-updates":
            continue

        for trigger in skill_data.get("triggers", set()):
            trigger_lower = trigger.lower().strip()
            if len(trigger_lower) > min_trigger_length:
                trigger_to_skills.setdefault(trigger_lower, set()).add(skill_name)

    duplicates = []
    for trigger, skills in trigger_to_skills.items():
        if len(skills) > 1:
            duplicates.append({"trigger": trigger, "skills": list(skills)})

    return duplicates


def find_ambiguous_triggers(
    all_skills: Mapping[str, Mapping[str, Any]],
    ambiguous_patterns: Sequence[Tuple[str, Sequence[str]]] = DEFAULT_AMBIGUOUS_PATTERNS,
) -> Sequence[Dict[str, Any]]:
    """Find generic trigger phrases that currently match multiple skills."""
    pattern_matches: Dict[str, list] = {}

    for skill_name, skill_data in all_skills.items():
        if skill_name == "check-updates":
            continue

        desc_lower = skill_data.get("description", "").lower()
        triggers = skill_data.get("triggers", set())

        for pattern_name, pattern_variants in ambiguous_patterns:
            for variant in pattern_variants:
                found_in = None
                if variant in desc_lower:
                    found_in = f'description contains "{variant}"'
                else:
                    for trigger in triggers:
                        if variant in trigger.lower():
                            found_in = f'trigger "{trigger}"'
                            break

                if found_in:
                    pattern_matches.setdefault(pattern_name, [])
                    if not any(existing_skill == skill_name for existing_skill, _ in pattern_matches[pattern_name]):
                        pattern_matches[pattern_name].append((skill_name, found_in))
                    break

    ambiguous = []
    for pattern, matches in pattern_matches.items():
        if len(matches) > 1:
            ambiguous.append(
                {
                    "trigger_phrase": pattern,
                    "skills": [{"skill": skill, "match": match} for skill, match in matches],
                    "ambiguity": f"Could match {len(matches)} skills",
                }
            )

    return ambiguous


# --------------------------------------------------------------------------- #
# Sensei-inspired anti-trigger overlap detector (advisory; never blocks a PR).
# Compares the ``Triggers:`` field token sets across skill pairs to surface
# routing collisions the description-level Jaccard matrix cannot see.
# Provenance: heuristic inspired by Azure/azure-sdk-tools .github/skills/sensei.
# --------------------------------------------------------------------------- #

def _extract_trigger_list_field(description: str) -> Set[str]:
    """Extract the contents of the ``Triggers:`` field as a normalised token set.

    Differs from ``_extract_triggers`` in that it only considers the explicit
    ``Triggers:`` span — quoted phrases elsewhere in the description are ignored.
    This is exactly the granularity the anti-trigger overlap detector needs.

    The capture terminates at a real **sentence boundary** — a period followed
    by whitespace, a newline, or end-of-string — so periods *inside* a trigger
    (e.g. ``"v1.5 query"``, ``"Gen2.1 dataflow"``) do not truncate the field.
    Prose appearing after the field (e.g. ``Triggers: "a", "b". Do NOT match
    "c".``) is still cleanly excluded because the prose-ending period is also a
    sentence boundary.
    """
    if not description:
        return set()

    match = re.search(
        # ``.+?`` is non-greedy so the lookahead resolves at the first true
        # sentence boundary, not at the first period anywhere.
        r"Triggers?:\s*(.+?)(?:\.(?=\s|$)|$)",
        description,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return set()

    span = match.group(1)
    triggers: Set[str] = set()

    quoted = re.findall(r'"([^"]+)"', span)
    if quoted:
        for phrase in quoted:
            phrase = phrase.strip().lower()
            if len(phrase) > 2:
                triggers.add(phrase)
    else:
        for phrase in span.split(","):
            phrase = phrase.strip().strip("\"'.")
            if len(phrase) > 2:
                triggers.add(phrase.lower())

    return triggers


def find_trigger_overlap(
    all_skills: Mapping[str, Mapping[str, Any]],
    overlap_threshold: float = TRIGGER_OVERLAP_DEFAULT_THRESHOLD,
    min_trigger_count: int = TRIGGER_OVERLAP_MIN_SET_SIZE,
) -> Sequence[Dict[str, Any]]:
    """Find pairs of skills whose ``Triggers:`` field token sets overlap.

    Overlap = ``|A ∩ B| / min(|A|, |B|)`` — i.e. fraction of the smaller
    skill's triggers that also appear in the larger skill. Pairs where either
    set has fewer than ``min_trigger_count`` triggers are skipped to avoid
    noisy single-trigger collisions. The ``check-updates`` utility skill is
    excluded.

    Returns a list of dicts sorted by descending overlap.
    """
    skill_triggers: Dict[str, Set[str]] = {}
    for skill_name, skill_data in all_skills.items():
        if skill_name == "check-updates":
            continue
        description = skill_data.get("description", "")
        triggers = _extract_trigger_list_field(description)
        if len(triggers) >= min_trigger_count:
            skill_triggers[skill_name] = triggers

    skill_names = sorted(skill_triggers.keys())
    overlaps: list = []
    for index, skill_a in enumerate(skill_names):
        set_a = skill_triggers[skill_a]
        for skill_b in skill_names[index + 1 :]:
            set_b = skill_triggers[skill_b]
            common = set_a & set_b
            if not common:
                continue
            denom = min(len(set_a), len(set_b))
            overlap = len(common) / denom if denom else 0.0
            if overlap > overlap_threshold:
                # Store the raw float; downstream renders (summary line,
                # PR-comment template, ``reason`` string) all use ``math.ceil``
                # on the percent so that the displayed % can never disagree
                # with the ``> 0.5`` threshold decision. ``round()`` would
                # rounding-half-to-even map e.g. 0.501 to "50%" while the
                # pair was flagged for exceeding 50%; ceil keeps the display
                # in the >50 band for every flagged pair.
                overlap_pct = math.ceil(overlap * 100)
                overlaps.append(
                    {
                        "skill1": skill_a,
                        "skill2": skill_b,
                        "overlap": overlap,
                        "overlap_pct": overlap_pct,
                        "shared_triggers": sorted(common),
                        "skill1_trigger_count": len(set_a),
                        "skill2_trigger_count": len(set_b),
                        "reason": (
                            f"{len(common)} of {denom} smaller-set triggers overlap "
                            f"({overlap_pct}%) — may collide at routing time"
                        ),
                    }
                )

    overlaps.sort(key=lambda row: (-row["overlap"], row["skill1"], row["skill2"]))
    return overlaps
