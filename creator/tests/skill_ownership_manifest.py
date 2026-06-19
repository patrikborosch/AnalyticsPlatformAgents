"""
Helpers for validating the checked-in skill ownership manifest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


# schemaVersion >= 2 introduces required per-team contact info. Bump this
# constant when adding new required fields so old fixtures stay valid.
CONTACT_REQUIRED_SCHEMA_VERSION = 2
CONTACT_REQUIRED_FIELDS = ("name", "email", "github")

# schemaVersion >= 3 introduces optional fields on contacts and teams
# that describe partitioned ownership within a single team, plus a
# relaxation on the primary contact: 'github' becomes optional (mirrors
# additionalContacts) so a team can route via a DG / DL with no GitHub
# user. v2 required fields are otherwise unchanged.
CONTACT_PARTITION_SCHEMA_VERSION = 3
# v3 RELAXATION: on primary contacts, only name + email are strictly
# required. 'github' becomes optional (same rule as additionalContacts) so
# a team can route via a DG / DL that has no GitHub user. When the github
# key IS present on a v3 primary contact, it must still be a non-empty
# string -- the validator collapses the tri-state (missing / empty / set)
# the same way it does for additionalContacts.
CONTACT_REQUIRED_FIELDS_V3 = ("name", "email")
# Required fields on each additionalContacts entry. github is optional here
# (DGs / DLs may not have a GitHub user); areas is also optional (a co-owner
# without an areas list is just an extra contact for the whole team).
ADDITIONAL_CONTACT_REQUIRED_FIELDS = ("name", "email")


def discover_skills(skills_dir: Path) -> list[str]:
    """Return checked-in skill folder names that contain SKILL.md."""
    return sorted(
        skill_dir.name
        for skill_dir in skills_dir.iterdir()
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists()
    )


def load_skill_ownership_manifest(manifest_path: Path) -> dict[str, Any]:
    """Load the YAML ownership manifest."""
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def get_team_contact(manifest: dict[str, Any], team_name: str) -> dict[str, str] | None:
    """Return the contact block for a team, or None if the team / contact is missing.

    Returns a dict with name, email, github keys (any of which may be missing
    if the team has a partial contact block; callers should handle).
    """
    teams = manifest.get("teams")
    if not isinstance(teams, dict):
        return None
    team = teams.get(team_name)
    if not isinstance(team, dict):
        return None
    contact = team.get("contact")
    if not isinstance(contact, dict):
        return None
    return contact


def _team_has_skills(manifest: dict[str, Any], team_name: str) -> bool:
    """True if at least one skill in the manifest references this team."""
    skills = manifest.get("skills")
    if not isinstance(skills, dict):
        return False
    for meta in skills.values():
        if isinstance(meta, dict) and meta.get("owningTeam") == team_name:
            return True
    return False


def _validate_contact_areas(
    team_name: str, label: str, contact: dict[str, Any]
) -> list[str]:
    """Validate the optional 'areas' field on a contact entry.

    When present, 'areas' must be a list of non-empty strings. The field is
    purely documentation (no routing impact today), so this validation only
    catches structural mistakes, not semantic ones (e.g. unknown area names).
    """
    errors: list[str] = []
    if "areas" not in contact:
        return errors
    areas = contact.get("areas")
    if not isinstance(areas, list):
        errors.append(
            f"Team '{team_name}' {label} 'areas' must be a list (got {type(areas).__name__})."
        )
        return errors
    for idx, area in enumerate(areas):
        if not isinstance(area, str) or not area.strip():
            errors.append(
                f"Team '{team_name}' {label} 'areas[{idx}]' must be a non-empty string."
            )
    return errors


def _validate_additional_contacts(
    team_name: str, team_data: dict[str, Any]
) -> list[str]:
    """Validate the optional 'additionalContacts' field on a team.

    When present, must be a list of dicts. Each dict needs name + email (the
    same required-strings rule as the primary contact); 'github' is optional
    here because DGs / DLs may not map to a GitHub user. The 'areas' field is
    optional and follows the same shape as the primary contact's areas.
    """
    errors: list[str] = []
    if "additionalContacts" not in team_data:
        return errors
    extras = team_data.get("additionalContacts")
    if not isinstance(extras, list):
        errors.append(
            f"Team '{team_name}' 'additionalContacts' must be a list "
            f"(got {type(extras).__name__})."
        )
        return errors
    for idx, extra in enumerate(extras):
        label = f"additionalContacts[{idx}]"
        if not isinstance(extra, dict):
            errors.append(
                f"Team '{team_name}' {label} must be an object (got {type(extra).__name__})."
            )
            continue
        for field in ADDITIONAL_CONTACT_REQUIRED_FIELDS:
            value = extra.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"Team '{team_name}' {label} is missing or empty field '{field}'."
                )
        github = extra.get("github")
        if "github" in extra:
            # When the key is present, it MUST be a non-empty string. An
            # explicit github: "" is rejected so downstream tooling can
            # treat "key missing" as the single canonical "no handle"
            # signal (avoids tri-state: missing / empty / set).
            if not isinstance(github, str) or not github.strip():
                errors.append(
                    f"Team '{team_name}' {label} 'github' must be a non-empty string "
                    f"when present (omit the key entirely if there is no GitHub handle)."
                )
        errors.extend(_validate_contact_areas(team_name, label, extra))
    return errors


def validate_skill_ownership_manifest(repo_root: Path) -> list[str]:
    """Return validation errors for the ownership manifest."""
    manifest_path = repo_root / ".github" / "skill-ownership.yml"
    if not manifest_path.exists():
        return [f"Missing ownership manifest: {manifest_path}"]

    manifest = load_skill_ownership_manifest(manifest_path)
    errors: list[str] = []

    raw_schema_version = manifest.get("schemaVersion")
    if raw_schema_version is None:
        schema_version = 1
    else:
        try:
            schema_version = int(raw_schema_version)
        except (TypeError, ValueError):
            errors.append(
                f"Manifest 'schemaVersion' must be an integer (got {raw_schema_version!r})."
            )
            # Use 1 as a conservative default so the rest of validation can
            # still run on the manifest and surface other errors in one pass,
            # rather than aborting at the first parse problem.
            schema_version = 1
    teams = manifest.get("teams")
    skills = manifest.get("skills")

    if not isinstance(teams, dict) or not teams:
        errors.append("Manifest must define a non-empty 'teams' mapping.")
        teams = {}

    if not isinstance(skills, dict) or not skills:
        errors.append("Manifest must define a non-empty 'skills' mapping.")
        skills = {}

    contact_required = schema_version >= CONTACT_REQUIRED_SCHEMA_VERSION
    partition_supported = schema_version >= CONTACT_PARTITION_SCHEMA_VERSION

    for team_name, team_data in teams.items():
        if not isinstance(team_data, dict):
            errors.append(f"Team '{team_name}' must map to an object.")
            continue
        if not team_data.get("displayName"):
            errors.append(f"Team '{team_name}' is missing 'displayName'.")
        if not team_data.get("scope"):
            errors.append(f"Team '{team_name}' is missing 'scope'.")
        if contact_required and _team_has_skills(manifest, team_name):
            contact = team_data.get("contact")
            if not isinstance(contact, dict):
                errors.append(
                    f"Team '{team_name}' owns at least one skill but is missing "
                    f"'contact' (required for schemaVersion >= {CONTACT_REQUIRED_SCHEMA_VERSION})."
                )
            else:
                if partition_supported:
                    # v3+: name + email strictly required; github is
                    # optional (mirrors additionalContacts). If the github
                    # key IS present, it must be a non-empty string -- an
                    # explicit "" is rejected so downstream tooling can
                    # treat "key missing" as the single canonical "no
                    # handle" signal.
                    for field in CONTACT_REQUIRED_FIELDS_V3:
                        value = contact.get(field)
                        if not isinstance(value, str) or not value.strip():
                            errors.append(
                                f"Team '{team_name}' contact is missing or empty field '{field}' "
                                f"(required for schemaVersion >= {CONTACT_REQUIRED_SCHEMA_VERSION})."
                            )
                    if "github" in contact:
                        gh = contact.get("github")
                        if not isinstance(gh, str) or not gh.strip():
                            errors.append(
                                f"Team '{team_name}' contact 'github' must be a non-empty string "
                                f"when present (omit the key entirely if there is no GitHub handle)."
                            )
                    errors.extend(_validate_contact_areas(team_name, "contact", contact))
                else:
                    for field in CONTACT_REQUIRED_FIELDS:
                        value = contact.get(field)
                        if not isinstance(value, str) or not value.strip():
                            errors.append(
                                f"Team '{team_name}' contact is missing or empty field '{field}' "
                                f"(required for schemaVersion >= {CONTACT_REQUIRED_SCHEMA_VERSION})."
                            )

        if partition_supported:
            errors.extend(_validate_additional_contacts(team_name, team_data))

    repo_skills = discover_skills(repo_root / "skills")
    manifest_skills = sorted(skills.keys()) if isinstance(skills, dict) else []

    missing_entries = sorted(set(repo_skills) - set(manifest_skills))
    extra_entries = sorted(set(manifest_skills) - set(repo_skills))

    for skill_name in missing_entries:
        errors.append(f"Skill '{skill_name}' is missing from .github/skill-ownership.yml.")

    for skill_name in extra_entries:
        errors.append(f"Manifest contains unknown skill '{skill_name}'.")

    for skill_name in set(repo_skills) & set(manifest_skills):
        metadata = skills.get(skill_name)
        if not isinstance(metadata, dict):
            errors.append(f"Skill '{skill_name}' must map to an object.")
            continue

        owning_team = metadata.get("owningTeam")
        area = metadata.get("area")

        if not owning_team:
            errors.append(f"Skill '{skill_name}' is missing 'owningTeam'.")
        elif owning_team not in teams:
            errors.append(
                f"Skill '{skill_name}' references unknown team '{owning_team}'."
            )

        if not area:
            errors.append(f"Skill '{skill_name}' is missing 'area'.")

    return errors
