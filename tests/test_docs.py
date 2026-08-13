"""Guard against drift between zensical.toml nav and docs/ on disk."""

import tomllib
from pathlib import Path

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
