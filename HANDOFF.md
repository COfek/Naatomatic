# Naatomatic — handoff / continue-here

Pick up the project on any machine. **Naatomatic** is a Python + LangChain +
SQLAlchemy + SQLite, local, chat-based multi-agent system for managing the
**CombatAI** branch. Repo: <https://github.com/COfek/Naatomatic>

> Read `DESIGN.md` first — it's the single source of truth. `PROJECT_STRUCTURE.md`
> is the target layout. **`IMPLEMENTATION_GUIDE.md`** has the build contracts + the
> 4-person work split (read it before coding). This file is just how to get running.

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
- **`knowledge/`** — **real** branch content the General Knowledge agent serves (Hebrew, verbatim policy): `00-glossary` (Hebrew↔system-ID map), `01`-intro, `02`-open-networks, `03`-shift-readiness, `04`-infosec, `05`-fairness (derived from design), `06`-roles, `07`-site-procedures. Only the SmartBase/Kitbag URLs are real; `resources/weapon-carry-permit.md` is a **mock** file.
- **`models/`** also has `OrgUnit` (real Branch-300 departments/teams are seeded) + Personnel `team_id`/`phone`/`email`/`last_range_qualification` + `EquipmentItem.handover_pending` (Kitbag).

Everything above is green: 12/12 constraints pass, `pytest` 3 passed / 2 skipped. All
five agents (Network, Logistics, Guard Duty, AdHoc, General Knowledge) are **designed**
in `DESIGN.md`; the data/rules/knowledge for them exist, the agent *code* does not yet.

## 4. What's DESIGNED but NOT built yet (the actual agent)

All of this is scaffolded as empty packages (see `PROJECT_STRUCTURE.md`) — design is
complete, code is not written:
- **`data/services/`** — repository layer (the only thing that writes the DB; must auto-write AuditLog + EquipmentTransfer rows — R2-9).
- **`tools/`** — per-domain tools the model calls (network, logistics, guard_duty, adhoc, general_knowledge), each: validate (rules) → act (services) → return.
- **`agents/`** — the LangGraph node graph: Router → Worker → Tool Executor → Validator → Presenter.
- **`services/`** — LLM client, agent runtime, telemetry, auth (login by personal_number, role checks).
- **`mcp/server.py`** — exposes tools over MCP.
- **`scripts/maintenance.py`** — daily idempotent routine (formatting completion, shift/mission completion, leaver cleanup, **quarterly SUPPORT roster**, Keva year reset). NOTE: must NOT reset the Sadir burden pools.
- **`evaluation/`** — scored agent-scenario harness.

## 5. Suggested next step

Build **one domain end-to-end** to establish the pattern — **Logistics** is the most
self-contained, and it exercises the repository + tools + validator + the ticket
resolution flow (and knocks out R2-9 + the status-transition guard). Order:
1. `data/services/` repository for logistics (transactional, writes audit/transfer).
2. `tools/logistics_tools.py` — `create_equipment_request`, `resolve_ticket` (incl. the **Kitbag two-step handover** — set `handover_pending`, then recipient confirms), `sign`/`return`, `set_equipment_status`/`decommission_item` (with the §5 transition guard), all validated by `rules/`.
3. `tests/tools/` — hard-coded accept + reject path tests against the in-memory fixture.
4. Then wire it into the agent node graph.

## 6. Open decisions

**All design decisions are closed.** (AdHoc-for-Keva, the `שמור` classification
question, the role list, the knowledge content, the SmartBase/Kitbag URLs — all
resolved.) The only remaining items are **build-time code**, not decisions:
- **R2-5** — HC-GD-1/2 are end-of-year *targets* (enforced by the scheduler's planning), not snapshot invariants; tighten HC-GD-3 when the carryover code (R2-6) is built.
- **R2-9 / R2-8 / R2-6** — audit+transfer writes, the status-transition guard, and the carryover/year-reset math — all land with the repository/tools/maintenance code.
- *(Optional)* the `resources/weapon-carry-permit.md` is a mock — swap for the real document if/when available.

## 7. Conventions to keep in mind

- **Agent proposes, constraint engine decides** — hard rules live in `rules/` (service layer), never only in a tool.
- **No fabricated arguments** — the agent asks for missing required inputs; tools reject invented references; mistyped ids get a "did-you-mean" list (`DESIGN.md` §2).
- **Derive, don't duplicate** — e.g., port/wall-jack classification, formatting status.
- **Two Sadir burden pools** — `shifts_burden_points` (guard + ad-hoc) and `support_burden_points`, balanced independently; cumulative (never reset).
- Commit messages end with the Co-Authored-By line; `naatomatic.db` / `dashboard.html` / `.venv` stay git-ignored.

*Project memory (cross-session context) also lives in the assistant's memory file
`combatai-project.md`; this handoff mirrors the essentials.*
