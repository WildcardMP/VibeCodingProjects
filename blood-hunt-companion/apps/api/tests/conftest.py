"""Pytest path config — make `app` importable without installing the package."""

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent.parent
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(REPO_ROOT))
