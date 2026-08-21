"""Guard against drift between zensical.toml nav and docs/ on disk."""

import re
import tomllib
from pathlib import Path

from pin_actions.config import Settings

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def _collect_nav_paths(entries: list) -> set[str]:
    """Recursively collect all .md path strings referenced by a nav array."""
    paths = set()
    for entry in entries:
        for value in entry.values():
            if isinstance(value, str):
                paths.add(value)
            else:
                paths |= _collect_nav_paths(value)
    return paths


def test_nav_matches_docs_on_disk() -> None:
    """Every docs/**/*.md file must be reachable from zensical.toml nav, and vice versa."""
    config = tomllib.loads((REPO_ROOT / "zensical.toml").read_text())
    nav_paths = _collect_nav_paths(config["project"]["nav"])

    disk_paths = {str(p.relative_to(DOCS_DIR)) for p in DOCS_DIR.rglob("*.md")}

    orphaned_on_disk = disk_paths - nav_paths
    orphaned_in_nav = nav_paths - disk_paths

    assert not orphaned_on_disk, f"Files on disk missing from zensical.toml nav: {sorted(orphaned_on_disk)}"
    assert not orphaned_in_nav, f"Nav entries reference nonexistent files: {sorted(orphaned_in_nav)}"


def test_cli_reference_documents_all_settings_fields() -> None:
    """Every Settings field's --kebab-case flag (or raw name) must appear in reference/cli.md.

    The ``::: pin_actions.config.Settings`` mkdocstrings directive renders full field docs
    at build time, so this only guards the hand-written prose/examples against drift; actual
    field coverage is verified by the mkdocstrings directive itself at `tox -e docs` time.
    """
    cli_doc = (DOCS_DIR / "reference" / "cli.md").read_text()
    missing = [
        name for name in Settings.model_fields if name not in cli_doc and f"--{name.replace('_', '-')}" not in cli_doc
    ]
    assert not missing, f"Settings fields missing from reference/cli.md: {missing}"


def test_all_project_scripts_are_documented() -> None:
    """Every [project.scripts] entry point must be mentioned somewhere under docs/."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    scripts = pyproject["project"]["scripts"]
    all_docs_text = "\n".join(p.read_text() for p in DOCS_DIR.rglob("*.md"))
    undocumented = [name for name in scripts if not re.search(rf"\b{re.escape(name)}\b", all_docs_text)]
    assert not undocumented, f"[project.scripts] entries not documented anywhere: {undocumented}"
