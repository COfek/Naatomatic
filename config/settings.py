"""Central settings — model ids, DB path, domain constants. (Template stub.)

Domain constants currently live in models/enums.py (DEPOT_PERSONAL_NUMBER,
FORMATTING_DURATION_DAYS). As the agent layer lands, app-level config (model id,
reasoning effort, db path override) is centralized here.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Default SQLite database (mirrors models.db.DEFAULT_DB_PATH).
DB_PATH = Path(__file__).resolve().parent.parent / "naatomatic.db"

OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
DEFAULT_LLM_MODEL: str = "deepseek/deepseek-v4-pro"

# --- Dashboard / chart rendering ---
CHARTS_DIR: Path = Path(__file__).resolve().parent.parent / "static" / "charts"
CHARTS_BASE_URL: str = "http://localhost:8000"
CHARTS_TTL_HOURS: float = 24.0
CHART_DPI: int = 120

# Equipment shortage demand policy — used when no open tickets exist for a category.
# Replace with a dedicated DB policy table if per-classification quotas are needed later.
MONITOR_DEMAND_PER_PERSON: float = 1.0    # each active person requires 1 monitor
COMPUTER_DEMAND_PER_PERSON: float = 0.25  # each active person requires ~0.25 computers

CHART_STYLE: dict = {
    "fig_facecolor":  "#1a1a2e",
    "ax_facecolor":   "#16213e",
    "text_color":     "white",
    "tick_color":     "#cfd8dc",
    "grid_color":     "#37474f",
    "spine_color":    "#37474f",
    "colors":         ["#4fc3f7", "#ef9a9a", "#a5d6a7", "#ffcc80", "#ce93d8"],
    "shortage_color": "#ef5350",
    "surplus_color":  "#66bb6a",
}
