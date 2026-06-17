# Naatomatic — handoff / continue-here

Pick up the project on any machine. **Naatomatic** is a Python + LangChain +
SQLAlchemy + SQLite, local, chat-based multi-agent system for managing the
**CombatAI** branch. Repo: <https://github.com/COfek/Naatomatic>

> Read `DESIGN.md` first — it's the single source of truth. `PROJECT_STRUCTURE.md`
> is the target layout. This file is just how to get running and what's next.

---

## 1. Get set up (fresh machine)

```powershell
git clone https://github.com/COfek/Naatomatic.git
cd Naatomatic
py -3 -m venv .venv                       # Python 3.13 used; 3.11+ fine
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
(macOS/Linux: `python3 -m venv .venv` then `.venv/bin/python -m pip install -r requirements.txt`.)

The `.venv` is **per-machine** — it's git-ignored, so recreate it (above) after
cloning; don't copy it across machines.

## 2. Run things

Use the venv's python (`.\.venv\Scripts\python.exe` on Windows, `.venv/bin/python` elsewhere).

```powershell
# Generate a valid random database (configurable size; --seed for reproducibility)
python -m data.generation.generate_data 30 --seed 42

# Verify every hard constraint (currently 12 checks) — exits non-zero on any violation
python scripts/verify.py

# Run the tests
python -m pytest -q

# Build the visual dashboard -> opens as dashboard.html in a browser
python scripts/dashboard.py

# Terminal summary of the data
python -m data.generation.inspect_data
```
`naatomatic.db` and `dashboard.html` are git-ignored — regenerate them; never commit.

For raw table browsing, open `naatomatic.db` in **DB Browser for SQLite**
(`winget install --id DBBrowserForSQLite.DBBrowserForSQLite`).

## 3. What's BUILT and working

- **`models/`** — SQLAlchemy data layer: `tables.py` (all entities), `enums.py`, `db.py`.
- **`rules/constraints.py`** — the constraint engine: 12 hard checks (HC-NET-1/2, HC-LOG-1/2, HC-GD-0/3/5/6/7/8/9, DEPOT, STATUS) + `run_all`.
- **`data/generation/`** — `generate_data.py` (valid random data, respects all rules) + `inspect_data.py`.
- **`scripts/`** — `verify.py`, `dashboard.py`.
- **`tests/`** — `conftest.py` (in-memory seeded fixture) + `unit/` smoke tests (passing); `tools/` + `agents/` are placeholders.
- **`knowledge/`** — markdown the General Knowledge agent will serve (4 docs are **DRAFT placeholders** to replace with real branch content; `05-fairness-explained` is authoritative).

Everything above is green: 12/12 constraints pass, `pytest` 3 passed / 2 skipped.

## 4. What's DESIGNED but NOT built yet (the actual agent)

All of this is scaffolded as empty packages (see `PROJECT_STRUCTURE.md`) — design is
complete, code is not written:
- **`data/services/`** — repository layer (the only thing that writes the DB; must auto-write AuditLog + EquipmentTransfer rows — R2-9).
- **`tools/`** — per-pillar tools the model calls (network, logistics, guard_duty, adhoc, general_knowledge), each: validate (rules) → act (services) → return.
- **`agents/`** — the LangGraph node graph: Router → Worker → Tool Executor → Validator → Presenter.
- **`services/`** — LLM client, agent runtime, telemetry, auth (login by personal_number, role checks).
- **`mcp/server.py`** — exposes tools over MCP.
- **`scripts/maintenance.py`** — daily idempotent routine (formatting completion, shift/mission completion, leaver cleanup, **quarterly SUPPORT roster**, Keva year reset). NOTE: must NOT reset the Sadir burden pools.
- **`evaluation/`** — scored agent-scenario harness.

## 5. Suggested next step

Build **one pillar end-to-end** to establish the pattern — **Logistics** is the most
self-contained, and it exercises the repository + tools + validator + the ticket
resolution flow (and knocks out R2-9 + the status-transition guard). Order:
1. `data/services/` repository for logistics (transactional, writes audit/transfer).
2. `tools/logistics_tools.py` — `create_equipment_request`, `resolve_ticket`, `sign`/`return`, `set_equipment_status`/`decommission_item` (with the §5 transition guard), all validated by `rules/`.
3. `tests/tools/` — hard-coded accept + reject path tests against the in-memory fixture.
4. Then wire it into the agent node graph.

## 6. Open decisions still pending (small)

- **AdHoc-for-Keva** (`DESIGN.md` §7 ❓OPEN) — recommendation noted: assignable to both, burden-tracked for Keva but outside the 2/4 quota. Confirm.
- **Knowledge content** — replace the 4 draft docs in `knowledge/` with real branch material (intro, procedure, infosec) + the real SmartBase URL and weapon-safety file.
- **R2-5** — HC-GD-1/2 are end-of-year *targets* (enforced by the scheduler's planning), not snapshot invariants; tighten HC-GD-3 when the carryover code is built.

## 7. Conventions to keep in mind

- **Agent proposes, constraint engine decides** — hard rules live in `rules/` (service layer), never only in a tool.
- **No fabricated arguments** — the agent asks for missing required inputs; tools reject invented references; mistyped ids get a "did-you-mean" list (`DESIGN.md` §2).
- **Derive, don't duplicate** — e.g., port/wall-jack classification, formatting status.
- **Two Sadir burden pools** — `shifts_burden_points` (guard + ad-hoc) and `support_burden_points`, balanced independently; cumulative (never reset).
- Commit messages end with the Co-Authored-By line; `naatomatic.db` / `dashboard.html` / `.venv` stay git-ignored.

*Project memory (cross-session context) also lives in the assistant's memory file
`combatai-project.md`; this handoff mirrors the essentials.*
