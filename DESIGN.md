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
| `can_do_week_long` | bool | Eligible for WEEK_LONG shifts. Default `true`. |
| `can_do_single_day` | bool | Eligible for SINGLE_DAY shifts (day or night). Default `true`. |
| `can_do_support` | bool | Eligible for SUPPORT shifts (**Sadir only**). Default **`false`** — new members must complete a course first; a manager then sets it true. |
| `can_do_adhoc` | bool | Eligible for ad-hoc missions. Default `true`. |
| `active` | bool | Soft-disable for personnel who left |
| `created_at` / `updated_at` | timestamp | |

**Duty-type eligibility** is just three booleans, one per duty type. We don't model *why* a person can't do a duty (no medical reasons stored) — only the yes/no per type. Each duty type has its own real-world requirements; whether a person meets them is captured as a single flag set by a manager.

### PersonnelDateBlock
Date-based unavailability — a person can't serve on specific dates (trip, appointment, etc.). One-to-many (a person can have several), separate from the duty-type booleans above.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `personnel_id` | FK → Personnel | |
| `start_date` | date | |
| `end_date` | date | |
| `reason` | string | free-text note (e.g., "trip", "appointment") |

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
| `resolved_item_catalog` | FK → EquipmentItem (nullable) | EQUIPMENT_REQUEST: the item handed over (set on resolution) |
| `resolved_port_id` | FK → Port (nullable) | NETWORK_REQUEST: the port connected (set on resolution) |
| `history` | list | append-only status transitions |

**Ticket state machine**
```
OPEN ⇄ ON_HOLD → RESOLVED (terminal)
```
- `OPEN` — submitted, awaiting handling.
- `ON_HOLD` — handling paused (e.g., waiting on the requester, parts, or scheduling).
- `RESOLVED` — the underlying problem is solved (terminal). Resolution is what links the request to its fulfilment (see Ticket resolution flow below).

**Ticket resolution flow (decided — chat-driven).** A manager (with the right role per §9) resolves a ticket **through the chat agent** — there is no separate app; the chat *is* the manager's interface. A `resolve_ticket` tool runs these steps atomically, validated by the constraint engine first:
1. **Validate** the intended outcome against hard rules (e.g., HC-LOG-2 before signing a computer; HC-NET-1 before allocating a port). Reject if it would violate one — the DB is left unchanged.
2. **Apply the fulfilment:**
   - *EQUIPMENT_REQUEST* → sign the chosen item to the requester (`signed_to = requester`), clear `reserved_for`, set status (`READY_TO_USE → IN_USE`); set `resolved_item_catalog`. The item is no longer held by the depot (`1234567`).
   - *NETWORK_REQUEST* → write the WallJack→Port mapping, set the port `OCCUPIED` / `allocated_to = requester`; set `resolved_port_id`.
3. **Close the ticket** (`status = RESOLVED`, stamp `resolved_at`).
4. **Record** an `EquipmentTransfer` (for equipment) and an `AuditLog` entry (always).

> This single tool answers Issue R2-7 (request↔fulfilment link), the "depot must be unassigned on resolution" requirement, and feeds R2-9 (transfer/audit rows). A future GUI/app, if ever added, would call the same tool — the logic is interface-independent.

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
| `allocated_to` | FK → Personnel (nullable) | the person holding this port |

> The physical jack↔port link is stored **once**, on `WallJack.port_id` (below) — not duplicated on Port. Given a port, its jack is found by reverse lookup. (Earlier drafts also listed `Port.wall_jack_id`; that duplicate is removed.)

**WallJack**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `label` | string | physical jack label on the wall |
| `room` / `location` | string | |
| `port_id` | FK → Port (nullable, **unique**) | which port it patches to. Unique ⇒ **at most one wall jack per port**; null = unconnected jack. |

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
  - Counts only **OCCUPIED** ports (a `DISABLED` port is not a live allocation).
- **HC-NET-2 — Port status / allocation consistency.** An `OCCUPIED` port must have an `allocated_to`; a `FREE` or `DISABLED` port must not. (And, via the unique `WallJack.port_id`, a port has at most one wall jack.)

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
| `signed_to` | FK → Personnel (nullable) | current **custody** (often the depot) |
| `reserved_for` | FK → Personnel (nullable) | **destination** on return — who the item is promised to while it sits at the depot (e.g. during formatting). Distinct from `signed_to`. |
| `created_at` / `updated_at` | timestamp | |

> **Why `reserved_for` is separate from `signed_to`.** When a computer is sent to formatting on behalf of a specific person, custody passes to the depot (`signed_to = 1234567`) but the machine is still earmarked for that person (`reserved_for = them`). On pickup it is signed back to `reserved_for` and the reservation is cleared. Keeping the two facts separate means "who holds it now" and "who it's coming back to" never overwrite each other. `reserved_for` is null for items not earmarked for anyone (e.g. a broken item with no pending owner).

**Status by kind:**
- **Monitor:** `FUNCTIONAL` \| `BROKEN` \| `DECOMMISSIONED`
- **Computer:** richer lifecycle (below) — plus a `classification`.

**Computer status lifecycle**
| Status | Meaning |
|--------|---------|
| `FORMATTING` | Being formatted. Two cases: **intake** (a new computer must be formatted before it can be used) and **repair** (a broken machine is re-imaged). Occupies a **2-week slot** on the Formatting Calendar from the send date. |
| `READY_FOR_PICKUP` | Formatting finished **and** the machine was reserved for a specific person, who collects it. |
| `READY_TO_USE` | In inventory / storage (מלאי), available to be signed out. A new computer reaches here only **after** intake formatting. |
| `IN_USE` | Currently signed to and used by a personnel member. |
| `BROKEN` | Malfunctioning, still in the branch (awaiting a fix attempt). |
| `DECOMMISSIONED` | **Out of service and removed from the branch** — IT could not fix it. **Terminal.** Held by nobody (`signed_to`/`reserved_for` cleared). Row kept for history; not part of inventory. |

**Intake rule (decided):** a computer **can't be used the moment it arrives.** When a new computer is received (assigned to the logistics manager), it is **sent to formatting first**, then enters storage. So the normal entry path is: `(new)` → `FORMATTING` → `READY_TO_USE` → `IN_USE`.

```
   (new computer / repaired)                    not reserved
        arrives → FORMATTING ───────────────────────────────► READY_TO_USE ──┐
                     │  │                                          ▲  │       │ sign out
        IT can't fix │  │ reserved for someone                    │  │ return ▼
                     │  └──► READY_FOR_PICKUP ──(collected)────────┘  └──── IN_USE
                     ▼                                                        │ breaks
              DECOMMISSIONED ◄──(IT can't fix)── BROKEN ◄────────────────────┘
              (terminal: removed                   │ sent to fix
               from branch)                        └──► FORMATTING
```

⚠️ASSUMPTION — `READY_TO_USE` = available in inventory; `IN_USE` = signed to someone. `signed_to` is set on `IN_USE` and cleared on return.

**Computer state machine (decided — resolves R2-8).** Only these transitions are legal; a tool that changes status must reject anything else:
| From | Allowed to |
|------|-----------|
| *(new intake)* | starts at `FORMATTING` |
| `FORMATTING` | `READY_TO_USE` (not reserved → into storage), `READY_FOR_PICKUP` (reserved for someone), `DECOMMISSIONED` (IT can't fix) |
| `READY_TO_USE` | `IN_USE` (sign out), `BROKEN` |
| `IN_USE` | `READY_TO_USE` (return), `BROKEN` (breaks in use) |
| `BROKEN` | `FORMATTING` (attempt repair), `DECOMMISSIONED` (unfixable) |
| `READY_FOR_PICKUP` | `READY_TO_USE` (into inventory), `IN_USE` (handed directly to `reserved_for`) |
| `DECOMMISSIONED` | — (terminal) |

A working in-inventory computer is **not** sent to formatting — formatting is entered only on **intake** or from **`BROKEN`**. (Monitors: `FUNCTIONAL` ⇄ `BROKEN`; `BROKEN` → `DECOMMISSIONED`.)

**Decommissioning & removal (documented).** When IT declares an item unfixable, a `decommission_item` tool sets status `DECOMMISSIONED`, clears `signed_to` and `reserved_for` (it has left the branch), and **records the removal**: an `EquipmentTransfer` (`to_personnel = null`, reason `"decommissioned — IT unable to repair"`) plus an `AuditLog` entry (who/when/why). Decommissioned items are excluded from inventory/stock queries but remain in the table for history.

**Decided — status from the slot, flipped by daily maintenance.** A computer sent to formatting gets a **2-week slot** (event) on the Formatting Calendar at the send date. Whether it is still `FORMATTING` or now `READY_FOR_PICKUP` is determined by comparing **today** against the slot's `end_date`. Because the system is chat-only with no background clock, the actual status flip is performed by the **daily maintenance routine** (see §14), which is idempotent and also handles other time-driven transitions. Reads may also derive the status directly from the slot for within-day precision.

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

### Equipment Dispensing Pipeline (decided)
The end-to-end flow when a soldier wants equipment. Validation happens **twice** — once to open the ticket, once at resolution — because stock and holdings can change in between.

1. **Request** — soldier asks (via chat) for N monitors, or a computer of classification X.
2. **Cap validation (projected state).** Reject if fulfilling the request would exceed a limit. The check is on **current holdings + this request**, where "holdings" counts items `signed_to` the person **and** items `reserved_for` them (so an in-formatting machine still counts):
   - monitors held + requested ≤ 2 (HC-LOG-1)
   - per classification: computers held + requested ≤ 1 (HC-LOG-2)
   - (This subsumes "he already has too many" and "the request itself is absurd, e.g. asking for 3 monitors" — they're the same projected-cap test.)
3. **Stock check.** Confirm a usable matching item exists in inventory:
   - **Computer:** status `READY_TO_USE` and in inventory (held by the depot, not a person).
   - **Monitor:** status `FUNCTIONAL` and in inventory.
   - **No reservation is made here** (decided) — opening the ticket only confirms stock *exists*; the specific item is chosen at resolution.
4. **Ticket opens** (`EQUIPMENT_REQUEST`, `OPEN`).
5. **Manager review (pull-based, decided).** The logistics officer **asks the chat** for open tickets (e.g. on login or "show open equipment tickets"). **No push notifications** — consistent with §9 (revisit WhatsApp/email later if needed).
6. **Physical handover.** The manager physically gives the soldier the item.
7. **Resolve (chat).** The manager runs `resolve_ticket` (see §3): it **re-validates** steps 2–3 against the *current* state (stock or holdings may have shifted), then signs the item over, unassigns the depot, links the ticket to the item, closes it, and records a transfer/audit row. If re-validation now fails (e.g. last unit gone, or requester hit the cap meanwhile), the resolution is refused and the ticket stays open with a reason.

> **Two-gate validation** is the key property: step 2–3 gate *ticket creation* (don't open an obviously-impossible request); step 7 re-gates *fulfilment* (the world may have changed since the ticket opened). The same HC-LOG-1/2 logic runs at both points — single source of truth, two call sites.

---

## 6. Pillar 3 — Guard Duty Scheduling Agents

Two distinct scheduling models sharing the **Justice Table**.

### Shared entities

**Shift**

> **Duty types:** `WEEK_LONG` and `SINGLE_DAY` are guard shifts. `SUPPORT` is the round-the-clock **customer-support standby** duty — a person on call to handle customers' support tickets. ⚠️ **Naming:** a SUPPORT shift is unrelated to the internal **Ticket** entity (§3), which is a branch-internal request about network/logistics/shifts. Different concepts — don't conflate.
>
> **SUPPORT coverage (decided).** Every single day must have **exactly one** SUPPORT person on call (continuous 24/7 cover). Weekdays (Sun–Thu) are one-day SUPPORT shifts. The **weekend is one shift covering Friday + Saturday** assigned to a single person — it spans 2 days (`start_date`=Fri, `end_date`=Sat) and counts **double** in burden points (2). Filling every day with no gaps and no overlaps is the **scheduler's** responsibility; HC-GD-7 already guarantees no person covers two overlapping days.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `type` | enum | `WEEK_LONG` \| `SINGLE_DAY` \| `SUPPORT` (Sadir-only) — drives quota counting / burden |
| `time_of_day` | enum (nullable) | `DAY` \| `NIGHT` — informational only, for `SINGLE_DAY` shifts; does **not** affect quotas (1 day = 1 night) |
| `start_date` / `end_date` | date | |
| `eligible_population` | enum (nullable) | `KEVA` \| `SADIR`; null = either |
| `required_rank` | enum (nullable) | Rank; null = any rank |
| `assigned_to` | FK → Personnel (nullable) | |
| `status` | enum | `OPEN` \| `ASSIGNED` \| `COMPLETED` \| `CANCELLED` |

**Shift eligibility:** a person is eligible only if they (1) match every non-null targeting field (population, rank — HC-GD-0), (2) have the duty-type flag for this shift's `type` set true (HC-GD-6 — e.g., SUPPORT requires `can_do_support`), and (3) are not date-blocked on the shift's dates (HC-GD-5). The balancing/quota logic then operates within that eligible pool.

**JusticeTable** — derived/maintained tally per person:
| Field | Type | Notes |
|-------|------|-------|
| `personnel_id` | FK | |
| `week_long_count` | int | Keva: WEEK_LONG shifts done this calendar year |
| `single_day_count` | int | Keva: SINGLE_DAY shifts done this calendar year |
| `week_long_carryover` | int (signed) | Keva: WEEK_LONG carryover from prior year. **Positive** = surplus (did extra) → reduces this year's requirement; **negative** = shortfall (did fewer) → increases it. See HC-GD-4. |
| `single_day_carryover` | int (signed) | Keva: SINGLE_DAY carryover, same signed convention |
| `total_burden_points` | decimal | Balancing currency (Sadir always; Keva for ad-hoc tie-breaks) — see **Burden Points** scale below |
| `period_start` | date | quota window anchor (Jan 1 of the calendar year) |

**Burden Points scale** (the single fairness currency for Sadir balancing):
| Assignment | Points |
|------------|--------|
| WEEK_LONG guard shift | 7 (1 per day) |
| SINGLE_DAY guard shift | 1 |
| SUPPORT shift | **number of days covered**: 1 for a weekday, **2 for a Fri–Sat weekend** (one person covers both days = double) |
| AdHoc mission | **0.5 × number of days** (no overnight stay — half weight) |

All assignment types accumulate into the same `total_burden_points`, so balancing sees a soldier's *complete* load, not just guard duty.

### Shared hard constraints (eligibility — apply to Keva, Sadir, and ad-hoc)
- **HC-GD-0 — Population/rank match.** An assignment may only go to a person matching its `eligible_population` and `required_rank` (when set).
- **HC-GD-5 — Availability.** A person must not be assigned to an assignment whose dates overlap any of their `PersonnelDateBlock` records.
- **HC-GD-6 — Duty-type eligibility.** A person must have the matching duty-type flag set true: `can_do_week_long` for WEEK_LONG shifts, `can_do_single_day` for SINGLE_DAY shifts, `can_do_support` for SUPPORT shifts, `can_do_adhoc` for ad-hoc missions. (SUPPORT shifts are **Sadir-only**, and `can_do_support` is false until a member completes the required course.)
- **HC-GD-7 — No overlapping assignments.** A person may not be assigned to two assignments whose date ranges overlap — at most one shift/SUPPORT/ad-hoc at a time. Applies across all assignment types (a guard shift and an ad-hoc mission on the same day is a violation).

### A. Keva (career) — annual quotas with carry-over
Base annual target per Keva member (calendar year, Jan 1 – Dec 31):
- **HC-GD-1 — 2 `WEEK_LONG` shifts per year.**
- **HC-GD-2 — 4 `SINGLE_DAY` shifts per year** (day and night count the same — 1 day = 1 night).
- The two quotas are tracked **independently** (single-day shifts do not offset the week-long requirement, or vice-versa).
- SUPPORT shifts do not apply to Keva at all — they are **Sadir-only** (see §6.B).

- **HC-GD-3 — Don't over-assign under normal operation.** The agent will not voluntarily assign a Keva member beyond their *effective* annual requirement for a shift type. Ad-hoc missions do **not** let a Keva member skip these guard quotas — the 2/4 still stand.

- **HC-GD-4 — Carryover (bidirectional).** At year end, the difference between what a Keva member did and their quota carries into next year, so the burden stays fair across year boundaries.
  - `carryover = done − quota` (per shift type), stored in `week_long_carryover` / `single_day_carryover`.
  - **Effective requirement next year = base quota − carryover.**
  - *Over-served:* did 3 week-long (quota 2) → carryover `+1` → next year owe **1**.
  - *Under-served:* did 1 week-long (quota 2) → carryover `−1` → next year owe **3** (the missed one rolls forward — "do one extra"). (This replaces the earlier "waive" decision.)
  - The Justice Table uses this when choosing who serves: someone who over-served is lower priority; someone who under-served is higher priority until they catch up.

> **Impossible-debt guard (decided).** A shortfall only rolls forward if the member was *able* to serve. If their duty flag is off (e.g. `can_do_week_long = false`) that quota **does not apply** to them at all, so **no shortfall accrues** — this prevents a permanently-restricted member from owing an ever-growing, unpayable debt. (A surplus, if somehow present, still rolls forward normally.)

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
- **HC-GD-0, HC-GD-5, HC-GD-6 (Eligibility)** apply — population/rank match, date availability, and the `can_do_adhoc` flag, same pattern as shifts.
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
- **DB layer: SQLAlchemy (ORM).** ✓ Decided — entity tables (§3–§7) become Python model classes; handles relationships, foreign keys, and constraints cleanly. Swapping SQLite→Postgres later is a connection-string change.
- **Runtime:** a Python process running the LangChain agent loop (message in → agent picks a tool → tool runs against the constraint engine + SQLite → response out). Nothing exotic required.
- **API surface: chat-only.** ✓ Decided — no REST/CLI for now; all interaction is through the chat agent.
- **Deployment target: local.** ✓ Decided — runs on a local machine for now.

---

## 12. Data Generation & Persistence

### Persistence model
The **SQLite database (`naatomatic.db`) is the single source of truth** — there is no in-memory "world" object threaded through tools. Flow for any mutating action:

1. A tool runs (e.g., `assign_shift`).
2. The **Validator** checks the relevant hard constraints (HC-*).
3. On pass, the tool calls the **repository layer**, which applies the change inside a **transaction** and commits.
4. Subsequent queries read the committed state directly — no copying, no state-swapping.

This replaces the reference framework's deep-copy-and-swap world dict: saving is automatic and transactional, scoped to each successful tool call.

### Schema
SQLAlchemy model classes mirror the entity tables in §3–§7. The schema is created from these models (`create_all` for dev; Alembic migrations if/when needed). `naatomatic.db` is **git-ignored** — only code and seed definitions are committed, never the database file.

### Seeding (data generation)
A standalone **`seed.py`** script populates a fresh database: create schema → insert curated records → commit. Run once to spin up a working DB.

- **Curated fixtures** (decided): a small, hand-authored, *known* dataset for development, demos, and deterministic tests — e.g., a handful of named personnel across Keva/Sadir and ranks, a few switches/ports, sample equipment, and some shifts. This is the equivalent of the reference framework's `DEFAULT_WORLD`, but expressed as SQLAlchemy rows.
- The reserved **Default Holder** (`personal_number = 1234567`, the equipment depot — §5) is always seeded.
- Faker-based bulk generation is **deferred** — add later only if we need volume/stress data.

### Test isolation
Each test run uses a fresh **in-memory SQLite (`:memory:`)** database seeded from the same fixtures (or a transaction rolled back at teardown). Fully isolated, fast, no leftover state — a cleaner equivalent of the reference framework's per-run deep copy.

---

## 13. Review Findings — Round-2 Open Questions

A structured review (design holes, code correctness, design↔code consistency, test coverage) surfaced the following genuine gaps. These are **decisions still to make**, not yet reflected in the rules above. Severity in brackets.

- **R2-1 — Time/scheduler actor [HIGH]. ✓ RESOLVED.** The system is chat-only/local with no background clock, so time-driven transitions are handled by an **idempotent daily maintenance routine** (see §14): formatting completion, shift/mission completion, and the Keva year reset. Formatting status is derived from the slot's `end_date` and flipped by maintenance. (The carryover/year-reset specifics still depend on R2-4/R2-6.)
- **R2-2 — Assignee double-booking [HIGH]. ✓ RESOLVED.** Added **HC-GD-7 (no overlapping assignments per person)** to §6 — enforced in `rules/constraints.py`, checked by `verify.py`, and respected by the generator.
- **R2-3 — SUPPORT continuous coverage [MED]. ✓ RESOLVED.** One SUPPORT person per day, every day (24/7). Weekdays = one-day shifts; the **weekend (Fri+Sat) is one 2-day shift** for a single person, counting **double** (2 burden points). See §6 SUPPORT coverage note and the Burden Points table. Gap-free coverage is the scheduler's job; HC-GD-7 prevents overlaps.
- **R2-4 — Keva under-served [MED]. ✓ RESOLVED — defer.** If a Keva member did **fewer** than their quota, the shortfall **rolls forward**: next year they owe the difference on top of the base (did 1 of 2 week-long → owe 3 next year). Carryover is therefore **bidirectional** (surplus reduces, shortfall increases) — see HC-GD-4. **Impossible-debt guard (decided):** a shortfall accrues only if the member's duty flag was on; if `can_do_*` is false the quota doesn't apply and nothing accrues, so a permanently-restricted member never builds an unpayable debt.
- **R2-5 — HC-GD-1/2 semantics [MED].** "Exactly 2 week-long / 4 single-day per year" are **end-of-year targets**, not per-snapshot invariants, so they can't be validated on a mid-year database. Clarify they're enforced by the **scheduler's planning**, not by `verify.py`. Separately, the cap side **HC-GD-3** currently ignores carryover, the calendar-year window, and shift status — tighten once R2-1/R2-6 are decided.
- **R2-6 — HC-GD-4 carryover unimplemented [MED]. Policy decided, build pending.** The rule is now fully specified (bidirectional — see R2-4/HC-GD-4). Still to build: the year-reset code in `scripts/maintenance.py` that, at the calendar-year boundary, sets `*_carryover = done − quota` (signed; subject to the impossible-debt guard), resets the counts, and re-anchors `period_start`.
- **R2-7 — Ticket↔fulfillment linkage [MED]. ✓ RESOLVED.** Tickets now carry `resolved_item_catalog` / `resolved_port_id`, set by a chat-driven `resolve_ticket` tool (see §3 Ticket resolution flow) that validates, applies the fulfilment, unassigns the depot, closes the ticket, and records a transfer/audit row. Interface = the chat (manager role), not a separate app. *(Still minor/open: the reopen path — `RESOLVED` is terminal; if an issue recurs, open a new ticket for now.)*
- **R2-8 — Computer status transition guards [LOW]. ✓ RESOLVED.** The legal-transition table is now defined in §5, including: the **intake rule** (a new computer can't be used on arrival — it starts at `FORMATTING`, then `READY_TO_USE`, then `IN_USE`); `FORMATTING` exits to `READY_TO_USE` (unreserved) or `READY_FOR_PICKUP` (reserved); and the terminal **`DECOMMISSIONED`** state. Formatting is entered only on intake or from `BROKEN` (a working in-inventory computer is never formatted). Enforcement is a `set_equipment_status`/`decommission_item` tool guard (built with the Logistics tools); the integrity check already asserts decommissioned items hold no custody.
- **R2-9 — Audit log & equipment transfers [LOW].** `AuditLog` and `EquipmentTransfer` are first-class in the design but nothing writes them yet. Wire them into the repository layer (every mutation → audit row; every sign/return → transfer row) when that layer is built.

> Note: **SC-GD-1/2** (Sadir balancing + tie-break) are **soft** optimization rules, enforced at *assignment time* by the scheduler — they are correctly **not** in `verify.py` (which checks hard invariants only).

### Network agent gaps (round-2 review)
A focused review found the Network pillar thinner than Logistics. Fixed in this round: the duplicated Audit Log section; the `Port.wall_jack_id`/`WallJack.port_id` mismatch (now single, unique link); **HC-NET-2** (port status/allocation consistency) added and checked; HC-NET-1 now counts only OCCUPIED ports. Remaining:

- **NET-1 — Network ticket payload [MED, decision].** A `NETWORK_REQUEST` doesn't capture *what* is asked — which wall-jack and which **desired classification**. A jack's classification is null until patched, so the requested level needs a home (recommend a typed `payload`, e.g. `{wall_jack_id, desired_classification}`).
- **NET-2 — `DISABLED` port semantics [MED, decision].** When is a port DISABLED (faulty/reserved/decommissioned?), who sets it, and is it excluded from `count_free_ports`? Currently defined but never used.
- **NET-3 — Release / disconnect + leaver cleanup [MED, decision].** No flow frees a port. When a person goes inactive, their ports should be released (analogous to equipment return). Define `release_port` semantics and the leaver rule.
- **NET-4 — Port allocation history [LOW, decision].** Network has no movement trail (Logistics has EquipmentTransfer + AuditLog). Decide whether port allocate/release/re-patch should be logged (recommend: at least AuditLog rows).
- **NET-5 — Switch/port decommission [LOW, decision].** No path to retire a switch or port. Probably fine to defer; confirm.
- **NET-6 — Resolution-driven mapping unbuilt [build-time].** `resolved_port_id` and the allocate-on-resolve flow are specified (§3/§4) but unimplemented; the generator currently produces RESOLVED network tickets with no port link. Build with the Network tools (the `resolve_ticket` flow already covers the logic).
- **NET-7 — Reporting unexercised [build-time].** `count_free_ports` (FREE vs DISABLED) and `Switch.total_ports`-vs-actual-rows reconciliation get covered when the Network tools/tests are built.

These mirror features Logistics already has; most are **parity work for the build phase**, with a few small decisions (NET-1, NET-2, NET-3) worth settling first.

---

## 14. Time-Driven Maintenance

The system is chat-only and local — there is **no background clock**. Anything that should change "as time passes" is handled by a single **idempotent maintenance routine** (planned: `scripts/maintenance.py`). Idempotent = safe to run any number of times; running it twice in a day changes nothing extra.

**Daily tasks:**
| Task | Action |
|------|--------|
| **Formatting completion** | Each computer whose Formatting-Calendar slot `end_date` has passed and is still `FORMATTING`: if `reserved_for` is set → `READY_FOR_PICKUP` (someone is waiting to collect it); otherwise → `READY_TO_USE` (straight into storage — e.g. intake of a new computer). Custody stays with the depot until collected/used. |
| **Shift / mission completion** | Each `Shift` / `AdHocMission` with `end_date` in the past and status `ASSIGNED` → `COMPLETED`. (Nothing flips these otherwise.) |
| **Keva year reset** | On a new calendar year, for each Keva member: set `week_long_carryover = week_long_count − 2` and `single_day_carryover = single_day_count − 4` (**signed** — positive = surplus reduces next year, negative = shortfall increases it), reset the counts to 0, and re-anchor `period_start` to Jan 1. Subject to the impossible-debt guard (no shortfall accrues when the duty flag is off) — see HC-GD-4 / R2-4. |

**Trigger (decided):** run the routine **on app startup, guarded to once per day** (compare a stored "last maintenance date" to today). No external scheduler required for the local deployment. Optionally, Windows Task Scheduler can also run `scripts/maintenance.py` daily — but the startup guard makes the system self-sufficient.

> Why idempotent + guarded rather than a real scheduler: it keeps a local, chat-only app self-contained (no daemon to install or keep alive) while guaranteeing the time-driven transitions happen at least once per day, and never double-apply.

---

*Schema and stack are confirmed (Python + LangChain + SQLAlchemy + SQLite, local, chat-only). Resolved: R2-1 (maintenance routine), R2-2 (HC-GD-7), R2-3 (SUPPORT coverage), R2-4 (defer under-served — bidirectional carryover), R2-6 (carryover policy), R2-7 (ticket resolution flow, chat-driven). The daily maintenance routine (§14) and the `resolve_ticket` flow (§3) are fully specified and pending build. Remaining open item: R2-9 (audit/transfer writes — first uses now specified: ticket resolution and decommissioning), best handled while building the Logistics/Network tools. R2-8 (computer state machine incl. the terminal `DECOMMISSIONED` state) is now defined; only the tool-level transition guard remains to build. The project structure template (`PROJECT_STRUCTURE.md`) lays out where each pillar, tool, service, and test will live as we build.*
