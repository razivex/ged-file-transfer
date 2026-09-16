"""
GED file transfer entrypoint.

Origin: DOWNLOAD_DIR   Destiny: DEST_DIR
Credentials: ged-file-transfer/.env (gitignored). See AGENTS.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ged_transfer.pipeline import main

if __name__ == "__main__":
    main()
