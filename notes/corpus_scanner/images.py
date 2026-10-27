"""Describe the mutable container images behind the residual-surface statistic.

The corpus CSV stores counts only; ``scan.list_mutable_images`` re-reads the clones of fully pinned repositories
and records each mutable image reference, so slides can show which images float and how.
This module stays standard-library only so the slides can import it without the scanner's dependencies.
"""

import csv
import re
from collections import Counter
from dataclasses import astuple, dataclass, fields
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from pathlib import Path

type TagShape = Literal["latest", "major", "minor", "patch", "named"]
type ImageKind = Literal["service", "container", "step"]

_VERSION = re.compile(r"v?\d+(\.\d+)?(\.\d+)?")


def tag_shape(tag: str) -> TagShape:
    """Classify an image tag by how far it can move.

    The version is read from the text before the first ``-``, so variant suffixes such as
    ``-slim`` or ``-alpine`` do not change the shape.

    Args:
        tag: Image tag; an omitted tag is ``latest``.

    Returns:
        ``latest``; ``major`` (``20``), ``minor`` (``3.14``), or ``patch`` (``1.27.3``) for numeric versions;
        ``named`` for anything else, such as ``lts`` or ``bookworm``.

    Example:
        >>> [tag_shape(tag) for tag in ("latest", "20-alpine", "3.14-slim", "v1.27.3", "lts")]
        ['latest', 'major', 'minor', 'patch', 'named']
    """
    if tag == "latest":
        return "latest"
    match = _VERSION.fullmatch(tag.partition("-")[0])
    if match is None:
        return "named"
    if match[2]:
        return "patch"
    return "minor" if match[1] else "major"


def image_kind(item_path: tuple[object, ...]) -> ImageKind:
    """Name where an image reference sits in a workflow.

    Args:
        item_path: Path returned by ``pinref.core._collect_image_refs``.

    Returns:
        ``service`` for ``services.<name>.image``, ``step`` for ``uses: docker://``,
        and ``container`` for the job container in either form.

    Example:
        >>> image_kind(("jobs", "test", "services", "db", "image"))
        'service'
    """
    match item_path:
        case (*_, "services", _, "image"):
            return "service"
        case (*_, "uses"):
            return "step"
        case _:
            return "container"


@dataclass(frozen=True, slots=True)
class MutableImage:
    """One mutable image reference in a fully ``uses:``-pinned repository.

    Attributes:
        repo: Repository full name.
        path: Workflow or action file, relative to the repository root.
        kind: Result of :func:`image_kind`.
        image: Image name without registry; Docker Hub official images drop ``library/``.
        tag: Tag as written, or ``latest`` when omitted.
        shape: Result of :func:`tag_shape`.
    """

    repo: str
    path: str
    kind: ImageKind
    image: str
    tag: str
    shape: TagShape


def write_images(images: list[MutableImage], out: Path) -> None:
    """Write image references to a CSV with one row per reference."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(field.name for field in fields(MutableImage))
        writer.writerows(astuple(image) for image in images)


def read_images(csv_path: Path) -> list[MutableImage]:
    """Read image references written by :func:`write_images`."""
    with csv_path.open(encoding="utf-8", newline="") as handle:
        return [
            MutableImage(
                repo=row["repo"],
                path=row["path"],
                kind=cast("ImageKind", row["kind"]),
                image=row["image"],
                tag=row["tag"],
                shape=cast("TagShape", row["shape"]),
            )
            for row in csv.DictReader(handle)
        ]


def repos_per_image(images: list[MutableImage]) -> Counter[str]:
    """Count distinct repositories referencing each image by a mutable tag."""
    return Counter(image for image, _repo in {(item.image, item.repo) for item in images})


def repos_per_shape(images: list[MutableImage]) -> Counter[TagShape]:
    """Count distinct repositories with at least one mutable reference of each tag shape."""
    return Counter(shape for shape, _repo in {(item.shape, item.repo) for item in images})


def repos_per_kind(images: list[MutableImage]) -> Counter[ImageKind]:
    """Count distinct repositories with at least one mutable image of each kind."""
    return Counter(kind for kind, _repo in {(item.kind, item.repo) for item in images})
