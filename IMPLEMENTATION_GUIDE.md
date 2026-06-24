# Implementation guide — building Naatomatic with 4 people

Goal: four people build in parallel and the code **fits together** because everyone
codes against the **same contracts**. Read this + `DESIGN.md` (the spec) before
writing code. The skeleton already compiles and tests pass — fill in the bodies.

## Layers (dependencies point one way — never upward)

```
models/        data shapes (tables, enums, db)          ← done
rules/         constraint engine (HC-* checks)           ← done (12 checks)
data/services/ repositories: the ONLY writers of the DB  ← base done; per-domain TODO
tools/         tools the model calls (1 fn = 1 tool)     ← contract + reference done; rest TODO
services/      llm, agent_runtime, auth, telemetry       ← auth done; rest stub
agents/        the LangGraph node graph (router→…→present)← wiring done; node bodies TODO
mcp/           expose tools/ over MCP                     ← stub
```

## The contracts (do not deviate)

**Tool** = a plain function whose inputs are ONE described Pydantic model (see
`tools/base.py` and the reference `tools/logistics_tools.py::sign_equipment`):
```python
class SignEquipmentArgs(BaseModel):
    catalog_number: str = Field(description="Catalog number of the item to sign out.")
    personnel_id: int = Field(description="Id of the person receiving the item.")

def sign_equipment(ctx: ToolContext, args: SignEquipmentArgs) -> ToolOutput[dict]:
    """One-line on WHEN to use this tool, then details. (The model reads this.)"""
```
- **Every tool input is a `pydantic` field with a `Field(description=...)`** — the
  description is what the model sees (`tool_spec` builds the schema from the model).
- `ctx` first (session + actor + roles); the second param is the args model.
- **Every tool has a docstring** whose first line states the usage context (intent).
- **All tools return `ToolOutput`** — `ToolOutput.of(value)` / `ToolOutput.err(msg, suggestions=[...])`; **never raise** for expected failures.
- Gate manager actions with `require_role(ctx, "…")`.
- Tool names are a **single global namespace** — keep them unique (registry raises on a clash).
- Code is **PEP 8 + clean code**: small functions, clear names, no dead code (the stubs above still use keyword params — convert each to its own `Args` model when you implement it).

**Mutating tool pattern** (copy `sign_equipment` exactly): look up (err+suggestions if missing) → apply to ORM objects → `repo.validate([check_fns])` → on violations `repo.rollback()` + `ToolOutput.err` → else `repo.transfer/audit` → `repo.commit()` → `ToolOutput.of(...)`. **Hard rules are enforced by re-using `rules/constraints.py` checks** against the pending state — never reimplement a rule in a tool.

**Repository** = the only DB writer (`data/services/base.py` + `logistics_repo.py`).
Every mutation records `audit(...)` (and `transfer(...)` for equipment) — that's R2-9.

**Registry + MCP** (`tools/registry.py`): each domain module exports `TOOLS` (tuple of
functions) and `MUTATING` (set of names). The registry aggregates them; the in-process
executor and the MCP server both call `registry.call_tool(ctx, name, **args)` — so tools
are written **once**. (Note the `mcp/` folder name clash — see `mcp/server.py`.)

## Work split (by domain)

**First (one person, ~half a day): freeze the core.** Land the agent graph node bodies
(`agents/nodes/*`), `services/llm.py` + `services/agent_runtime.py`, and confirm the
contracts above. **Once merged, the contracts are frozen** — changes to `tools/base.py`,
`data/services/base.py`, `agents/state.py`, or `tools/registry.py` need team sign-off.

**Then, one owner per domain — each does repo + tools + tests end-to-end:**
| Dev | Domain | Files |
|-----|--------|-------|
| A | **Network** | `data/services/network_repo.py`, `tools/network_tools.py`, `tests/tools/test_network_*.py` |
| B | **Logistics** | finish `tools/logistics_tools.py` (reference already done), `tests/tools/test_logistics_*.py` |
| C | **Guard Duty + AdHoc** + `scripts/maintenance.py` | `…/scheduling_repo.py`, `guard_duty_tools.py`, `adhoc_tools.py`, tests |
| D | **General Knowledge** + **MCP server** + **eval** | `general_knowledge_tools.py` (read-only), `mcp/`, `evaluation/`, tests |
(Dev D's domain is read-only/lighter, so they also own MCP + eval. Rebalance as needed.)

Domains touch **disjoint files**, so merge conflicts are rare. Shared files (models,
rules, base, registry, state) change only by coordination.

## Rules everyone follows
- **Agent proposes, engine decides** — rules live in `rules/`; tools call them.
- **No fabricated args; did-you-mean** — missing input → ask; bad id → `ToolOutput.err(..., suggestions=...)` (`DESIGN.md` §2).
- **Structured communication, never free text between agents/nodes.** Nodes pass the
  typed `GraphState`; tool inputs/outputs are Pydantic/`ToolOutput`, not prose. **Refer
  to entities by id** (`personnel_id`, `catalog_number`, `ticket_id`, `port_id`), never
  by a loose name. Natural-language is produced in exactly one place: the **Presenter**.
- **Derive, don't duplicate** (port/jack classification, formatting status).
- **Audit every mutation; equipment moves write a transfer.**
- **General Knowledge is read-only and self-only** for personal data.
- **Never commit** `naatomatic.db`, `dashboard.html`, `.venv` (already git-ignored).

## Testing (required — every deployed agent ships BOTH)
Each domain agent must come with two kinds of runnable tests:
1. **Tool-call unit tests** (`tests/tools/`) — deterministic, **no model in the loop**.
   Call the tool with fixed args against the seeded in-memory `session` and assert the
   `ToolOutput` + the resulting DB state. Cover an **accept path** and a **reject path**
   (rule violation rolls back, DB unchanged). Copy `tests/tools/test_logistics_reference.py`.
2. **Agent-scenario tests** (`tests/agents/`) — feed natural-language **questions into the
   agent itself**, run the graph, and capture the **final text answer** (and/or assert the
   intended DB change). This is how we see what the agent actually replies. Keep a small
   list of questions per domain (e.g. "Sign monitor CAT-123 to person 7", "How many free
   secret ports are there?") so reviewers can eyeball the answers.

`python -m pytest -q` and `python scripts/verify.py` must stay green before every PR.

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
4. Build your domain's repo → tools → tests, copying the reference.
