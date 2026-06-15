# Naatomatic — System Design

> **Status:** Draft for review. Nothing here is final — open questions are marked **❓OPEN** and assumptions are marked **⚠️ASSUMPTION**. Please annotate inline.
>
> **Naming:** **Naatomatic** is the project/system name. **CombatAI** is the branch being managed — the domain "world" entity (the root state object, parallel to a `BusinessWorld`).

---

## 1. Overview

Naatomatic is an autonomous, AI-agent-based system for managing and optimizing daily operations within the **CombatAI** branch. It spans three operational pillars and enforces base/branch regulations as hard constraints, while giving personnel transparency into their open tickets and the fair distribution of operational burden.

### Pillars
1. **Network Infrastructure** — physical/logical network state, port allocation, IT tickets.
2. **Logistics & End-User Equipment** — computers & monitors inventory, equipment requests, transfers.
3. **Guard Duty Scheduling** — shift allocation with a "Justice Table," split between Keva (career) and Sadir (mandatory service).
4. **AdHoc Missions** — sudden, unplanned missions (ceremonies, memorials, volunteering); shares the Justice Table balancing.

### Design principles
- **Hard constraints are enforced at the data/service layer**, not left to the agent's judgment. The LLM agent proposes actions; a deterministic rules engine validates and commits them.
- **Full auditability** — every allocation, ticket transition, and shift assignment is logged with actor + timestamp.
- **Transparency** — personnel can query their own ticket status and the Justice Table at any time.
- **Separation of concerns** — each pillar is an independent agent with its own tools, sharing a common Personnel and Audit core.

---

## 2. Architecture (high level)

```
                ┌─────────────────────────────────────────┐
                │              User / Personnel             │
                └───────────────────┬──────────────────────┘
                                    │ (requests, queries)
                ┌───────────────────▼──────────────────────┐
                │           Orchestrator / Router            │
                │  routes intent → correct pillar agent       │
                └─┬──────────┬──────────┬──────────┬─────────────┘
                  │          │          │          │
        ┌─────────▼──┐ ┌─────▼─────┐ ┌──▼────────┐ ┌▼──────────┐
        │  Network   │ │ Logistics │ │ Guard Duty│ │  AdHoc    │
        │   Agent    │ │   Agent   │ │  Agents   │ │  Agent    │
        └─────────┬──┘ └─────┬─────┘ └──┬────────┘ └┬──────────┘
                  │          │          │           │
        ┌─────────▼──────────▼──────────▼───────────▼────────────┐
        │   Deterministic Rules / Constraint Engine (shared)       │
        │   - validates every mutating action against hard rules   │
        └───────┬──────────────────────────────────────────────────┘
                │
        ┌───────▼──────────────────────────────────────────────────┐
        │   Core Data Layer  (Personnel, Audit Log, Tickets)        │
        └───────────────────────────────────────────────────────────┘
```

**Agent vs. engine boundary:** The agent interprets natural-language requests and decides *what* to attempt. The constraint engine decides whether it is *allowed*. This keeps hard rules reliable and testable independent of model behavior.

**Decided:** Single **orchestrator + router** — the user talks to one entry point, which classifies intent and routes to the correct pillar agent.

### Node Architecture

We build on a standard agentic-node taxonomy, adopting only the nodes our flows need. Each pillar agent is a ReAct loop (LangGraph) made of these nodes.

**Core nodes (every pillar):**

| Node | Type | Role in Naatomatic |
|------|------|------------------|
| **Router** | LLM | The orchestrator entry point. Classifies intent → routes to the correct pillar, exposing only that pillar's tools and the user's role-permitted actions. |
| **Worker** | LLM | The ReAct reasoning step: interprets the request and decides which tool to call next (or that it's done). |
| **Tool Executor** | Code | Runs the chosen pillar tool against SQLite. Deterministic, no LLM. |
| **Validator** | Code | **The constraint engine.** Enforces every hard rule (HC-*) — pass/fail, cannot be bypassed. See placement note below. |

**Recommended:**

| Node | Type | Role |
|------|------|------|
| **Presenter** | LLM | Formats the final user-facing answer (chat-only, bilingual HE/EN). May start folded into the Worker and split out later. |

**Deferred — add only when a task demands it:**

| Node | Trigger to add |
|------|----------------|
| **Planner** (LLM) | A genuinely multi-step task the ReAct loop handles awkwardly — e.g., "assign the next 4 guard shifts fairly." |
| **Critic** (LLM) | A need for *subjective* evaluation. Mostly unnecessary: our quality bar is objective (Justice Table + hard constraints), already covered by the Validator. |
| **Integrator** (LLM) | A cross-pillar query that merges sources — e.g., "everything about soldier X: equipment, ports, shifts." |
| **Summarizer** (LLM) | Long flows needing context/memory compression. Our flows are short; not needed now. |

**Validator placement (important):** the hard-constraint logic lives in the **service layer** (so tools/repository can never be bypassed). The Validator node is a thin pre-commit gate that calls that same logic. Single source of truth, enforced regardless of how an action arrives. This is the concrete implementation of the "agent proposes, engine decides" boundary above.

---

## 3. Core Domain Model

Shared entities used across pillars.

### Personnel
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Primary key |
| `personal_number` | string | Military/service ID (unique) |
| `full_name` | string | |
| `population` | enum | `KEVA` \| `SADIR` |
| `rank` | enum | see Rank enum — used for guard-duty eligibility |
| `roles` | list of enum | see Roles & Permissions (§9). Empty = plain branch member. |
| `active` | bool | Soft-disable for personnel who left |
| `created_at` / `updated_at` | timestamp | |

### Rank (shared enum)
Used for guard-duty eligibility (some shifts are restricted to a specific rank).
```
LIEUTENANT | CAPTAIN | MAJOR
```
This is the complete and exhaustive list of ranks in the branch.

### Classification (shared enum)
Used by network ports and computers.
```
CIVILIAN | GLOBAL | SECRET | TOP_SECRET
```

### Role (shared enum)
Held by Personnel as a list (`roles`); empty = plain branch member. Drives permissions — see §9.
```
NETWORK_MANAGER | LOGISTICS_OFFICER | SHIFT_MANAGER
```

### Ticket (shared lifecycle)
Both Network and Logistics requests are tickets with a common state machine.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `type` | enum | `NETWORK_REQUEST` \| `EQUIPMENT_REQUEST` |
| `requester_id` | FK → Personnel | |
| `status` | enum | see state machine below |
| `subject` / `description` | string | |
| `payload` | JSON | type-specific request details |
| `created_at` / `updated_at` / `resolved_at` | timestamp | |
| `history` | list | append-only status transitions |

**Ticket state machine**
```
OPEN ⇄ ON_HOLD → RESOLVED (terminal)
```
- `OPEN` — submitted, awaiting handling.
- `ON_HOLD` — handling paused (e.g., waiting on the requester, parts, or scheduling).
- `RESOLVED` — the underlying problem is solved (terminal). For a network connection ticket, reaching `RESOLVED` is the trigger that updates the WallJack→Port mapping (see §4).

### Audit Log
Append-only. Every mutating action writes one entry: `{ id, actor, action, entity_type, entity_id, before, after, timestamp }`.

---

## 4. Pillar 1 — Network Infrastructure Agent

### Entities

**Switch**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `name` | string | e.g., "SW-FLOOR2-A" |
| `location` | string | |
| `classification` | enum | A switch is **single-classification**: all its ports carry this level. |
| `total_ports` | int | |

**Port**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `switch_id` | FK → Switch | |
| `port_number` | int | |
| `classification` | enum (derived) | Inherited from `switch.classification` (switches are single-class). Not stored separately. |
| `status` | enum | `FREE` \| `OCCUPIED` \| `DISABLED` |
| `wall_jack_id` | FK → WallJack (nullable) | physical mapping |
| `allocated_to` | FK → Personnel (nullable) | |

**WallJack**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `label` | string | physical jack label on the wall |
| `room` / `location` | string | |
| `port_id` | FK → Port (nullable) | which port it patches to |

> **Classification is derived, not stored.** A wall jack inherits the classification of the port it's patched to (`port.classification`, via `port_id`). We deliberately do *not* duplicate it on WallJack to avoid the two drifting out of sync — the port/switch owns the classification. An **unconnected** jack (`port_id = null`) has no classification; that's expected, not an error.

### Capabilities (agent tools)
- `create_network_request(personnel, wall_jack, classification)` — open a ticket.
- `get_ticket_status(ticket_id)` / `list_my_tickets(personnel)`.
- `allocate_port(personnel, port)` — validated by engine.
- `release_port(port)`.
- `map_walljack_to_port(wall_jack, port)`.
- `count_free_ports(filter: switch? classification?)`.
- `query_infrastructure(...)` — read-only reporting.

### Hard Constraints
- **HC-NET-1 — One port per classification per person.** A given personnel member may hold at most one allocated port of each classification (so up to 4 total, one per level).
  - Enforced on `allocate_port`: reject if person already holds a port at that classification.

**Mapping updates are resolution-driven.** The WallJack→Port mapping (and the port's `allocated_to`) is updated **only when the network manager resolves the connection ticket** — never automatically on ticket creation. Flow: requester opens a `NETWORK_REQUEST` → manager physically patches → manager resolves the ticket → resolution writes the WallJack/Port changes.

---

## 5. Pillar 2 — Logistics Operations Agent

### Entities

**EquipmentItem** (base)
| Field | Type | Notes |
|-------|------|-------|
| `catalog_number` | string | **unique identifier** (primary key) |
| `kind` | enum | `MONITOR` \| `COMPUTER` |
| `status` | enum | depends on kind (below) |
| `classification` | enum (nullable) | computers only |
| `signed_to` | FK → Personnel (nullable) | current holder |
| `created_at` / `updated_at` | timestamp | |

**Status by kind:**
- **Monitor:** `FUNCTIONAL` \| `BROKEN`
- **Computer:** richer lifecycle (below) — plus a `classification`.

**Computer status lifecycle**
| Status | Meaning |
|--------|---------|
| `FORMATTING` | Sent to formatting. Occupies a **2-week slot** on the Formatting Calendar starting from the send date. |
| `READY_FOR_PICKUP` | The 2-week formatting window has elapsed; the machine is done and awaiting collection. |
| `READY_TO_USE` | Picked up and back in inventory (מלאי), available to be signed out / used. |
| `IN_USE` | Currently signed to and used by a personnel member. |
| `BROKEN` | Malfunctioning / out of service. |

```
              sent to format          +2 weeks            picked up
   (any) ───────────────────► FORMATTING ──────► READY_FOR_PICKUP ──────► READY_TO_USE
                                                                              │   ▲
                                                                    signed out │   │ returned
                                                                              ▼   │
                                                                            IN_USE
   BROKEN  ◄── (from any status, on malfunction)
```

⚠️ASSUMPTION — `READY_TO_USE` is the "available in inventory" state and `IN_USE` is the "signed to someone" state. The `signed_to` field is set when a computer moves to `IN_USE` and cleared on return. A `BROKEN` computer can be sent to `FORMATTING` for repair/re-image.

**Decided:** The system **auto-transitions** `FORMATTING → READY_FOR_PICKUP` once the slot's `end_date` passes — no manual confirmation needed.

**EquipmentTransfer** (audit of movement)
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `catalog_number` | FK | |
| `from_personnel` / `to_personnel` | FK (nullable) | |
| `reason` | string | draw / return / repair / format |
| `timestamp` | timestamp | |

### Capabilities (agent tools)
- `create_equipment_request(personnel, kind, classification?)` — open a ticket.
- `get_ticket_status` / `list_my_tickets`.
- `sign_equipment_to(catalog_number, personnel)` — validated.
- `return_equipment(catalog_number)`.
- `set_equipment_status(catalog_number, status)`.
- `query_inventory(...)`.

### Hard Constraints
- **HC-LOG-1 — Max 2 monitors per person.** Reject sign-out if person already holds 2 monitors.
- **HC-LOG-2 — Max 1 computer per classification per person.** Reject if person already holds a computer at that classification.

### Default Holder (depot / non-usable items)
There is a reserved sentinel personnel record with **personal number `1234567`** that acts as the "depot" for items not currently usable by a real person.

- When an item becomes `BROKEN` or is sent to `FORMATTING`, it is **automatically signed to `1234567`** (auto-unsigned from the real holder).
- This means broken/formatting items are **never signed to a regular person**, and therefore can't be "drawn" until they return to `READY_TO_USE`.
- The per-person hard constraints (**HC-LOG-1/2**) are **not enforced for `1234567`** — the depot can hold unlimited items.

This cleanly answers two earlier questions: a broken item can't be signed out to a real person (it lives under the depot), and the limit logic never counts depot-held items against anyone.

---

## 6. Pillar 3 — Guard Duty Scheduling Agents

Two distinct scheduling models sharing the **Justice Table**.

### Shared entities

**Shift**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `type` | enum | `WEEK_LONG` \| `SINGLE_DAY` — drives quota counting |
| `time_of_day` | enum (nullable) | `DAY` \| `NIGHT` — informational only, for `SINGLE_DAY` shifts; does **not** affect quotas (1 day = 1 night) |
| `start_date` / `end_date` | date | |
| `eligible_population` | enum (nullable) | `KEVA` \| `SADIR`; null = either |
| `required_rank` | enum (nullable) | Rank; null = any rank |
| `assigned_to` | FK → Personnel (nullable) | |
| `status` | enum | `OPEN` \| `ASSIGNED` \| `COMPLETED` \| `CANCELLED` |

**Shift eligibility:** a shift may be targeted by population, by rank, or both. A person is eligible only if they match every non-null targeting field. Example: a "Captain night shift" sets `required_rank = CAPTAIN`; only captains can be assigned, and the balancing/quota logic operates within that eligible pool.

**JusticeTable** — derived/maintained tally per person:
| Field | Type | Notes |
|-------|------|-------|
| `personnel_id` | FK | |
| `week_long_count` | int | Keva: WEEK_LONG shifts done this calendar year |
| `single_day_count` | int | Keva: SINGLE_DAY shifts done this calendar year |
| `week_long_carryover` | int | Keva: surplus WEEK_LONG shifts carried from prior year (reduces this year's requirement). See HC-GD-4. |
| `single_day_carryover` | int | Keva: surplus SINGLE_DAY shifts carried from prior year |
| `total_burden_points` | decimal | Balancing currency (Sadir always; Keva for ad-hoc tie-breaks) — see **Burden Points** scale below |
| `period_start` | date | quota window anchor (Jan 1 of the calendar year) |

**Burden Points scale** (the single fairness currency for Sadir balancing):
| Assignment | Points |
|------------|--------|
| WEEK_LONG guard shift | 7 (1 per day) |
| SINGLE_DAY guard shift | 1 |
| AdHoc mission | **0.5 × number of days** (no overnight stay — half weight) |

All assignment types accumulate into the same `total_burden_points`, so balancing sees a soldier's *complete* load, not just guard duty.

### Shared hard constraint
- **HC-GD-0 — Eligibility.** A shift may only be assigned to a person who matches its `eligible_population` and `required_rank` (when set). Applies to both Keva and Sadir.

### A. Keva (career) — annual quotas with carry-over
Base annual target per Keva member (calendar year, Jan 1 – Dec 31):
- **HC-GD-1 — 2 `WEEK_LONG` shifts per year.**
- **HC-GD-2 — 4 `SINGLE_DAY` shifts per year** (day and night count the same — 1 day = 1 night).
- The two quotas are tracked **independently** (single-day shifts do not offset the week-long requirement, or vice-versa).

- **HC-GD-3 — Don't over-assign under normal operation.** The agent will not voluntarily assign a Keva member beyond their *effective* annual requirement for a shift type. Ad-hoc missions do **not** let a Keva member skip these guard quotas — the 2/4 still stand.

- **HC-GD-4 — Forced overflow carries to next year.** In an extreme/operationally-forced situation a Keva member may have to exceed 2 week-long or 4 single-day shifts in a year. When this happens:
  - The surplus is recorded in `week_long_carryover` / `single_day_carryover`.
  - **Effective requirement next year = base quota − carryover.** Example: a member forced to do 3 week-long shifts this year carries `+1`, so next year they owe only **1** week-long shift.
  - The Justice Table accounts for this when choosing who serves next: a member who over-served last year is **lower priority** for new assignments until the carry-over is worked off. This keeps the burden fair across year boundaries rather than resetting and forgetting the overflow.

**Ad-hoc for Keva:** Keva members *usually* don't get ad-hoc missions, but occasionally do. When they do, the ad-hoc burden (in `total_burden_points`) is used **only as a tie-breaker** to balance ad-hoc fairness *among Keva* — it never substitutes for or reduces the 2/4 guard quotas.

### B. Sadir (mandatory) — soft optimization
- **No hard cap.**
- **SC-GD-1 — Balance the burden.** Prioritize assigning the soldier(s) with the **lowest `total_burden_points`** to date, **within the eligible pool** (after applying HC-GD-0 rank/population filtering). Points combine guard duty *and* ad-hoc missions (see Burden Points scale above).
- **SC-GD-2 — Tie-break.** When multiple eligible soldiers are tied on `total_burden_points`, prefer the one with the **longest time since their last assignment** (any type).

### Capabilities (agent tools)
- `create_shift(type, dates)`.
- `assign_shift(shift, personnel)` — validated against Keva quotas / Sadir balancing.
- `suggest_assignment(shift)` — returns the recommended person(s) per the model.
- `get_justice_table(filter: population?)`.
- `mark_shift_completed(shift)`.

---

## 7. AdHoc Missions Agent

Handles **sudden, unplanned missions** the branch receives on short notice — representing the branch at ceremonies, memorials, volunteering activities, etc. Distinct from guard duty: no quota cycle, appears out of nowhere, and personnel typically do **not** stay overnight.

It is a **separate agent** (own triggering and lifecycle) but shares the **Justice Table** and balancing engine with guard duty, so a soldier's ad-hoc load counts toward their overall fairness burden.

### Entity

**AdHocMission**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `title` | string | e.g., "Memorial ceremony — Northern base" |
| `description` | string | |
| `start_date` / `end_date` | date | |
| `days` | int | mission length in days; default 1, but any length allowed (e.g., 3) |
| `eligible_population` | enum (nullable) | `KEVA` \| `SADIR`; null = either |
| `required_rank` | enum (nullable) | Rank; null = any |
| `assigned_to` | FK → Personnel (nullable) | |
| `status` | enum | `OPEN` \| `ASSIGNED` \| `COMPLETED` \| `CANCELLED` |

### Burden
- Each ad-hoc mission contributes **0.5 × `days`** to the assignee's `total_burden_points` (half weight — no overnight stay). A 3-day mission = 1.5 points.

### Capabilities (agent tools)
- `create_adhoc_mission(title, dates, days, eligibility?)`.
- `assign_adhoc_mission(mission, personnel)` — validated via HC-GD-0 eligibility; balanced via SC-GD-1/2.
- `suggest_adhoc_assignment(mission)`.
- `mark_adhoc_completed(mission)`.

### Constraints
- **HC-GD-0 (Eligibility)** applies — population/rank targeting works the same as shifts.
- **SC-GD-1/2 (Balancing + tie-break)** apply — ad-hoc assignment prefers the lowest-`total_burden_points` eligible soldier.

❓OPEN — Do ad-hoc missions apply to **Keva** as well as Sadir? If assigned to Keva, do they count toward any Keva quota, or sit entirely outside the quota system (burden-tracked only)? (Recommendation: assignable to both; for Keva, burden-tracked but *not* part of the 2/4 guard quotas.)

---

## 8. Calendars

Calendars are **queryable, time-based data** — not visual UI views. Since Naatomatic is a chat-based system, a "calendar" is simply a set of dated events the agent can filter and report on however a request is scoped. They serve two purposes: **conflict detection** (a slot can't be double-booked) and **transparency** (the agent can answer "who/what is scheduled when").

**Querying is flexible by scope.** The same underlying data can be filtered by population (Keva only, Sadir only, or both together), by rank, by date range, or by subject — driven entirely by what the user asks. There are no fixed "separate vs combined" views to pre-define.

### Generic model
A single `Calendar` abstraction backs all use cases (guard, ad-hoc, formatting), so we don't duplicate logic.

**Calendar**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `kind` | enum | `GUARD` \| `ADHOC` \| `FORMATTING` |
| `name` | string | |

**CalendarEvent** (a time slot on a calendar)
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `calendar_id` | FK → Calendar | |
| `start_date` | date(time) | |
| `end_date` | date(time) | |
| `subject_type` | enum | `SHIFT` \| `ADHOC_MISSION` \| `EQUIPMENT_ITEM` — what the slot is about |
| `subject_id` | FK | → Shift, AdHocMission, or EquipmentItem (catalog_number) |
| `label` | string | human-readable summary |
| `status` | string | mirrors the underlying subject's state |

> Events are **derived from / linked to** the source entities (Shifts, Computers), not a separate source of truth. The calendar reflects state; the entity owns it.

### Guard calendar (`GUARD`)
- One event per assigned `Shift`, regardless of population.
- The assignee's `population` (Keva/Sadir) and `rank` come from the linked Shift/Personnel, so the agent can answer any scope on demand:
  - "Keva guard duties in July" → filter `population == KEVA`.
  - "Sadir guard duties" → filter `population == SADIR`.
  - "Everyone on guard next week" → no population filter.
- Used to verify Keva quota windows (HC-GD-1/2/3), feed the Sadir balancing (Justice Table), and detect date conflicts.

### AdHoc calendar (`ADHOC`)
- One event per assigned `AdHocMission`.
- Same flexible scoping as the guard calendar (filter by population, rank, date).
- Feeds `total_burden_points` (0.5 × days) and is included in conflict detection alongside guard duty.

### Formatting calendar (`FORMATTING`)
- Tracks computers undergoing formatting.
- When a computer moves to `FORMATTING`, the system creates an event:
  - `subject_type = EQUIPMENT_ITEM`, `subject_id = catalog_number`
  - `start_date = <send date>`, `end_date = start_date + FORMATTING_DURATION`
- While "today" is within the slot → computer is `FORMATTING`.
- Once `end_date` passes → computer **auto-transitions** to `READY_FOR_PICKUP`.
- After pickup → computer is `READY_TO_USE` and the event is marked completed (or archived).

**Formatting duration is a fixed, configurable value** — `FORMATTING_DURATION`, default **14 days**. Treated as an exact duration (the slot end is when the machine is ready), but exposed as a config setting so it can be changed without code edits.

---

## 9. Cross-Cutting Concerns

### Roles & Permissions (AuthN + AuthZ)

**Authentication:** users log in with their **personal number**, which identifies them as a Personnel record.

**Authorization (RBAC):** access is role-based, with a baseline everyone shares plus domain-scoped manager roles.

**Baseline — every branch member can:**
- Open tickets (network / equipment requests).
- View the status of their own tickets.
- Update / cancel their own open requests.
- Query their own data (their equipment, ports, guard/ad-hoc assignments, burden points).

**Manager roles** grant **write access scoped to one domain only** (a manager has full branch-member rights plus their domain powers):

| Role | Domain | Can additionally... |
|------|--------|---------------------|
| `NETWORK_MANAGER` | Network | Resolve network tickets; create/update switches, ports, wall-jacks; write the wall-jack→port mapping; allocate/release ports. |
| `LOGISTICS_OFFICER` | Logistics | Resolve equipment tickets; update item statuses; sign/return equipment to personnel; manage inventory. |
| `SHIFT_MANAGER` | Guard Duty + AdHoc | Create shifts & ad-hoc missions; assign/reassign them; put events on the calendars; mark completed. |

- The agent **enforces domain scope**: e.g., a logistics officer asking to "open port 12 on SW-A" is refused — that's the network manager's domain.
- `roles` is a **list** — one person can hold multiple roles (e.g., a small branch where one person is both network manager and logistics officer).
- The constraint engine still applies on top of permissions: even a shift manager can't assign a Keva member past quota (HC-GD-3), etc. Roles govern *who may attempt* an action; hard constraints govern *whether it's allowed*.

**`SHIFT_MANAGER` is a single role covering both guard duty and ad-hoc missions** (both are scheduling/balancing under the shared Justice Table).

**Login is by personal number alone** for now — no password/PIN. This is acceptable because the system runs **local-only**. A secret should be added if it ever becomes networked/multi-user.

### Other cross-cutting concerns
- **Notifications** — **No active/push notifications for now.** Users learn ticket status by **asking the chat** ("what's the status of my request?"). Push notifications may be added later.
- **Audit & reporting** — every mutation logged (Section 3). Reporting dashboards TBD.
- **Concurrency** — port/equipment/shift allocation must be atomic to avoid double-allocation under concurrent requests.

---

## 10. Open Questions Summary

✅ **All open questions resolved.** Decisions are reflected inline throughout the document. Deferred-for-later items (not blocking): push notifications, login secret, REST/CLI surface, cloud deployment, Postgres migration — all to revisit if/when the system goes networked or multi-user.

---

## 11. Tech Stack

- **Language: Python.** ✓ Decided.
- **Agent framework: LangChain.** ✓ Decided — orchestrator + per-pillar agents with tool-calling.
- **Storage: SQLite** (start here). ✓ Decided.
  - Free, zero-setup (single file, built into Python), fully relational (FKs/constraints this design relies on), and right-sized for a single branch.
  - Migration path: schema moves to **PostgreSQL** with minimal change if we outgrow it (free hosted options: Supabase, Neon).
- **Runtime:** a Python process running the LangChain agent loop (message in → agent picks a tool → tool runs against the constraint engine + SQLite → response out). Nothing exotic required.
- **API surface: chat-only.** ✓ Decided — no REST/CLI for now; all interaction is through the chat agent.
- **Deployment target: local.** ✓ Decided — runs on a local machine for now.

---

*All open questions are resolved and the stack is confirmed (Python + LangChain + SQLite, local, chat-only). Next step: lock the data schema from the entity tables above and build pillar by pillar.*
