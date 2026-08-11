"""Semver-aware tag selection for --update-to-latest-major/--update-to-latest-minor."""

from packaging.version import InvalidVersion, Version


def parse_tag_version(tag: str) -> Version | None:
    """Parse a tag name as a semver or CalVer ``Version``, tolerating a leading 'v'.

    Supports:
    - Semver: ``v1.2.3``, ``1.2.3-rc1``
    - CalVer: ``2023.10.15``, ``2023-10-15`` (dash → dot conversion), ``2023.1.5``
    - Unparseable: branches like ``main``, ``nightly`` → None (fallback to hash re-resolve)

    Returns:
        Parsed version, or None if ``tag`` isn't a valid version.
    """
    candidate = tag[1:] if tag.lower().startswith("v") and len(tag) > 1 else tag
    try:
        return Version(candidate)
    except InvalidVersion:
        # Retry with dash-separated CalVer (e.g., 2024-05-01 → 2024.05.01)
        if "-" in candidate:
            try:
                return Version(candidate.replace("-", "."))
            except InvalidVersion:
                pass
        return None


def _render_tag(version: Version, precision: int, prefix: str) -> str:
    """Format ``version`` using ``precision`` dot-separated components and ``prefix``.

    Truncates (or zero-pads, if the winning tag has fewer components than the
    original) ``version.release`` to ``precision`` entries, so the rewritten
    comment matches the precision of the tag it's replacing (e.g. a 'v4'
    comment stays major-only even if the winning remote tag is 'v9.1.2').
    """
    release = version.release
    parts = release[:precision] if len(release) >= precision else (*release, *([0] * (precision - len(release))))
    return prefix + ".".join(str(p) for p in parts)


def select_latest_tag(
    tags: list[tuple[str, str]],
    current_tag: str,
    *,
    latest_patch: bool = False,
    latest_minor: bool = False,
    latest_major: bool = False,
    full_version: bool = False,
) -> tuple[str, str] | None:
    """Pick the highest-version tag satisfying the constraint relative to ``current_tag``.

    - ``latest_major``: no constraint — the single highest semver tag on the
      remote repo wins, even if it's a different major version (e.g. v4.0.5 -> v9.1.2).
    - ``latest_minor``: constrained to the same major version as ``current_tag``
      (e.g. v4.0.5 -> v4.9.0, never v5.x).
    - ``latest_patch``: constrained to the same major.minor as ``current_tag``
      (e.g. v4.2.3 -> v4.2.9, never v4.3.x).

    When multiple are set, narrower constraint wins: patch > minor > major.
    The returned tag name preserves the precision (number of dot-separated
    version components) and 'v'-prefix style of ``current_tag`` — e.g. a 'v4'
    comment stays 'v9' even though the winning remote tag is 'v9.1.2'.
    If ``full_version`` is True, uses the full precision of the winning tag instead.

    Args:
        tags: All (tag_name, commit_sha) pairs available on the remote repo.
        current_tag: The tag currently recorded for this pin (defines the
            constraint window and the output precision/prefix).
        latest_patch: Constrain candidates to the same major.minor version.
        latest_minor: Constrain candidates to the same major version.
        latest_major: No constraint — consider every semver tag on the repo.
        full_version: If True, use the full precision of the winning tag instead
            of truncating to match ``current_tag``'s precision.

    Returns:
        (tag_name, commit_sha) of the winning tag, re-rendered to match
        ``current_tag``'s precision (or full precision if ``full_version`` is True),
        or None if no constraint is set, ``current_tag`` isn't a valid version,
        or no candidate satisfies the constraint.
    """
    if not latest_patch and not latest_minor and not latest_major:
        return None

    current = parse_tag_version(current_tag)
    if current is None:
        return None

    precision = len(current.release)
    candidates: list[tuple[Version, str, str]] = []
    for name, sha in tags:
        version = parse_tag_version(name)
        if version is None:
            continue
        if not latest_major and version.major != current.major:
            continue
        if latest_patch and precision >= 2 and version.minor != current.minor:
            continue
        candidates.append((version, name, sha))

    if not candidates:
        return None

    best_version, _best_name, best_sha = max(candidates, key=lambda c: c[0])
    prefix = current_tag[0] if current_tag[:1].lower() == "v" and len(current_tag) > 1 else ""
    output_precision = len(best_version.release) if full_version else precision
    return _render_tag(best_version, output_precision, prefix), best_sha
