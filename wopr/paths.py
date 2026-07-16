"""Repo-relative paths shared across wopr modules.

WOPR_QUESTIONS overrides the journal directory (used by tests and smoke runs
so they never touch the real journal).
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
CANDIDATE = SOURCES / "candidate"
DATA = ROOT / "data"
TABLES = DATA / "tables"
REGISTRY = DATA / "registry"
QUESTIONS = Path(os.environ.get("WOPR_QUESTIONS", ROOT / "questions"))
