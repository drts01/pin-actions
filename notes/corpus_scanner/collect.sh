#!/usr/bin/env bash
#
# Collect the SCaLE 24x corpus in three stages: frame, pilot, full.
#
# The pilot is a strict subsample of the full run. `select_sample()` shuffles the frame once with a fixed seed and
# takes a prefix, so raising --sample only adds repositories. Every clone the pilot creates is reused by the full
# run instead of discarded.
#
# Resource estimates
# ------------------
# Derived from blobless depth-1 sparse clones (commit + HEAD tree + blobs under the sparse cone), measured at
# roughly 1.1 MB and 2.5 s per repository. Override PER_REPO_KB once the pilot reports real numbers.
#
#   stage   repositories   wall clock        disk
#   -----   ------------   ---------------   --------
#   frame   n/a            90-120 min        < 20 MB
#   pilot   2,000          7-12 min          ~2.2 GB
#   full    50,000         3.5-5 h           ~55 GB
#   scan    50,000         10-25 min         < 50 MB  (local, CPU bound)
#   report  n/a            seconds           < 1 MB
#
# Disk checks below require the estimate plus 10% headroom on the filesystem holding the clone cache.
#
# Rate limits
# -----------
# The token is used only by the `frame` stage, which calls the GitHub search API (30 req/min authenticated).
# Clones in `fetch` are unauthenticated HTTPS and are not charged against the REST quota, but GitHub applies
# secondary rate limiting per IP; concurrency is kept deliberately low for the multi-hour full run.
#
# Usage
# -----
#   notes/corpus_scanner/collect.sh frame    # build the sampling frame (run once)
#   notes/corpus_scanner/collect.sh pilot    # 2,000 repos: size the full run from measured rates
#   notes/corpus_scanner/collect.sh full     # 50,000 repos: the published corpus
#   notes/corpus_scanner/collect.sh report   # re-aggregate without refetching
#
# All stages are resumable. Re-running `fetch` skips any repository that already has a clone.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# --- Parameters. Record every one of these on the methodology slide. ---------------------------------------------

GH_ACCOUNT="${GH_ACCOUNT:-drts01}"
MIN_STARS="${MIN_STARS:-100}"
MAX_STARS="${MAX_STARS:-500000}"
PUSHED_SINCE="${PUSHED_SINCE:-2026-04-01}"
SEED="${SEED:-20260401}"
PILOT_SIZE="${PILOT_SIZE:-2000}"
FULL_SIZE="${FULL_SIZE:-50000}"
PILOT_CONCURRENCY="${PILOT_CONCURRENCY:-12}"
FULL_CONCURRENCY="${FULL_CONCURRENCY:-10}"
TIMEOUT="${TIMEOUT:-45}"

VERBOSE="${VERBOSE:-2}"

# Mean on-disk size of one blobless depth-1 sparse clone, in KiB. Recompute after the pilot:
#   du -sk notes/corpus/repos | awk '{print $1 / 2000}'
PER_REPO_KB="${PER_REPO_KB:-1100}"

OUT_DIR="${OUT_DIR:-notes/corpus}"
FRAME="$OUT_DIR/frame.jsonl"
CACHE="$OUT_DIR/repos"
MANIFEST="$CACHE/manifest.jsonl"

# --- Helpers -----------------------------------------------------------------------------------------------------

log() { printf '==> %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

require_tools() {
  for tool in uv git gh awk df; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is not on PATH"
  done
}

# Resolve the GitHub token. Never echoed, never written to an artifact.
export_token() {
  local token
  token="$(gh auth token --user "$GH_ACCOUNT")" || die "gh auth token --user $GH_ACCOUNT failed; run: gh auth login"
  [ -n "$token" ] || die "gh returned an empty token for $GH_ACCOUNT"
  export GITHUB_TOKEN="$token"
  log "token resolved for $GH_ACCOUNT (not displayed)"
}

# require_space <repositories> — abort unless the cache filesystem holds the estimate plus 10%.
require_space() {
  local repos="$1" need_kb avail_kb
  mkdir -p "$CACHE"
  need_kb=$(( repos * PER_REPO_KB * 110 / 100 ))
  avail_kb="$(df -Pk "$CACHE" | awk 'NR == 2 { print $4 }')"
  [ -n "$avail_kb" ] || die "could not read free space for $CACHE"

  awk -v need="$need_kb" -v avail="$avail_kb" -v repos="$repos" 'BEGIN {
    printf "==> disk: need %.1f GiB for %d repos (incl. 10%% headroom), %.1f GiB free\n",
      need / 1048576, repos, avail / 1048576 > "/dev/stderr"
  }'
  [ "$avail_kb" -ge "$need_kb" ] || die "insufficient disk space on the filesystem holding $CACHE"

  # Several million small files otherwise pin mds_stores for hours on macOS.
  touch "$CACHE/.metadata_never_index"
}

require_frame() {
  [ -s "$FRAME" ] || die "no frame at $FRAME; run: ${BASH_SOURCE[0]} frame"
}

# --- Stages ------------------------------------------------------------------------------------------------------

stage_frame() {
  export_token
  mkdir -p "$OUT_DIR"
  log "frame: stars $MIN_STARS..$MAX_STARS pushed after $PUSHED_SINCE (estimated 90-120 min)"

  uv run --group corpus python -m notes.corpus_scanner -v "$VERBOSE" frame \
    --min-stars "$MIN_STARS" \
    --max-stars "$MAX_STARS" \
    --pushed-since "$PUSHED_SINCE" \
    --out "$FRAME" 2>&1 | tee "$OUT_DIR/frame.log"

  # Star-band bisection cannot split a singleton band, so dense bands at the floor silently truncate at GitHub's
  # 1000-result cap. Disclose any hit on the methodology slide.
  if grep -q 'truncating to' "$OUT_DIR/frame.log"; then
    log "WARNING: search result cap hit; these bands are incomplete:"
    grep 'truncating to' "$OUT_DIR/frame.log" >&2
  fi

  log "frame: $(wc -l < "$FRAME" | tr -d ' ') repositories -> $FRAME"
}

# fetch_and_scan <size> <concurrency> <corpus-csv> <label>
fetch_and_scan() {
  local size="$1" concurrency="$2" corpus="$3" label="$4"

  require_frame
  require_space "$size"
  log "$label: cloning $size repositories at concurrency $concurrency"

  uv run --group corpus python -m notes.corpus_scanner -v "$VERBOSE" fetch \
    --frame "$FRAME" \
    --cache "$CACHE" \
    --sample "$size" \
    --seed "$SEED" \
    --concurrency "$concurrency" \
    --timeout "$TIMEOUT"

  cp "$MANIFEST" "$OUT_DIR/manifest-$label.jsonl"

  log "$label: scanning clones"
  uv run --group corpus python -m notes.corpus_scanner -v "$VERBOSE" scan --cache "$CACHE" --out "$corpus"

  log "$label: report"
  uv run --group corpus python -m notes.corpus_scanner report --csv "$corpus" --exclude-dynamic \
    --out "$OUT_DIR/report-$label.md"
  cat "$OUT_DIR/report-$label.md"
}

stage_pilot() {
  fetch_and_scan "$PILOT_SIZE" "$PILOT_CONCURRENCY" "$OUT_DIR/corpus-pilot.csv" pilot
  cat >&2 <<'EOF'

==> Pilot complete. The report's "Sizing the full run" section states the measured rates and the sample size
    that `Z` requires. Compare that figure against "repos" in notes/corpus/frame.meta.json before proceeding:
      - below the frame size -> set FULL_SIZE to it
      - above the frame size -> `Z` is unreachable at this frame; lower MIN_STARS or drop `Z`,
        and size the full run off the headline interval instead (50,000 puts N near 4,200, +/- 1.0 points)
    Then recompute the disk estimate from the measured clone size:
      PER_REPO_KB=$(du -sk notes/corpus/repos | awk '{print int($1 / 2000)}')
    Re-run with the SAME SEED so the pilot clones are reused:
      FULL_SIZE=... PER_REPO_KB=... notes/corpus_scanner/collect.sh full
EOF
}

stage_full() {
  fetch_and_scan "$FULL_SIZE" "$FULL_CONCURRENCY" "$OUT_DIR/corpus.csv" full
  cat >&2 <<EOF

==> Full collection complete. Publish, per the methodology commitment:
      $FRAME
      $OUT_DIR/frame.meta.json
      $OUT_DIR/sample.jsonl        (the sampled repositories; seed $SEED)
      $OUT_DIR/manifest-full.jsonl (per-repository HEAD SHAs, pinning the snapshot)
      $OUT_DIR/corpus.csv
    Check the failure rate before trusting the denominator:
      grep -c '"ok": false' $OUT_DIR/manifest-full.jsonl
    The clones under $CACHE are reproducible from the manifest and may be deleted.
EOF
}

stage_report() {
  [ -s "$OUT_DIR/corpus.csv" ] || die "no corpus at $OUT_DIR/corpus.csv"
  uv run --group corpus python -m notes.corpus_scanner report --csv "$OUT_DIR/corpus.csv" --exclude-dynamic
}

# --- Dispatch ----------------------------------------------------------------------------------------------------

require_tools

case "${1:-}" in
  frame)  stage_frame ;;
  pilot)  stage_pilot ;;
  full)   stage_full ;;
  report) stage_report ;;
  *)      die "usage: ${BASH_SOURCE[0]} {frame|pilot|full|report}" ;;
esac
