# Naatomatic — Project Structure (Template)

This is the **target layout** we build into. Folders that already exist are marked ✅;
the rest are scaffolded as empty packages (with `__init__.py` + a README) so the shape is
clear before the logic is written. Existing working scripts stay put for now; the
"Migration" notes say where they'll eventually live.

```
Naatomatic/
├── models/                  ✅ data layer — ORM tables, enums, DB engine/session
│   ├── tables.py            ✅ SQLAlchemy models (one class per entity)
│   ├── enums.py             ✅ domain enums + constants (depot number, formatting days)
│   └── db.py                ✅ engine, session factory, Base, create_all
│
├── rules/                   ✅ constraint engine — the single source of truth for HC-*
│   └── constraints.py       ✅ each hard rule as a check; ALL_CHECKS registry; run_all
│
├── data/                    data generation + data services (repositories)
│   ├── services/            repository layer (one per aggregate) + unit-of-work
│   │   ├── personnel_repo.py
│   │   ├── network_repo.py
│   │   ├── logistics_repo.py
│   │   └── scheduling_repo.py
│   └── generation/          how the DB gets populated
│       ├── generate_data.py random/bulk generator (Faker)   [migrates from scripts/]
│       ├── seed.py          small curated fixtures (known dataset)
│       └── fixtures/        optional JSON/py fixture data
│
├── tools/                   MCP-exposed tools the model calls, grouped per pillar
│   ├── network_tools.py     connect/release port, map wall-jack, count free ports, ...
│   ├── logistics_tools.py   sign/return equipment, set status, query inventory, ...
│   ├── guard_duty_tools.py  create/assign shift, suggest assignment, justice table, ...
│   ├── adhoc_tools.py       create/assign ad-hoc mission, ...
│   └── registry.py          tool catalog: name → fn, mutating set, JSON specs
│
├── mcp/                     MCP server entry point exposing tools/ to the model
│   └── server.py
│
├── agents/                  the node graph (LangGraph) — see DESIGN.md §2
│   ├── orchestrator.py      builds & runs the graph
│   ├── router.py            Router node: classify intent → pillar + role scope
│   ├── nodes/               reusable nodes
│   │   ├── worker.py        Worker (ReAct reasoning step)
│   │   ├── validator.py     Validator node — calls rules/constraints.py before commit
│   │   └── presenter.py     Presenter (formats final HE/EN answer)
│   └── pillars/             per-pillar worker config (system prompts, tool subsets)
│       ├── network.py
│       ├── logistics.py
│       ├── guard_duty.py
│       └── adhoc.py
│
├── services/                cross-cutting infrastructure
│   ├── llm.py               LLM client wrapper (model ids, structured output, retries)
│   ├── agent_runtime.py     per-run runtime: session, telemetry, tool/LLM calls
│   ├── telemetry.py         tool/LLM metrics schemas
│   └── auth.py              login by personal_number; role/permission checks (§9)
│
├── evaluation/              eval harness (inspired by agents_day2/validation)
│   ├── tasks/               scenario task definitions (prompt + expected outcome)
│   ├── evaluator.py         scores an agent run against expected state/answer
│   └── run_eval.py          batch runner + summary
│
├── tests/                   pytest suite
│   ├── conftest.py          in-memory seeded DB fixtures (DESIGN.md §12 isolation)
│   ├── unit/                unit tests of services, rules, repositories
│   ├── tools/               hard-coded direct tool-call tests (accept + reject paths)
│   └── agents/              agent-scenario tests: ask the agent, assert action/output
│
├── scripts/                 ✅ CLI utilities
│   ├── verify.py            ✅ run all hard constraints over a DB (gate)
│   ├── inspect_data.py      ✅ summary + spot checks
│   └── generate_data.py     ✅ (will migrate into data/generation/)
│
├── config/                  settings — model ids, db path, domain constants
│   └── settings.py
│
├── DESIGN.md                ✅ the spec (single source of truth)
├── PROJECT_STRUCTURE.md     ✅ this file
├── README.md                ✅
├── requirements.txt         ✅
└── pytest.ini               ✅ test discovery
```

## Layer responsibilities (bottom-up)

1. **models/** — the data shapes. No business logic.
2. **rules/** — pure hard-constraint predicates over the DB. Knows nothing about agents.
3. **data/services/** — repositories: the *only* place that writes the DB, inside transactions.
   Tools and the Validator go through here.
4. **tools/** — thin functions the model calls. Each tool: validate (rules/) → act (services/) →
   return a `ToolResult`. No SQL or reasoning here.
5. **agents/** — the node graph that decides *which* tool to call. Router → Worker → Tool
   Executor → Validator → Presenter.
6. **mcp/** — exposes tools/ over MCP so the model can call them.
7. **services/** — shared infra used by agents (LLM, runtime, telemetry, auth).
8. **evaluation/** — measures whole-system behavior on scenario tasks.
9. **tests/** — fast, isolated correctness checks at every layer.

## Testing strategy (matches the three things you asked to test)

- **`tests/unit/`** — test `rules/` predicates and `data/services/` repositories directly.
  Example: "signing a 3rd monitor raises / is rejected (HC-LOG-1)."
- **`tests/tools/`** — **hard-coded tool calls** with no model in the loop. Call a tool with
  fixed args against a seeded in-memory DB and assert the result + the resulting DB state.
  Cover both the **accept path** (valid action succeeds and persists) and the **reject path**
  (invalid action is blocked by a hard rule and the DB is unchanged).
- **`tests/agents/`** — **agent-scenario tests**. Give the agent a natural-language task
  ("connect wall-jack WJ-007 to a free secret port"), run the graph, and assert the intended
  **action happened** (DB changed correctly) or the **answer is correct** (for info questions).
  This is the behavioral layer, modeled on the lecturer's `validation/` eval style but as
  assertions rather than scored batches.
- **`evaluation/`** — the scored, batch version of agent-scenario tests for tracking quality
  over time (accuracy, tool-call counts, cost), mirroring `agents_day2/validation`.

## Migration notes (don't break what works)

- `scripts/generate_data.py` → `data/generation/generate_data.py` once the package is wired
  (update the two import lines + the test fixture). Kept in `scripts/` for now so the working
  generator/verifier stay green.
- `scripts/verify.py` and `inspect_data.py` stay as CLI entry points but import from `rules/`.
- Nothing in `models/` or `rules/` moves.
