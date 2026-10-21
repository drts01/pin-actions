"""Classify fetched repositories into corpus statistics."""

import csv
from dataclasses import asdict, dataclass, fields
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from pathlib import Path

import yamlrocks
from pin_actions._util import is_full_sha
from pin_actions.core import _collect_image_refs, _collect_refs, _is_local_action
from pin_actions.precommit import _collect_precommit_refs
from pin_actions.registry import is_image_digest

from .io import read_jsonl

_YAML_SUFFIXES = frozenset({".yml", ".yaml"})
_PRECOMMIT_NAMES = (".pre-commit-config.yaml", ".pre-commit-config.yml")
_PRECOMMIT_CI_MARKERS = (b"pre-commit/action@", b"pre-commit run", b"prek run", b"prek-action@")


@dataclass(slots=True)
class _Counts:
    """Accumulate mutable per-repository counts."""

    workflow_files: int = 0
    parse_errors: int = 0
    uses_total: int = 0
    uses_pinned: int = 0
    uses_dynamic: int = 0
    uses_local: int = 0
    image_total: int = 0
    image_mutable: int = 0
    image_dynamic: int = 0
    withref_total: int = 0
    withref_mutable: int = 0
    withref_dynamic: int = 0
    precommit_in_ci: bool = False
    precommit_total: int = 0
    precommit_mutable: int = 0


@dataclass(frozen=True, slots=True)
class RepoStats:
    """Represent one scanned repository as one row of the corpus CSV."""

    repo: str
    head_sha: str
    workflow_files: int
    parse_errors: int
    uses_total: int
    uses_pinned: int
    uses_dynamic: int
    uses_local: int
    fully_pinned: bool
    image_total: int
    image_mutable: int
    image_dynamic: int
    withref_total: int
    withref_mutable: int
    withref_dynamic: int
    precommit_in_ci: bool
    precommit_total: int
    precommit_mutable: int


def _is_dynamic(value: str) -> bool:
    """Check whether a value contains a GitHub Actions expression."""
    return "${{" in value


class _ReadOnlyDocument:
    """Expose PyYAML values through the walk interface used by the collectors."""

    def __init__(self, value: Any) -> None:  # noqa: ANN401
        self.value = value

    def walk(self) -> list[tuple[tuple[str | int, ...], Any]]:
        """Visit scalar values and their paths without modifying the source YAML."""
        items: list[tuple[tuple[str | int, ...], Any]] = []

        def visit(value: Any, path: tuple[str | int, ...]) -> None:  # noqa: ANN401
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, (*path, key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, (*path, index))
            else:
                items.append((path, value))

        visit(self.value, ())
        return items

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401
        """Allow the pre-commit collector to inspect ``repos``."""
        return self.value[key]


def _load_doc(path: Path) -> Any | None:  # noqa: ANN401
    """Parse YAML for analysis, falling back when yamlrocks rejects valid corpus YAML."""
    content = path.read_bytes()
    try:
        doc = yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)
        if isinstance(doc, yamlrocks.YAMLRocksDocument):
            return doc
    except Exception:  # noqa: BLE001 -- arbitrary corpus files may fail in any parser layer
        doc = None
    try:
        return _ReadOnlyDocument(yaml.load(content, Loader=yaml.BaseLoader))
    except yaml.YAMLError, UnicodeError:
        return None


def _count_local_uses(doc: Any) -> int:  # noqa: ANN401
    """Count local action references, which are out of scope rather than unpinned."""
    return sum(
        1
        for item_path, value in doc.walk()
        if item_path and item_path[-1] == "uses" and isinstance(value, str) and value.startswith(("./", "$/"))
    )


def _scan_workflow(doc: Any, counts: _Counts) -> None:  # noqa: ANN401
    """Fold one workflow or action definition into an accumulator."""
    counts.uses_local += _count_local_uses(doc)

    for _path, repo, ref, is_uses in _collect_refs(doc):
        if is_uses:
            if _is_local_action(repo):
                continue
            if _is_dynamic(repo) or _is_dynamic(ref):
                counts.uses_dynamic += 1
            else:
                counts.uses_total += 1
                if is_full_sha(ref):
                    counts.uses_pinned += 1
        elif _is_dynamic(ref):
            counts.withref_dynamic += 1
        else:
            counts.withref_total += 1
            if not is_full_sha(ref):
                counts.withref_mutable += 1

    for _path, image, tag in _collect_image_refs(doc):
        if _is_dynamic(image) or _is_dynamic(tag):
            counts.image_dynamic += 1
        else:
            counts.image_total += 1
            if not is_image_digest(tag):
                counts.image_mutable += 1


def _scan_precommit(doc: Any, counts: _Counts) -> None:  # noqa: ANN401
    """Fold one pre-commit configuration into an accumulator."""
    for _path, _repo, rev, _is_uses in _collect_precommit_refs(doc, host="github.com"):
        counts.precommit_total += 1
        if not is_full_sha(rev):
            counts.precommit_mutable += 1


def _workflow_paths(root: Path) -> list[Path]:
    """Collect workflow files and action definitions under a repository root."""
    paths: list[Path] = []
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        paths.extend(sorted(path for path in workflows.iterdir() if path.is_file() and path.suffix in _YAML_SUFFIXES))
    actions = root / ".github" / "actions"
    if actions.is_dir():
        paths.extend(
            sorted(path for path in actions.rglob("action.*") if path.is_file() and path.suffix in _YAML_SUFFIXES)
        )
    paths.extend(sorted(path for path in root.glob("action.*") if path.is_file() and path.suffix in _YAML_SUFFIXES))
    return paths


def scan_repo(repo: str, head_sha: str, root: Path) -> RepoStats:
    """Classify one cloned repository into a corpus row."""
    counts = _Counts()
    workflow_blobs: list[bytes] = []

    for path in _workflow_paths(root):
        counts.workflow_files += 1
        doc = _load_doc(path)
        if doc is None:
            counts.parse_errors += 1
            continue
        workflow_blobs.append(path.read_bytes())
        _scan_workflow(doc, counts)

    counts.precommit_in_ci = any(marker in blob for blob in workflow_blobs for marker in _PRECOMMIT_CI_MARKERS)

    precommit = next((root / name for name in _PRECOMMIT_NAMES if (root / name).is_file()), None)
    if precommit is not None:
        doc = _load_doc(precommit)
        if doc is None:
            counts.parse_errors += 1
        else:
            _scan_precommit(doc, counts)

    return RepoStats(
        repo=repo,
        head_sha=head_sha,
        fully_pinned=counts.uses_total > 0 and counts.uses_pinned == counts.uses_total,
        workflow_files=counts.workflow_files,
        parse_errors=counts.parse_errors,
        uses_total=counts.uses_total,
        uses_pinned=counts.uses_pinned,
        uses_dynamic=counts.uses_dynamic,
        uses_local=counts.uses_local,
        image_total=counts.image_total,
        image_mutable=counts.image_mutable,
        image_dynamic=counts.image_dynamic,
        withref_total=counts.withref_total,
        withref_mutable=counts.withref_mutable,
        withref_dynamic=counts.withref_dynamic,
        precommit_in_ci=counts.precommit_in_ci,
        precommit_total=counts.precommit_total,
        precommit_mutable=counts.precommit_mutable,
    )


def scan_corpus(manifest: Path, cache: Path, out: Path, *, limit: int | None = None) -> int:
    """Scan every successfully cloned repository in a manifest into a CSV.

    Args:
        manifest: JSON Lines manifest produced by the fetch stage.
        cache: Root directory holding the clones.
        out: Destination CSV path.
        limit: Optional cap on repositories scanned.

    Returns:
        Number of rows written.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    field_names = [field.name for field in fields(RepoStats)]
    written = 0

    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names)
        writer.writeheader()
        for row in read_jsonl(manifest):
            if not row.get("ok"):
                continue
            stats = scan_repo(row["repo"], row["head_sha"], cache / row["repo"])
            writer.writerow(
                {key: int(value) if isinstance(value, bool) else value for key, value in asdict(stats).items()}
            )
            written += 1
            if limit is not None and written >= limit:
                break
    return written
