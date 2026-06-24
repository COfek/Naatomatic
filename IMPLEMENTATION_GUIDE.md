# Implementation guide — building Naatomatic with 4 people

Goal: four people build in parallel and the code **fits together** because everyone
codes against the **same contracts**. Read this + `DESIGN.md` (the spec) before
writing code. The skeleton already compiles and tests pass — fill in the bodies.

## Layers (dependencies point one way — never upward)

```
models/        data shapes (tables, enums, db)          ← done
rules/         constraint engine (HC-* checks)           ← done (12 checks)
data/services/ repositories: the ONLY writers of the DB  ← base done; per-pillar TODO
tools/         tools the model calls (1 fn = 1 tool)     ← contract + reference done; rest TODO
services/      llm, agent_runtime, auth, telemetry       ← auth done; rest stub
agents/        the LangGraph node graph (router→…→present)← wiring done; node bodies TODO
mcp/           expose tools/ over MCP                     ← stub
```

## The contracts (do not deviate)

**Tool** = a plain function (see `tools/base.py` and the reference
`tools/logistics_tools.py::sign_equipment`):
```python
def tool_name(ctx: ToolContext, *, arg1: str, arg2: int = 0) -> ToolResult[...]:
```
- `ctx` first (session + actor + roles); model inputs are keyword-only, type-hinted.
- Return `ToolResult.of(value)` / `ToolResult.err(msg, suggestions=[...])` — **don't raise** for expected failures.
- Gate manager actions with `require_role(ctx, "…")`.
- Tool names are a **single global namespace** — keep them unique (registry raises on a clash).

**Mutating tool pattern** (copy `sign_equipment` exactly): look up (err+suggestions if missing) → apply to ORM objects → `repo.validate([check_fns])` → on violations `repo.rollback()` + `ToolResult.err` → else `repo.transfer/audit` → `repo.commit()` → `ToolResult.of(...)`. **Hard rules are enforced by re-using `rules/constraints.py` checks** against the pending state — never reimplement a rule in a tool.

**Repository** = the only DB writer (`data/services/base.py` + `logistics_repo.py`).
Every mutation records `audit(...)` (and `transfer(...)` for equipment) — that's R2-9.

**Registry + MCP** (`tools/registry.py`): each pillar module exports `TOOLS` (tuple of
functions) and `MUTATING` (set of names). The registry aggregates them; the in-process
executor and the MCP server both call `registry.call_tool(ctx, name, **args)` — so tools
are written **once**. (Note the `mcp/` folder name clash — see `mcp/server.py`.)

## Work split (by pillar)

**First (one person, ~half a day): freeze the core.** Land the agent graph node bodies
(`agents/nodes/*`), `services/llm.py` + `services/agent_runtime.py`, and confirm the
contracts above. **Once merged, the contracts are frozen** — changes to `tools/base.py`,
`data/services/base.py`, `agents/state.py`, or `tools/registry.py` need team sign-off.

**Then, one owner per pillar — each does repo + tools + tests end-to-end:**
| Dev | Pillar | Files |
|-----|--------|-------|
| A | **Network** | `data/services/network_repo.py`, `tools/network_tools.py`, `tests/tools/test_network_*.py` |
| B | **Logistics** | finish `tools/logistics_tools.py` (reference already done), `tests/tools/test_logistics_*.py` |
| C | **Guard Duty + AdHoc** + `scripts/maintenance.py` | `…/scheduling_repo.py`, `guard_duty_tools.py`, `adhoc_tools.py`, tests |
| D | **General Knowledge** + **MCP server** + **eval** | `general_knowledge_tools.py` (read-only), `mcp/`, `evaluation/`, tests |
(Dev D's pillar is read-only/lighter, so they also own MCP + eval. Rebalance as needed.)

Pillars touch **disjoint files**, so merge conflicts are rare. Shared files (models,
rules, base, registry, state) change only by coordination.

## Rules everyone follows
- **Agent proposes, engine decides** — rules live in `rules/`; tools call them.
- **No fabricated args; did-you-mean** — missing input → ask; bad id → `ToolResult.err(..., suggestions=...)` (`DESIGN.md` §2).
- **Derive, don't duplicate** (port/jack classification, formatting status).
- **Audit every mutation; equipment moves write a transfer.**
- **General Knowledge is read-only and self-only** for personal data.
- **Never commit** `naatomatic.db`, `dashboard.html`, `.venv` (already git-ignored).

## Testing (required, per pillar)
- Every tool: a test in `tests/tools/` with an **accept path** and a **reject path** (rule violation rolls back, DB unchanged) — copy `tests/tools/test_logistics_reference.py`.
- Agent-scenario tests go in `tests/agents/`.
- `python -m pytest -q` and `python scripts/verify.py` must stay green before every PR.

## Git workflow
- Branch per task (`feat/network-tools`); small PRs; one reviewer.
- Commit messages end with the `Co-Authored-By:` line (see existing history).
- Don't push the local DB; regenerate with `python -m data.generation.generate_data`.

## Dependencies to add as they're needed (`requirements.txt`)
`langchain`, `langchain-anthropic` (LLM — Claude), `langgraph` (graph), `mcp` (server),
`openpyxl` (CSV/Excel shift-list import).

## Start-here checklist
1. Clone + venv + `pip install -r requirements.txt` (see `HANDOFF.md`).
2. `python -m data.generation.generate_data 30 --seed 42 && python scripts/verify.py && python -m pytest -q` — all green.
3. Read `tools/base.py`, `data/services/base.py`, and `tools/logistics_tools.py::sign_equipment`.
4. Build your pillar's repo → tools → tests, copying the reference.
