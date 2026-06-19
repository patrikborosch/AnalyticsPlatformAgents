"""
Shared pytest fixtures for skills-for-fabric tests.
"""
import pytest
from pathlib import Path

from skill_validation import load_skill_document


# =============================================================================
# Path Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def skills_dir(repo_root) -> Path:
    """Return the skills directory."""
    return repo_root / "skills"


@pytest.fixture(scope="session")
def common_dir(repo_root) -> Path:
    """Return the common directory."""
    return repo_root / "common"


# =============================================================================
# Skill Loading Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def all_skills(skills_dir) -> dict:
    """Load all skills with their frontmatter and content."""
    skills = {}
    for skill_folder in skills_dir.iterdir():
        if not skill_folder.is_dir():
            continue
        skill_md = skill_folder / "SKILL.md"
        if not skill_md.exists():
            continue

        skill_document = load_skill_document(skill_md)
        frontmatter = skill_document["frontmatter"]
        skills[skill_folder.name] = {
            "name": frontmatter.get("name", skill_folder.name),
            "description": skill_document["description"],
            "content": skill_document["content"],
            "body": skill_document["body"],
            "path": skill_md,
            "frontmatter": frontmatter,
            "triggers": skill_document["triggers"],
        }
    
    return skills


@pytest.fixture(scope="session")
def skill_index(all_skills) -> dict:
    """Expose skills in the shared analyzer input shape."""
    return {
        skill_name: {
            "description": skill_data["description"],
            "triggers": skill_data["triggers"],
            "path": str(skill_data["path"]),
        }
        for skill_name, skill_data in all_skills.items()
    }


# =============================================================================
# Pytest Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "semantic: tests that validate skill semantics (no external deps)")
    config.addinivalue_line("markers", "routing: tests that validate skill routing based on user prompts")
