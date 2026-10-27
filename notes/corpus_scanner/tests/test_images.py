# ruff: noqa: S101
"""Tests for the mutable-image listing stage."""

import csv
from typing import TYPE_CHECKING

import pytest
from notes.corpus_scanner.images import (
    MutableImage,
    read_images,
    repos_per_image,
    repos_per_kind,
    repos_per_shape,
    tag_shape,
    write_images,
)
from notes.corpus_scanner.scan import list_mutable_images

if TYPE_CHECKING:
    from pathlib import Path

    from notes.corpus_scanner.images import TagShape

_SHA = "a" * 40
_DIGEST = "b" * 64
_COLUMNS = (
    "repo,head_sha,workflow_files,parse_errors,uses_total,uses_pinned,uses_dynamic,uses_local,fully_pinned,"
    "image_total,image_mutable,image_dynamic,withref_total,withref_mutable,withref_dynamic,"
    "precommit_in_ci,precommit_total,precommit_mutable"
)


def _row(repo: str, *, fully_pinned: int = 1, uses_dynamic: int = 0, image_mutable: int = 1) -> str:
    return f"{repo},{_SHA},1,0,1,{fully_pinned},{uses_dynamic},0,{fully_pinned},2,{image_mutable},0,0,0,0,0,0,0"


def _workflow(cache: Path, repo: str) -> None:
    workflows = cache / repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        f"""jobs:
  test:
    container: python:3.14-slim
    services:
      redis:
        image: redis@sha256:{_DIGEST}
      db:
        image: ${{{{ matrix.db }}}}
    steps:
      - uses: actions/checkout@{_SHA}
      - uses: docker://ghcr.io/owner/tool
""",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("tag", "shape"),
    [
        ("latest", "latest"),
        ("7", "major"),
        ("20-alpine", "major"),
        ("3.14-slim", "minor"),
        ("v1.27.3", "patch"),
        ("lts", "named"),
        ("bookworm", "named"),
        ("1.2.3.4", "named"),
    ],
)
def test_tag_shape_ignores_variant_suffixes(tag: str, shape: TagShape) -> None:
    """Classify tags by the version before the first hyphen."""
    assert tag_shape(tag) == shape


def test_list_mutable_images_reads_only_pinned_repositories_with_an_image_gap(tmp_path: Path) -> None:
    """Skip unpinned, dynamic, and gap-free repositories, and skip digest and expression images."""
    cache = tmp_path / "repos"
    for repo in ("owner/gap", "owner/unpinned", "owner/dynamic", "owner/clean"):
        _workflow(cache, repo)
    corpus = tmp_path / "corpus.csv"
    corpus.write_text(
        "\n".join(
            (
                _COLUMNS,
                _row("owner/gap"),
                _row("owner/unpinned", fully_pinned=0),
                _row("owner/dynamic", uses_dynamic=1),
                _row("owner/clean", image_mutable=0),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    images = list_mutable_images(corpus, cache)

    assert images == [
        MutableImage("owner/gap", ".github/workflows/ci.yml", "container", "python", "3.14-slim", "minor"),
        MutableImage("owner/gap", ".github/workflows/ci.yml", "step", "owner/tool", "latest", "latest"),
    ]


def test_images_round_trip_and_count_distinct_repositories(tmp_path: Path) -> None:
    """Count each repository once per image and per shape, after a CSV round trip."""
    images = [
        MutableImage("owner/a", "x.yml", "service", "redis", "7", "major"),
        MutableImage("owner/a", "y.yml", "service", "redis", "7", "major"),
        MutableImage("owner/b", "x.yml", "service", "redis", "latest", "latest"),
        MutableImage("owner/b", "x.yml", "container", "postgres", "16", "major"),
    ]
    out = tmp_path / "images.csv"

    write_images(images, out)

    with out.open(encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == ["repo", "path", "kind", "image", "tag", "shape"]
    restored = read_images(out)
    assert restored == images
    assert repos_per_image(restored) == {"redis": 2, "postgres": 1}
    assert repos_per_shape(restored) == {"major": 2, "latest": 1}
    assert repos_per_kind(restored) == {"service": 2, "container": 1}
