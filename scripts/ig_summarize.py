#!/usr/bin/env python3
"""Run ig-summarize from a git clone (adds repo root to sys.path)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ig_summarize.app import entrypoint

if __name__ == "__main__":
    entrypoint()
