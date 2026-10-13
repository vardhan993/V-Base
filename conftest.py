"""Repository-root pytest configuration.

`backend/src` is added to sys.path so tests can import the `nexus` package
without an editable install, and `tests/backend` sits beside it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for path in (ROOT, ROOT / "backend" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
