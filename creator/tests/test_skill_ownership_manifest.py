"""
Tests for the checked-in skill ownership manifest.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent))

from skill_ownership_manifest import (
    get_team_contact,
    load_skill_ownership_manifest,
    validate_skill_ownership_manifest,
)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


V2_VALID_MANIFEST = """
schemaVersion: 2
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice Example
      email: alice@example.com
      github: alice_example
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip()


class SkillOwnershipManifestTests(unittest.TestCase):
    def test_repo_manifest_covers_all_checked_in_skills(self) -> None:
        repo_root = Path(__file__).parent.parent
        errors = validate_skill_ownership_manifest(repo_root)
        self.assertFalse(errors, "\n".join(errors))

    def test_validation_detects_missing_skill_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 1
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
skills: {}
""".strip())

            errors = validate_skill_ownership_manifest(repo_root)

            self.assertTrue(
                any("alpha-skill" in error for error in errors),
                f"Expected missing skill error, got: {errors}",
            )

    def test_v1_manifest_without_contact_still_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 1
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertEqual(errors, [])

    def test_v2_team_with_skills_missing_contact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 2
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any("contact" in e and "platform" in e for e in errors),
                f"Expected contact-missing error for 'platform', got: {errors}",
            )

    def test_v2_team_with_partial_contact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 2
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      # github missing
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any("github" in e for e in errors),
                f"Expected missing github error, got: {errors}",
            )

    def test_v2_team_without_skills_is_not_required_to_have_contact(self) -> None:
        # A team that owns NO skills shouldn't force contact info (allows
        # teams to exist as placeholders without forcing fake contact data).
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 2
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
  unused:
    displayName: Unused team
    scope: Has no skills yet
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_get_team_contact_returns_dict_for_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.yml"
            manifest_path.write_text(V2_VALID_MANIFEST, encoding="utf-8")
            manifest = load_skill_ownership_manifest(manifest_path)
            contact = get_team_contact(manifest, "platform")
            self.assertIsNotNone(contact)
            self.assertEqual(contact["github"], "alice_example")

    def test_get_team_contact_returns_none_for_missing_team(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.yml"
            manifest_path.write_text(V2_VALID_MANIFEST, encoding="utf-8")
            manifest = load_skill_ownership_manifest(manifest_path)
            self.assertIsNone(get_team_contact(manifest, "nonexistent"))

    def test_schema_version_string_is_coerced_to_int(self) -> None:
        # Some YAML editors / hand-edits write '2' as a string. Validation
        # must coerce, not raise TypeError when comparing schema_version to
        # the integer CONTACT_REQUIRED_SCHEMA_VERSION.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: "2"
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            # Should validate cleanly (contact present); the string '2' must
            # be coerced so the >= comparison doesn't raise.
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_schema_version_unparseable_string_reports_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: "not-a-number"
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any("schemaVersion" in e and "integer" in e for e in errors),
                f"Expected schemaVersion-must-be-int error, got: {errors}",
            )

    # ------------------------------------------------------------------
    # schemaVersion 3: optional 'areas' on contact + optional
    # 'additionalContacts' on team.
    # ------------------------------------------------------------------

    def test_v3_team_with_additional_contacts_and_areas_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
      areas:
        - widget-authoring
    additionalContacts:
      - name: Bob
        email: bob@example.com
        github: bob_example
        areas:
          - widget-runtime
          - default
      - name: Some DG
        email: somedg@example.com
        # github intentionally omitted (DGs may not have a handle).
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_v3_without_optional_partition_fields_validates(self) -> None:
        # A v3 manifest that omits both 'areas' and 'additionalContacts'
        # must still validate cleanly (the new fields are purely optional).
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_v3_additional_contact_missing_email_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
    additionalContacts:
      - name: Bob
        # email missing
        github: bob_example
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any("additionalContacts[0]" in e and "email" in e for e in errors),
                f"Expected additionalContacts[0] missing-email error, got: {errors}",
            )

    def test_v3_additional_contacts_not_list_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
    additionalContacts:
      name: Bob
      email: bob@example.com
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any("additionalContacts" in e and "list" in e for e in errors),
                f"Expected additionalContacts-must-be-list error, got: {errors}",
            )

    def test_v3_areas_with_empty_string_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
      areas:
        - widget-authoring
        - ""
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any("areas[1]" in e for e in errors),
                f"Expected areas[1] empty-string error, got: {errors}",
            )

    def test_v2_manifest_ignores_unknown_partition_fields(self) -> None:
        # A v2 manifest with 'areas' or 'additionalContacts' should not be
        # validated against the v3 rules: the new fields are silently ignored
        # (forward-compat: someone may experiment with the fields before the
        # schema bump lands).
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 2
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
    additionalContacts:
      # malformed entry; v2 must NOT validate the new shape
      - junk
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertEqual(errors, [], f"Unexpected v2 errors: {errors}")

    def test_v3_additional_contact_github_empty_string_fails(self) -> None:
        # Regression: an explicit `github: ""` on an additionalContacts entry
        # must be rejected. The contract is "if the github key is present, it
        # is a non-empty string"; downstream tooling treats key-missing as
        # the canonical "no handle" signal, so an empty string would create
        # an ambiguous tri-state (missing / empty / set).
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: alice_example
    additionalContacts:
      - name: Some DG
        email: somedg@example.com
        github: ""
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any(
                    "additionalContacts[0]" in e
                    and "github" in e
                    and "non-empty" in e
                    for e in errors
                ),
                f"Expected non-empty github error, got: {errors}",
            )

    def test_v3_primary_contact_without_github_validates(self) -> None:
        # Regression: v3 RELAXATION -- the primary 'contact' may omit the
        # github key (mirrors additionalContacts). DGs / DLs without a
        # GitHub user can be the routing target. name + email still
        # required; the renderer at .github/scripts/weekly-flake-report.py
        # L396 already handles a missing github cleanly via the
        # "(GitHub handle: lookup needed)" fall-back.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Fabric Eventstream AI Feature Team
      email: eventstreamaift@example.com
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_v3_primary_contact_github_empty_string_fails(self) -> None:
        # The relaxation does NOT mean github: "" is valid. If the key is
        # present, the value must be a non-empty string (mirrors the
        # additionalContacts contract). This collapses the tri-state
        # (missing / empty / set) to two canonical states.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Alice
      email: alice@example.com
      github: ""
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any(
                    "contact" in e
                    and "github" in e
                    and "non-empty" in e
                    for e in errors
                ),
                f"Expected non-empty github error, got: {errors}",
            )

    def test_v3_primary_contact_missing_email_still_fails(self) -> None:
        # The relaxation only affects github. name and email remain
        # strictly required on the primary contact for teams that own
        # at least one skill.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 3
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Some DG
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any("contact is missing or empty field 'email'" in e for e in errors),
                f"Expected missing-email error, got: {errors}",
            )

    def test_v2_primary_contact_without_github_still_fails(self) -> None:
        # The github-optional relaxation only applies under v3+. A v2
        # manifest must still satisfy the old strict contract -- this
        # keeps any consumer parsing legacy manifests unsurprised.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_file(repo_root / "skills" / "alpha-skill" / "SKILL.md", "# alpha\n")
            write_file(repo_root / ".github" / "skill-ownership.yml", """
schemaVersion: 2
teams:
  platform:
    displayName: Platform
    scope: Shared tooling
    contact:
      name: Some DG
      email: somedg@example.com
skills:
  alpha-skill:
    owningTeam: platform
    area: utility
""".strip())
            errors = validate_skill_ownership_manifest(repo_root)
            self.assertTrue(
                any("contact is missing or empty field 'github'" in e for e in errors),
                f"Expected v2 missing-github error, got: {errors}",
            )


if __name__ == "__main__":
    unittest.main()
