"""Load repo-root .env into os.environ (no override). Imported for side effect.

Keeps ACLED credentials out of the repo and out of shell profiles; .env is
gitignored. Same pattern as JUDGMENT.
"""

import os
from pathlib import Path

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
