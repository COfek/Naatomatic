"""Central settings — model ids, DB path, domain constants. (Template stub.)

Domain constants currently live in models/enums.py (DEPOT_PERSONAL_NUMBER,
FORMATTING_DURATION_DAYS). As the agent layer lands, app-level config (model id,
reasoning effort, db path override) is centralized here.
"""

from __future__ import annotations

from pathlib import Path

# Default SQLite database (mirrors models.db.DEFAULT_DB_PATH).
DB_PATH = Path(__file__).resolve().parent.parent / "naatomatic.db"

# LLM_MODEL = "claude-opus-4-8"   # wired when the agent/services layer is built
