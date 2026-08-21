#!/usr/bin/env -S uv run --with-editable . --script
"""Thin shim: pin-precommit console entry point, runnable as a standalone uv script."""

from pin_actions.precommit import main

if __name__ == "__main__":
    main()
