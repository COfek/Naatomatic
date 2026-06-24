# Naatomatic — System Design

> **Status:** Draft for review. Nothing here is final — open questions are marked **❓OPEN** and assumptions are marked **⚠️ASSUMPTION**. Please annotate inline.
>
> **Naming:** **Naatomatic** is the project/system name. **CombatAI** is the branch being managed — the domain "world" entity (the root state object, parallel to a `BusinessWorld`).

---

## 1. Overview

Naatomatic is an autonomous, AI-agent-based system for managing and optimizing daily operations within the **CombatAI** branch. It spans three operational domains and enforces base/branch regulations as hard constraints, while giving personnel transparency into their open tickets and the fair distribution of operational burden.

### Domains
1. **Network Infrastructure** — physical/logical network state, port allocation, IT tickets.
2. **Logistics & End-User Equipment** — computers & monitors inventory, equipment requests, transfers.
3. **Guard Duty Scheduling** — shift allocation with a "Justice Table," split between Keva (career) and Sadir (mandatory service).
4. **AdHoc Missions** — sudden, unplanned missions (ceremonies, memorials, volunteering); shares the Justice Table balancing.
5. **General Knowledge** — read-only help desk: explains how the system works (fairness, eligibility, lifecycles) and walks personnel through branch procedures (onboarding, opening network access, shift readiness, org structure, own details, infosec).

### Design principles
- **Hard constraints are enforced at the data/service layer**, not left to the agent's judgment. The LLM agent proposes actions; a deterministic rules engine validates and commits them.
- **Full auditability** — every allocation, ticket transition, and shift assignment is logged with actor + timestamp.
- **Transparency** — personnel can query their own ticket status and the Justice Table at any time.
- **Separation of concerns** — each domain is an independent agent with its own tools, sharing a common Personnel and Audit core.

---

## 2. Architecture (high level)

```
                ┌─────────────────────────────────────────┐
                │              User / Personnel             │
                └───────────────────┬──────────────────────┘
                                    │ (requests, queries)
                ┌───────────────────▼──────────────────────┐
                │           Orchestrator / Router            │
                │  routes intent → correct domain agent       │
                └─┬────────┬────────┬────────┬────────┬───────────┘
                  │        │        │        │        │
        ┌─────────▼┐ ┌─────▼────┐ ┌─▼──────┐ ┌▼──────┐ ┌▼──────────┐
        │ Network  │ │Logistics │ │ Guard  │ │ AdHoc │ │  General  │
        │  Agent   │ │  Agent   │ │ Duty   │ │ Agent │ │ Knowledge │
        └─────────┬┘ └─────┬────┘ └─┬──────┘ └┬──────┘ └┬──────────┘
                  │        │        │         │         │ (read-only)
        ┌─────────▼────────▼────────▼─────────▼─────────▼──────────┐
        │   Deterministic Rules / Constraint Engine (shared)       │
        │   - validates every mutating action against hard rules   │
        └───────┬──────────────────────────────────────────────────┘
                │
        ┌───────▼──────────────────────────────────────────────────┐
        │   Core Data Layer  (Personnel, Audit Log, Tickets)        │
        └───────────────────────────────────────────────────────────┘
```

**Agent vs. engine boundary:** The agent interprets natural-language requests and decides *what* to attempt. The constraint engine decides whether it is *allowed*. This keeps hard rules reliable and testable independent of model behavior.

**Decided:** Single **orchestrator + router** — the user talks to one entry point, which classifies intent and routes to the correct domain agent.

### Node Architecture

We build on a standard agentic-node taxonomy, adopting only the nodes our flows need. Each domain agent is a ReAct loop (LangGraph) made of these nodes.

**Core nodes (every domain):**

| Node | Type | Role in Naatomatic |
|------|------|------------------|
| **Router** | LLM | The orchestrator entry point. Classifies intent → routes to the correct domain, exposing only that domain's tools and the user's role-permitted actions. |
| **Worker** | LLM | The ReAct reasoning step: interprets the request and decides which tool to call next (or that it's done). |
| **Tool Executor** | Code | Runs the chosen domain tool against SQLite. Deterministic, no LLM. |
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
| **Integrator** (LLM) | A cross-domain query that merges sources — e.g., "everything about soldier X: equipment, ports, shifts." |
| **Summarizer** (LLM) | Long flows needing context/memory compression. Our flows are short; not needed now. |

**Validator placement (important):** the hard-constraint logic lives in the **service layer** (so tools/repository can never be bypassed). The Validator node is a thin pre-commit gate that calls that same logic. Single source of truth, enforced regardless of how an action arrives. This is the concrete implementation of the "agent proposes, engine decides" boundary above.

### No fabricated arguments — ask, don't guess
A core behavior rule for the **Worker**: the model must **never invent required tool arguments.** If the user's request is missing a needed detail — *which* wall jack, *which* classification, *which* catalog number, *which* person, *which* dates — the agent **asks a follow-up question** and waits, rather than filling in a plausible-looking value. Example: "connect my workstation" with no jack/level given → the agent replies *"Which wall jack, and which classification (Civilian/Global/Secret/Top-Secret)?"* — it does not pick one.

Enforced at **two layers** (defense in depth):
1. **Prompt-level** — the Worker's system prompt forbids guessing required inputs and instructs it to gather missing details first; tool schemas mark which arguments are required.
2. **Tool/validator backstop** — tools **validate every reference**: the `wall_jack_id` must resolve to a real jack, `desired_classification` must be a valid enum, a `catalog_number`/`personal_number` must exist. An invented or non-existent value is **rejected** (a clear error the agent surfaces / asks about), never acted on. This catches hallucinations the prompt missed — same spirit as "agent proposes, engine validates."

This applies to **every domain's tools**, not just network requests.

### Fuzzy reference resolution — "did you mean?"
When the user **does** give an identifier but it **doesn't exactly match** anything (a mistyped ticket id, catalog number, personal number, jack label, switch name…), the agent must **neither fabricate a match nor hard-fail**. Instead the tool returns the **closest existing candidates** and the agent presents them for the user to choose from.

Example — a manager types `resolve ticket 42` but there is no ticket 42:
> *"I couldn't find ticket 42. Did you mean one of these open tickets? **41** — Connect workstation (Noa), **45** — Draw equipment (Amit), **38** — Connect workstation (Dana). Which one?"*

The manager replies with the right id (or picks from the list); only then does the action proceed.

How "closest" is computed (in the tool/repository, not guessed by the model):
- **Numeric ids** (ticket id, port id) → nearest by absolute difference, scoped to the **relevant, actionable set** (e.g. OPEN tickets in the manager's domain).
- **String identifiers** (catalog number, personal number, jack label) → closest by shared prefix / edit distance.
- Return the top few (≈3–5); if there are no near matches, say so plainly.

This complements "no fabricated arguments": missing → ask; **present-but-not-found → suggest nearest and let them pick.** Applies to every tool that takes an identifier (notably `resolve_ticket`, which a manager invokes **by ticket id**).

---

## 3. Core Domain Model

Shared entities used across domains.

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
| `team_id` | FK → OrgUnit (nullable) | which team the person belongs to (§ General Knowledge) |
| `phone` / `email` | string (nullable) | contact details (shown for team leaders / own-details) |
| `last_range_qualification` | date (nullable) | most recent shooting-range qualification; valid ~6 months — required for guard duty (HC-GD-9) |
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
| `reason` | string | short explanation (required when a soldier submits one) |
| `status` | enum | `PENDING` \| `APPROVED` \| `REJECTED`. A soldier-submitted constraint starts `PENDING` and needs `SHIFT_MANAGER` approval; **only `APPROVED` blocks count.** |
| `level` | enum | `CRITICAL` \| `HIGH` \| `MEDIUM` \| `LOW`. Priority tier (we store the level, **not** what the event is). `CRITICAL` (close-family wedding/funeral, medical) is **never overridden**; lower levels are soft. See SC-GD-5. |

> **Approval workflow (decided).** A soldier adds a constraint with dates + reason + a proposed **level**; it is created `PENDING`. The `SHIFT_MANAGER` reviews and approves/rejects it, **confirming/adjusting the level** (the approval step guards against everyone marking their own constraint `CRITICAL`). Only `APPROVED` blocks take effect. A constraint that **overlaps a shift the soldier is already assigned to is rejected at submission** (they must do that shift or arrange a swap first). At **approval** time the conflict is **re-checked** (GD-7): if a shift was assigned in those dates while the constraint sat pending, approval is **refused and the clash flagged** for the manager (resolve via swap/reassignment first) — never silently create a contradiction.
>
> **Submission windows (decided).** Constraints are **forward-looking** — declared *before* the affected period is planned, never for the period in progress:
> - **Quarterly duties (SUPPORT + SINGLE_DAY):** a constraint must be submitted **before the quarter it falls in begins** — you cannot add one for the **current** (already-assigned) quarter.
> - **WEEK_LONG (half-yearly):** constraints must be in **before that half-year begins** (file for the *next* half-year).
> Once a period is locked/assigned, no new constraints for it — use a **swap** (op #2) or the manager's **emergency reassignment** (GD-5). `add_date_block` rejects a submission whose dates fall in an already-planned period.

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

### OrgUnit (branch structure)
The department/team tree, surfaced by the General Knowledge agent (structure queries).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `name` | string | e.g. "Network Dept", "Network Team 1" |
| `kind` | enum | `DEPARTMENT` \| `TEAM` |
| `parent_id` | FK → OrgUnit (nullable) | a team's department; null for a top-level department |
| `leader_id` | FK → Personnel (nullable) | the team/department leader |
| `contact_note` | string (nullable) | optional; default contact is the leader's `phone`/`email` |

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
0. **Identify the ticket by id.** The manager resolves *by ticket id* (e.g. "resolve ticket 42"). If the id has **no exact match**, the agent does **not** fail or guess — it lists the **closest open tickets** and asks the manager to pick (see §2 "Fuzzy reference resolution").
1. **Validate** the intended outcome against hard rules (e.g., HC-LOG-2 before signing a computer; HC-NET-1 before allocating a port). Reject if it would violate one — the DB is left unchanged.
2. **Apply the fulfilment:**
   - *EQUIPMENT_REQUEST* → sign the chosen item to the requester (`signed_to = requester`), clear `reserved_for`, set status (`READY_TO_USE → IN_USE`); set `resolved_item_catalog`. The item is no longer held by the depot (`1234567`). Set **`handover_pending = true`** (the physical custody transfer isn't done yet — see Kitbag step).
   - *NETWORK_REQUEST* → write the WallJack→Port mapping, set the port `CONNECTED` / `allocated_to = requester`; set `resolved_port_id`.
3. **Close the ticket** (`status = RESOLVED`, stamp `resolved_at`).
4. **Record** an `EquipmentTransfer` (for equipment) and an `AuditLog` entry (always).

**Kitbag hand-over (equipment, decided).** Resolving the ticket records the assignment in Naatomatic, but the **official custody transfer happens in Kitbag** (`KITBAG_URL`) and is a **two-sided** action the system can't perform itself:
1. On resolve, the agent **instructs the manager** to pass the item to the recipient in Kitbag (serves the link).
2. The recipient must **accept** the item in Kitbag, then **confirm in the chat** ("I accepted CAT-xxxx in Kitbag").
3. Until the recipient confirms, the item stays **`handover_pending = true`**; the General Knowledge / logistics agent shows the recipient *"you have an item pending acceptance in Kitbag"* (with the link) in their self-view, and reminds them. On confirmation → `handover_pending = false`.
> The system **can't verify Kitbag directly** (external app), so completion is by the recipient's attestation in chat; what it *can* do is track the pending state, surface it, and keep reminding until acknowledged.

> This single tool answers Issue R2-7 (request↔fulfilment link), the "depot must be unassigned on resolution" requirement, and feeds R2-9 (transfer/audit rows). A future GUI/app, if ever added, would call the same tool — the logic is interface-independent.

### Audit Log
Append-only. Every mutating action writes one entry: `{ id, actor, action, entity_type, entity_id, before, after, timestamp }`.

---

## 4. Domain 1 — Network Infrastructure Agent

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
| `status` | enum | `DISCONNECTED` (available) \| `CONNECTED` (wired to a jack & allocated). Binary — there is no "disabled" state. |
| `allocated_to` | FK → Personnel (nullable) | the person holding this port (set iff CONNECTED) |

> The physical jack↔port link is stored **once**, on `WallJack.port_id` (below) — not duplicated on Port. Given a port, its jack is found by reverse lookup. (Earlier drafts also listed `Port.wall_jack_id`; that duplicate is removed.)

**WallJack**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `label` | string | physical jack label on the wall |
| `room` / `location` | string | |
| `port_id` | FK → Port (nullable, **unique**) | which port it patches to. Unique ⇒ **at most one wall jack per port**; null = unconnected jack. |

> **Classification is derived, not stored.** A wall jack inherits the classification of the port it's patched to (`port.classification`, via `port_id`). We deliberately do *not* duplicate it on WallJack to avoid the two drifting out of sync — the port/switch owns the classification. An **unconnected** jack (`port_id = null`) has no classification; that's expected, not an error.

### Network request payload (decided)
A `NETWORK_REQUEST` ticket must specify **both**: the **wall jack** to connect and the **desired classification** (the soldier asks for, e.g., a SECRET connection at jack WJ-042). These live in the ticket's `payload`, because an unconnected jack has no classification of its own until it's patched:
```
payload = { "wall_jack_id": <id>, "desired_classification": "CIVILIAN|GLOBAL|SECRET|TOP_SECRET" }
```
(For symmetry, an `EQUIPMENT_REQUEST` payload carries `{ "kind", "classification"? }`.) On resolution, the manager patches that jack to a port of the requested classification and the port is allocated to the requester (validated by HC-NET-1).

> The agent must **obtain both values from the requester** — if the soldier didn't say which jack or which classification, the agent **asks** rather than guessing (see §2 "No fabricated arguments"). The tool also validates that the jack exists and the classification is a real level.

### Capabilities (agent tools)
- `create_network_request(personnel, wall_jack, desired_classification)` — open a ticket (payload above).
- `get_ticket_status(ticket_id)` / `list_my_tickets(personnel)`.
- `allocate_port(personnel, port)` — validated by engine.
- `release_port(port)`.
- `map_walljack_to_port(wall_jack, port)`.
- `count_free_ports(filter: switch? classification?)`.
- `query_infrastructure(...)` — read-only reporting.

### Hard Constraints
- **HC-NET-1 — One port per classification per person.** A given personnel member may hold at most one allocated port of each classification (so up to 4 total, one per level).
  - Enforced on `allocate_port`: reject if person already holds a port at that classification.
  - Counts **CONNECTED** ports.
- **HC-NET-2 — Port status / allocation consistency.** A `CONNECTED` port must have an `allocated_to`; a `DISCONNECTED` port must not. (And, via the unique `WallJack.port_id`, a port has at most one wall jack.)

**Mapping updates are resolution-driven.** The WallJack→Port mapping (and the port's `allocated_to`) is updated **only when the network manager resolves the connection ticket** — never automatically on ticket creation. Flow: requester opens a `NETWORK_REQUEST` → manager physically patches → manager resolves the ticket → resolution writes the WallJack/Port changes.

**Release / disconnect (decided).** A `release_port` action frees a port: `CONNECTED → DISCONNECTED`, clear `allocated_to`, and unpatch the jack (`WallJack.port_id = null`). It writes an `AuditLog` entry (NET-4). This is the network counterpart to returning equipment.

**Leaver cleanup (decided).** When a person is deactivated (`active = false`), their holdings are automatically reclaimed in one step: **all their `CONNECTED` ports are released** (above) **and all their signed equipment is returned** to inventory (computers → `READY_TO_USE`, monitors unsigned; `signed_to` cleared, recorded as transfers). This runs as part of the deactivation action, with a **daily maintenance sweep** (§14) as a backstop so no inactive person is left holding ports or equipment.

**Port history (decided — NET-4).** Every port allocate / release / re-patch is recorded as an `AuditLog` row (`entity_type = "port"`, who/when/before/after). There is **no** separate port-transfer table — the movement trail is obtained by querying `AuditLog` for that port. (Equipment keeps its dedicated `EquipmentTransfer` table; ports rely on the generic audit log, which is enough for their simpler allocate/release lifecycle.)

### Network Connection Pipeline (decided)
The end-to-end flow for connecting a workstation — the network twin of the Logistics dispensing pipeline (§5). Validation happens **twice** (at request and at resolution) because port stock and the requester's holdings can change in between.

1. **Request (soldier, via chat).** The soldier asks to connect a workstation. The agent needs **two** details — the **wall jack** and the **desired classification**. If either is missing it **asks** (never guesses — §2). → payload `{wall_jack_id, desired_classification}`.
2. **Validation — gate #1.** Reject before opening a ticket if: the jack/classification don't resolve to real values; the requester already holds a port of that classification (**HC-NET-1**); or there is no available (`DISCONNECTED`) port on a switch of that classification.
3. **Ticket opens** (`NETWORK_REQUEST`, `OPEN`, with the payload). The soldier can query its status anytime.
4. **Manager review (pull-based).** The `NETWORK_MANAGER` asks the chat for open network tickets — no push alerts. Only the network-manager role can act.
5. **Physical patch.** The manager physically wires the wall jack to a free port on a switch of the requested classification.
6. **Resolve (manager, via chat) — gate #2.** The manager runs `resolve_ticket` **by ticket id** (mistyped id → "did you mean?" list of the closest open tickets, §2). It **re-validates** (port still `DISCONNECTED`? requester still within HC-NET-1? switch classification correct?), then — resolution-driven — writes the WallJack→Port mapping, sets the port `CONNECTED` / `allocated_to = requester`, sets `resolved_port_id`, closes the ticket (`RESOLVED`), and writes an `AuditLog` row. If re-validation now fails, resolution is refused and the ticket stays open with a reason.
7. **Done.** The soldier's jack is live on the requested network; the system now knows they hold one port of that classification (a second such request is blocked by HC-NET-1). Disconnect later via `release_port`; deactivation triggers leaver cleanup.

> Same backbone as §5: **two-gate validation**, **role-scoped** action, **resolution-driven** state change, **no fabricated identifiers**, and **did-you-mean** on a bad ticket id.

---

## 5. Domain 2 — Logistics Operations Agent

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
| `handover_pending` | bool | true after a ticket assigns the item, until the recipient **accepts it in Kitbag** (see resolution flow). |
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

## 6. Domain 3 — Guard Duty Scheduling Agents

Two distinct scheduling models sharing the **Justice Table**.

### Shared entities

**Shift**

> **Duty types:** `WEEK_LONG` and `SINGLE_DAY` are guard shifts. `SUPPORT` is the round-the-clock **customer-support standby** duty — a person on call to handle customers' support tickets. ⚠️ **Naming:** a SUPPORT shift is unrelated to the internal **Ticket** entity (§3), which is a branch-internal request about network/logistics/shifts. Different concepts — don't conflate.
>
> **SUPPORT coverage (decided).** Every single day must have **exactly one** SUPPORT person on call (continuous 24/7 cover). Weekdays (Sun–Thu) are one-day SUPPORT shifts; the **weekend is one shift covering Friday + Saturday** assigned to a single person (spans 2 days, counts **double** = 2 points).
>
> **The SUPPORT roster is generated a quarter ahead by maintenance (decided — GD-2).** Unlike guard shifts (whose dates are handed in), SUPPORT dates are "every day," so the system generates them itself: a **quarterly maintenance step** (see §14) lays out the upcoming quarter's slots — weekday singles + Fri–Sat weekend pairs tiling every day exactly once — and **assigns them ahead** to eligible Sadir (`can_do_support`) using the **same Justice-Table fairness** (lowest burden first, constraints respected). It's idempotent: it only generates a quarter that isn't already laid out. A **coverage check** (`check_support_coverage`) flags any uncovered day (gap) or any day with two people (overlap) — a safety net if a slot is later cancelled. HC-GD-7 already prevents one person covering two overlapping days.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `type` | enum | `WEEK_LONG` \| `SINGLE_DAY` \| `SUPPORT` (Sadir-only) — drives quota counting / burden |
| `time_of_day` | enum (nullable) | `DAY` \| `NIGHT` — informational only, for `SINGLE_DAY` shifts; does **not** affect quotas (1 day = 1 night) |
| `start_date` / `end_date` | date | |
| `eligible_population` | enum (nullable) | `KEVA` \| `SADIR`; null = either |
| `required_rank` | enum (nullable) | Rank; null = any rank |
| `assigned_to` | FK → Personnel (nullable) | the **primary** |
| `reserve_id` | FK → Personnel (nullable) | the **reserve** (backup) — steps in on a last-minute drop-out (GD-5) |
| `status` | enum | `OPEN` \| `ASSIGNED` \| `COMPLETED` \| `CANCELLED` |

**Shift eligibility:** a person is eligible only if they (1) match every non-null targeting field (population, rank — HC-GD-0), (2) have the duty-type flag for this shift's `type` set true (HC-GD-6 — e.g., SUPPORT requires `can_do_support`), and (3) are not date-blocked on the shift's dates (HC-GD-5). The balancing/quota logic then operates within that eligible pool.

**JusticeTable** — derived/maintained tally per person:
| Field | Type | Notes |
|-------|------|-------|
| `personnel_id` | FK | |
| `week_long_count` | int | Keva: WEEK_LONG shifts done this calendar year |
| `single_day_count` | int | Keva: SINGLE_DAY shifts done this calendar year |
| `week_long_carryover` | int (signed) | Keva: WEEK_LONG carryover = cumulative (did − fair share). **Positive** = did more than peers → owes fewer next year; **negative** = did fewer → owes more. See HC-GD-4. |
| `single_day_carryover` | int (signed) | Keva: SINGLE_DAY carryover, same signed convention |
| `shifts_burden_points` | decimal | Sadir **shifts** fairness pool (WEEK_LONG + SINGLE_DAY + ad-hoc) |
| `support_burden_points` | decimal | Sadir **SUPPORT** ("tickets") fairness pool |
| `period_start` | date | quota window anchor (Jan 1 of the calendar year) |

**Burden points — two separate pools (decided — GD-3).** Sadir fairness is tracked in **two separate pools**, balanced **independently**. Doing a lot of one does **not** excuse a soldier from the other — guard/ad-hoc "shifts" and customer-support ("ticket") standby are tracked totally separately:
| Pool | Counts | Points |
|------|--------|--------|
| **Shifts** (`shifts_burden_points`) | WEEK_LONG + SINGLE_DAY + **ad-hoc** | 7 per week-long, 1 per single-day, 0.5 × days per ad-hoc |
| **Support** (`support_burden_points`) | SUPPORT standby | days covered — weekday 1, **Fri–Sat weekend 2** |

Each pool is balanced on its own: a SUPPORT shift goes to the eligible Sadir with the lowest **support** points; a guard shift or ad-hoc to the lowest **shifts** points. (Keva guard duty is quota/count-based, not points; Keva use the shifts pool only as the ad-hoc tie-break.)

### Shared hard constraints (eligibility — apply to Keva, Sadir, and ad-hoc)
- **HC-GD-0 — Population/rank match.** An assignment may only go to a person matching its `eligible_population` and `required_rank` (when set).
- **HC-GD-5 — Availability (hard part = CRITICAL).** A person must not be assigned over an **`APPROVED`, `CRITICAL`** date block — that's absolute. Lower-level approved blocks (`HIGH`/`MEDIUM`/`LOW`) are **soft**: normally still avoided, but overridable as a last resort (see SC-GD-5). Pending/rejected blocks don't count.
- **HC-GD-6 — Duty-type eligibility.** A person must have the matching duty-type flag set true: `can_do_week_long` for WEEK_LONG shifts, `can_do_single_day` for SINGLE_DAY shifts, `can_do_support` for SUPPORT shifts, `can_do_adhoc` for ad-hoc missions. (SUPPORT shifts are **Sadir-only**, and `can_do_support` is false until a member completes the required course.)
- **HC-GD-7 — No overlapping assignments.** A person may not be assigned to two assignments whose date ranges overlap — at most one shift/SUPPORT/ad-hoc at a time. Applies across all assignment types (a guard shift and an ad-hoc mission on the same day is a violation).
- **HC-GD-9 — Range qualification (guard shifts only).** A person assigned to (or reserve for) a `WEEK_LONG`/`SINGLE_DAY` guard shift must be **range-qualified** — `last_range_qualification` within ~6 months. Guard duty is armed, so an expired/missing qualification blocks assignment until renewed. Does **not** apply to SUPPORT (unarmed) or ad-hoc. Surfaced to the soldier by the General Knowledge agent (see §7.5). *(HC-GD-8 = shift reserve differs from primary; see §6.B / GD-5.)*

### A. Keva (career) — annual quotas with carry-over
Base annual target per Keva member (calendar year, Jan 1 – Dec 31):
- **HC-GD-1 — 2 `WEEK_LONG` shifts per year.**
- **HC-GD-2 — 4 `SINGLE_DAY` shifts per year** (day and night count the same — 1 day = 1 night).
- The two quotas are tracked **independently** (single-day shifts do not offset the week-long requirement, or vice-versa).
- SUPPORT shifts do not apply to Keva at all — they are **Sadir-only** (see §6.B).
- **Year-boundary (GD-6):** a shift straddling Dec→Jan counts toward the calendar year of its **`start_date`** (e.g. Dec 30 → Jan 5 counts in the old year).

- **HC-GD-3 — Don't over-assign under normal operation.** The agent will not voluntarily assign a Keva member beyond their *effective* annual requirement for a shift type. Ad-hoc missions do **not** let a Keva member skip these guard quotas — the 2/4 still stand.

- **HC-GD-4 — Carryover (bidirectional, fairness-based).** The goal is that over time every *able* Keva does an equal **total** load. Carryover measures how much **more or less than the fair share** a member did that year — **not** just versus the fixed 2/4 — so it works even when the branch got fewer shifts than the full quota would need.
  - **Fair share** of a type for a year ≈ (Keva shifts of that type that year) ÷ (eligible Keva). At year end: `carryover += done − fair_share` (signed), stored in `week_long_carryover` / `single_day_carryover`. Positive = did more than peers → owes fewer next year; negative = did fewer → owes more.
  - **Effective requirement next year = base quota − carryover**, and balancing (SC-GD-3) serves the most-owed (most-negative) first.
  - **Compensation example (your case):** 10 week-long shifts, 10 Keva, fair share = 1 each. One member has an approved constraint and can't serve, so another **covers and does 2** while the rest do 1. The coverer did one **above** fair share → carryover **+1** → next year owes **one fewer**. The absent member did one **below** → carryover **−1** → owes **one more** next year. The other 8 are even.
  - In a **full** year (enough shifts for everyone's 2/4), fair share = quota, so this reduces to the simple case: did 3 week-long → carryover +1 → owe 1 next year.

> **Impossible-debt guard (decided).** A shortfall only rolls forward if the member was *able* to serve. A **one-off approved constraint** (a date block) is a temporary absence — the member is generally able, so their shortfall **does** carry (they do more next year, as above). But if they are **permanently unable** — the duty flag is off (e.g. `can_do_week_long = false`) — that quota **doesn't apply** to them at all and **no shortfall accrues**, so a permanently-restricted member never owes an unpayable, ever-growing debt. (A surplus always carries normally.)

- **SC-GD-3 — Balance among Keva.** Keva are not only *capped* (HC-GD-3) — the available shifts are **spread evenly across them**. Among eligible Keva who still owe a shift of that type, prefer the one who has done the **fewest of that type so far** this year (carryover-adjusted: someone who over-served is lower priority, someone who under-served is higher). So with, e.g., **10 Keva and 10 week-long shifts, each does 1** — nobody does 2 while someone does 0 — and only once everyone has had their fair share does anyone approach the cap.
  - Consequence: in a year with **fewer** shifts than the full quota would require, Keva each do a fair share *below* 2/4; the shortfall vs the target **carries forward** (HC-GD-4 negative carryover). So "exactly 2/4" is an obligation reconciled **over time**, not forced within a single year regardless of how many shifts the branch actually got.

**Ad-hoc for Keva:** Keva members *usually* don't get ad-hoc missions, but occasionally do. When they do, the ad-hoc burden (in the shifts pool, `shifts_burden_points`) is used **only as a tie-breaker** to balance ad-hoc fairness *among Keva* — it never substitutes for or reduces the 2/4 guard quotas.

### B. Sadir (mandatory) — soft optimization
- **No hard cap.**
- **SC-GD-1 — Balance the burden (per pool).** Prioritize the eligible soldier(s) with the **lowest points in the pool matching the duty kind** — the **shifts** pool (guard + ad-hoc) or the **support** pool — so shifts fairness and SUPPORT fairness are balanced independently.
- **SC-GD-2 — Tie-break.** When eligible soldiers are tied on the relevant pool's points, prefer the one with the **longest time since their last assignment of that kind**.
- **SC-GD-4 — Cross-quarter compensation (decided — GD-4).** The Sadir pools are **cumulative — never reset** — so balancing self-corrects across periods, mirroring the Keva carryover: a soldier who **covered an extra** shift carries higher points → is picked **less** next quarter (**compensated with one fewer**); a soldier who **couldn't serve** (approved constraint / unavailable) carries lower points → is picked **more** next quarter (**does one extra**). The compensation surfaces when the next quarterly roster (§14) is generated.
- **SC-GD-5 — Constraint tiering (decided).** Assignment first tries candidates with **no** constraint on the dates (by burden). Only if the duty **cannot otherwise be filled** does the engine fall back to candidates with non-critical constraints, **overriding the lowest level first** (LOW → MEDIUM → HIGH), and within a level by burden. **`CRITICAL` is never overridden.** So among equally-burdened candidates who all have constraints, the one with the *lowest* constraint level is chosen.

**Unfillable slot (decided — GD-4).** A slot with **no eligible/available person** is near-impossible with ~100 soldiers, but is still handled: the slot stays **`OPEN`** and is **flagged and escalated to the `SHIFT_MANAGER`** (via the coverage check, §6 SUPPORT note). The system **never fabricates an assignment** or silently leaves a hidden gap — the manager resolves it (e.g. by arranging coverage). Ordinary single-person unavailability is *not* unfillable: someone else covers now and SC-GD-4 compensates next quarter.

### Scheduling & assignment flow (decided)
Shift **dates are an input**, not something the system invents — the branch is *given* the coverage it must staff, and the agent's job is to **assign people** to those slots fairly.

**Two input modes, one assignment engine:**
1. **Batch list (the normal case).** The branch periodically receives a list of dated shifts to cover:
   - **Half-yearly** — the `WEEK_LONG` shifts (a week here, a week there across the half-year).
   - **Quarterly** — the `SINGLE_DAY` shifts.
   Each entry = `{start_date, length → WEEK_LONG/SINGLE_DAY, optional population/rank targeting}`. The agent creates the shift rows and assigns people.
2. **Single shift (the edge case).** A one-off `WEEK_LONG` or `SINGLE_DAY` shift can appear out of nowhere; it's created and assigned through the **same** logic, just one at a time.

**List intake (decided).** Inputting the shift-date list is a **`SHIFT_MANAGER`-only** action (role-gated per §9 — a regular soldier can't create shifts). It can be provided **two ways** (both supported):
- **Pasted/stated in chat** — e.g. "week-long: Jan 6–12, Feb 3–9; single-day: Mar 4, Mar 19." The agent parses it, **echoes the parsed shifts back for confirmation**, and asks about anything ambiguous rather than guessing a date (§2 no-fabrication).
- **CSV / Excel file** — the manager points the system at a local spreadsheet of dates + lengths; it's ingested into the same shift rows (same confirmation step).

**Assignment logic (both modes).** For each shift, pick the person to staff it using the **current Justice Table + constraints**:
- **Eligible pool** = passes HC-GD-0 (population/rank), HC-GD-5 (not date-blocked on the shift dates), HC-GD-6 (has the duty flag), HC-GD-7 (no overlapping assignment).
- **Within that pool**, choose by the population's model: **Keva** must still owe this shift type (effective requirement = base − carryover, HC-GD-3/4 — don't exceed it) and are **balanced among themselves** — pick the eligible Keva who has done the fewest of that type (SC-GD-3), so the load spreads evenly; **Sadir** = lowest points **in the matching pool** for the duty kind (SC-GD-1). Tie-break in both cases: longest time since last assignment of that kind (SC-GD-2).
- A batch is assigned **greedily and sequentially**, updating each person's burden as you go, so the whole list comes out balanced (this is exactly what the data generator already does). The manager can `suggest_assignment` (preview) or `assign_shift` (commit), and override a suggestion manually (still constraint-validated).
- **Every shift also gets a `reserve`** — the **next-best eligible** person (a different, available individual). The reserve is the backup for GD-5 below.

### Reserve & last-minute drop-out (decided — GD-5)
- **Reserve:** each shift carries a **primary** (`assigned_to`) and a **reserve** (`reserve_id`). The reserve must be eligible and available too (HC-GD-0/5/6/7), and is **a different person** from the primary (HC-GD-8). Being on standby earns no burden by itself.
- **Drop-out:** if the primary can't serve at the last minute (sick, etc.), the **reserve steps in** — the shift is reassigned to the reserve and the swap-in is recorded (audit).
- **Compensation (automatic):** the reserve (who actually served) gets the shift's **burden points**; the original (who didn't) gets none. Because the pools are cumulative (SC-GD-4), next rotation the **original is picked more** (lower burden) and the **reserve is eased** (higher burden) — i.e., the original repays the reserve. No separate debt record needed; the burden balancing *is* the compensation.
- **Cancellation:** a shift no longer needed → `status = CANCELLED`; no burden accrues, and both primary and reserve are freed.

### Operations (use cases)
The Guard Duty agent supports these five operations:

1. **Batch assign (manager).** Manager inputs a list of dates → fair assignment across the Justice Table + constraints. (`create_shifts` + `auto_assign`.)
2. **Swap (manager).** Manager swaps two people's shifts. **A swap must be same population *and* same shift type** — week↔week, day↔day, support↔support, between two Keva or two Sadir; **never cross-population** (a Keva can't take a Sadir shift or vice-versa) and **never cross-type**. The agent still **verifies the rest is legal**: each person eligible for the other's shift (HC-GD-0/5/6), no new overlap (HC-GD-7), Keva quotas intact. If legal → swap the assignees (burden moves with the shift, within the same pool); else → refuse with the reason. (`swap_shifts`.)
3. **Add constraint (soldier).** A soldier submits unavailability: dates + short reason + a **level** (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`). Created `PENDING`; **rejected immediately if it overlaps a shift they're already assigned to** (do that shift or arrange a swap first). Otherwise it waits for `SHIFT_MANAGER` approval, who **confirms/adjusts the level**; only once `APPROVED` does it take effect — `CRITICAL` becomes a hard block (HC-GD-5), lower levels soft (SC-GD-5). (`add_date_block` + `review/approve_date_block`.)
4. **View my shifts (soldier).** A soldier sees their own assignments — upcoming **and** previously completed — plus their Justice-Table standing. Self-service, pull-based. (`list_my_shifts`.)
5. **Assign a new shift (manager).** A single new shift arrives → assign someone considering the current Justice Table, existing assignments, and constraints. (`create_shift` + `suggest_assignment`/`assign_shift`.) Same engine as #1, one shift.

### Capabilities (agent tools)
- `create_shifts(source)` — **batch**, `SHIFT_MANAGER` only: ingest the list — a chat-pasted list **or** a CSV/Excel file path — parse to `{start_date, length, targeting?}`, echo back for confirmation, then create shift rows.
- `create_shift(type, start_date, ...)` — **single** shift (the edge case), `SHIFT_MANAGER` only.
- `assign_shift(shift, personnel)` — commit a manual assignment (constraint-validated).
- `auto_assign(shifts)` — assign a batch automatically, balanced by the Justice Table.
- `suggest_assignment(shift)` — preview the recommended person(s) per the model, without committing.
- `swap_shifts(shift_a, shift_b)` — `SHIFT_MANAGER` only: swap two assignees. Requires **same population + same shift type**; then validates both eligible + no overlap + quotas (op #2).
- `add_date_block(start, end, reason, level)` — a soldier submits a constraint with a proposed level (→ `PENDING`; rejected if it overlaps their own existing assignment).
- `review_date_blocks()` / `approve_date_block(id)` / `reject_date_block(id)` — `SHIFT_MANAGER` only: act on pending constraints.
- `list_my_shifts(include_past?)` — a soldier's own assignments, upcoming and past (op #4).
- `report_unavailable(shift)` / `activate_reserve(shift)` — last-minute drop-out: reassign the shift to its reserve, record the swap-in (GD-5).
- `cancel_shift(shift)` — `SHIFT_MANAGER`: mark a shift `CANCELLED`, free primary + reserve.
- `generate_support_roster(quarter)` — `SHIFT_MANAGER` / maintenance: tile a quarter into daily + weekend SUPPORT slots and assign ahead by fairness (GD-2). Idempotent.
- `check_support_coverage(date_range)` — report any gap (uncovered day) or overlap (two people) in the SUPPORT roster.
- `get_justice_table(filter: population?)` — fairness standings (transparency).
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
- Each ad-hoc mission contributes **0.5 × `days`** to the assignee's `shifts_burden_points` (folded into the shifts pool; half weight — no overnight stay). A 3-day mission = 1.5 points.

### Capabilities (agent tools)
- `create_adhoc_mission(title, dates, days, eligibility?)`.
- `assign_adhoc_mission(mission, personnel)` — validated via HC-GD-0 eligibility; balanced via SC-GD-1/2.
- `suggest_adhoc_assignment(mission)`.
- `mark_adhoc_completed(mission)`.

### Constraints
- **HC-GD-0, HC-GD-5, HC-GD-6 (Eligibility)** apply — population/rank match, date availability, and the `can_do_adhoc` flag, same pattern as shifts.
- **SC-GD-1/2 (Balancing + tie-break)** apply — ad-hoc assignment prefers the eligible soldier with the lowest `shifts_burden_points` (ad-hoc is part of the shifts pool).

**Ad-hoc & Keva (decided):** ad-hoc missions *are* assignable to Keva (occasionally), but for Keva they are **burden-tracked only** (in the shifts pool, used as the ad-hoc tie-break) and sit **entirely outside** the 2/4 guard quota — never counting toward or reducing it. See §6.A "Ad-hoc for Keva."

---

## 7.5 Domain 5 — General Knowledge Agent

A **read-only** help-desk / onboarding agent. It does **not** mutate state — it
explains how the system works and walks personnel through branch procedures, by
combining a **knowledge base** (static docs), **live DB reads** (structure, own
details, readiness), and **served resources** (files, links).

### What it answers
1. **Branch intro** — what the CombatAI branch is and what the assistant can do. *(knowledge doc)*
2. **Open a user to the closed networks** — the how-to for getting a workstation onto Civilian/Global/Secret/Top-Secret (the network-request flow). *(knowledge doc, links to §4)*
3. **Pre-shift readiness ("debts")** — you must be **range-qualified** (shooting range every 6 months) to be fit for guard duty. The agent reports the person's current qualification status (from `last_range_qualification`, HC-GD-9), **serves the weapon-safety file**, and **links to the SmartBase safety test**. *(DB read + resources)*
4. **Branch structure** — departments, teams, team leaders and their contact details (phone/email). *(DB read: OrgUnit + Personnel)*
5. **My own details** — a person can review their own record (rank, population, team, contacts, duty flags, qualification, assignments) to check it's correct. *(DB read, self only)*
6. **Information security** — what NOT to do in the office (e.g., connecting a wrong-classification PC to a port without permission). *(knowledge doc)*
- **Plus: explain the mechanics** — fairness/balancing (Justice Table, burden pools, carryover), eligibility rules, equipment & computer lifecycles, the ticket flow — in plain language, including *"why was I / wasn't I picked for this shift?"*. *(knowledge doc + DB read)*

### Knowledge base
Static markdown under **`knowledge/`** (real branch content): `01-branch-intro` (Branch 300 general + structure), `02-open-closed-networks` (user form + network process), `03-shift-readiness` (range booklet + weapon-safety test, half-yearly), `04-infosec` (נהלי בטחון מידע), `05-fairness-explained` (derived from the design), `06-roles-and-responsibilities` (branch role-holders), `07-site-and-general-procedures` (Elbit site security + general procedures). Policy text is kept verbatim (Hebrew). The agent retrieves the relevant doc and explains it (HE/EN). Reference resources (the weapon-safety file, the **SmartBase** test URL `SMARTBASE_TEST_URL`) are served as links/attachments — both still placeholders.

### Capabilities (agent tools — all read-only)
- `explain(topic)` — retrieve + explain **any** knowledge doc in `knowledge/` (intro, open-networks, shift-readiness, infosec, fairness, roles, site procedures, glossary) **or** a system mechanic. If a topic isn't covered, it says so (no fabrication).
- `get_branch_structure(filter?)` — the department→team tree with leaders and their contacts (OrgUnit + leader's phone/email), returned as a **nicely-formatted org tree** (and may render a visual). Shared info — not personal.
- `get_my_details(personnel)` — a **comprehensive self-view** (self only): personal details (rank, population, team, contacts), duty flags, **range-qualification status**, current equipment (incl. any `handover_pending`) and **transfer history**, network ports/settings, **past and upcoming** shifts / SUPPORT / ad-hoc, Justice-Table standing, and active date-blocks. Essentially "everything about me."
- `get_shift_readiness(personnel)` — range-qualification status + steps/file/SmartBase links to renew (HC-GD-9).
- `get_resource(name)` — serve a file or link (weapon-carry file, SmartBase tests `SMARTBASE_TEST_URL` / weapon-form `SMARTBASE_WEAPON_FORM_URL`, Kitbag `KITBAG_URL`).

### Notes
- **Read-only & privacy-scoped (strict):** it never changes data. A member can ask **anything about themselves** — details, equipment + history, past/future shifts, network settings, readiness — but **only about themselves**; it must refuse requests for another person's private data. Branch **structure** (teams, leaders, contacts) is the one shared, non-personal exception.
- **Range qualification is enforced elsewhere:** this agent *surfaces* readiness; the **scheduler enforces HC-GD-9** (no guard assignment without a valid qualification). One rule, two touch-points.

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
- Feeds `shifts_burden_points` (0.5 × days, folded into the shifts pool) and is included in conflict detection alongside guard duty.

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
- **Agent framework: LangChain.** ✓ Decided — orchestrator + per-domain agents with tool-calling.
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
A focused review found the Network domain thinner than Logistics. Fixed in this round: the duplicated Audit Log section; the `Port.wall_jack_id`/`WallJack.port_id` mismatch (now single, unique link); **HC-NET-2** (port status/allocation consistency) added and checked; HC-NET-1 counts CONNECTED ports; **ports are binary `CONNECTED`/`DISCONNECTED`** (the `DISABLED` state was removed). Remaining:

- **NET-1 — Network ticket payload [MED]. ✓ RESOLVED.** A `NETWORK_REQUEST` carries `payload = {wall_jack_id, desired_classification}` (the soldier specifies the jack and the level they want). See §4 "Network request payload". The generator now populates it.
- **NET-2 — Port states [MED]. ✓ RESOLVED.** A port is **binary**: `CONNECTED` or `DISCONNECTED`. The `DISABLED` state is removed — there is no "out of order" port status. `count_free_ports` simply counts `DISCONNECTED` ports.
- **NET-3 — Release / disconnect + leaver cleanup [MED]. ✓ RESOLVED.** `release_port` frees a port (`CONNECTED → DISCONNECTED`, clear `allocated_to`, unpatch the jack). On deactivation (`active = false`), leaver cleanup auto-releases all the person's ports **and** returns their signed equipment to inventory, with a daily maintenance sweep as backstop (see §4 + §14). *(Build-time: the actual release/return code lands with the tools/repository.)*
- **NET-4 — Port allocation history [LOW]. ✓ RESOLVED.** Port allocate/release/re-patch are logged as `AuditLog` rows (`entity_type="port"`); no separate port-transfer table — query AuditLog for a port's trail. See §4 "Port history".
- **NET-5 — Switch/port decommission [LOW]. ✓ DEFERRED (decided).** No retire/decommission path for switches or ports. They are slow-moving infrastructure; removal is a rare admin act handled by direct data edit if it ever happens. Revisit only if it becomes a real operational need.
- **NET-6 — Resolution-driven mapping unbuilt [build-time].** `resolved_port_id` and the allocate-on-resolve flow are specified (§3/§4) but unimplemented; the generator currently produces RESOLVED network tickets with no port link. Build with the Network tools (the `resolve_ticket` flow already covers the logic).
- **NET-7 — Reporting unexercised [build-time].** `count_free_ports` (count of `DISCONNECTED` ports) and `Switch.total_ports`-vs-actual-rows reconciliation get covered when the Network tools/tests are built.

**All Network design decisions are now settled** (NET-1…NET-5). What remains (NET-6, NET-7) is **build-time parity work** that lands when the Network tools/repository/tests are built — same status as Logistics' pending tools.

### Guard Duty agent gaps (review)
- **GD-1 — Balance among Keva [resolved].** Keva are spread evenly, not just capped — **SC-GD-3** (fewest-of-type first, carryover-adjusted). Carryover is measured vs **fair share**, not the fixed quota (HC-GD-4), so someone who covered for an absentee (did more than peers, even if still ≤ quota) is **compensated with one fewer next year**, and the absentee owes one more. See §6.A.
- **GD-2 — SUPPORT coverage completeness [resolved].** A **quarterly maintenance step** (§14) generates the upcoming quarter's SUPPORT slots (tiling every day; weekday singles + Fri–Sat weekend pairs) and assigns them ahead by Justice-Table fairness; idempotent. A `check_support_coverage` safety-net flags gaps/overlaps (e.g. after a cancellation). See §6 SUPPORT note.
- **GD-3 — Swap nuances [resolved].** A swap must be **same population AND same shift type** (week↔week, day↔day, support↔support; never Keva↔Sadir, never cross-type), then the usual eligibility/overlap/quota checks. Also decided: Sadir burden is tracked in **two separate pools** — **shifts** (guard + ad-hoc) and **SUPPORT** — balanced independently; see §6 "Burden points — two separate pools." See §6 op #2.
- **GD-4 — Unfillable shift [resolved].** A truly unfillable slot (no eligible/available person — near-impossible with ~100 soldiers) stays `OPEN` and is **flagged/escalated to the `SHIFT_MANAGER`**; never auto-fabricated. Ordinary single-person unavailability is handled by **SC-GD-4 cross-quarter compensation**: someone covers now, and the cumulative pools make the unavailable person do one extra next quarter while the coverer is compensated with one fewer. See §6.B.
- **GD-5 — Emergency reassignment & cancellation [resolved].** Every shift has a **reserve** (`reserve_id`, HC-GD-8 = distinct from primary). On a last-minute drop-out the reserve steps in; the reserve gets the burden and the original gets none, so SC-GD-4 makes the original repay (does more) and eases the reserve (does less) next rotation — the compensation is automatic. A no-longer-needed shift is `CANCELLED` (frees both). See §6 "Reserve & last-minute drop-out."
- **GD-6 — Year-boundary shift [resolved].** A shift straddling Dec→Jan counts toward the year of its **`start_date`**. See §6.A.
- **GD-7 — Approval-time conflict re-check [resolved].** Constraint **approval** re-checks for conflicts; if a shift was assigned in those dates while pending, the approval is **refused and flagged** (resolve via swap/reassignment). Largely pre-empted by the **submission-window rule** (constraints come in before the period is planned). See §3.
- **GD-8 — Constraint submission windows [resolved].** Constraints are forward-looking: quarterly duties (SUPPORT/SINGLE_DAY) must be submitted **before the quarter begins**; WEEK_LONG **before the half-year begins**. No constraints for a period already planned (use swap / emergency reassignment). See §3.
- **Build-time:** carryover/year-reset code (R2-6), `auto_assign`/Planner, the tools, AuditLog writes for assignments.

---

## 14. Time-Driven Maintenance

The system is chat-only and local — there is **no background clock**. Anything that should change "as time passes" is handled by a single **idempotent maintenance routine** (planned: `scripts/maintenance.py`). Idempotent = safe to run any number of times; running it twice in a day changes nothing extra.

**Daily tasks:**
| Task | Action |
|------|--------|
| **Formatting completion** | Each computer whose Formatting-Calendar slot `end_date` has passed and is still `FORMATTING`: if `reserved_for` is set → `READY_FOR_PICKUP` (someone is waiting to collect it); otherwise → `READY_TO_USE` (straight into storage — e.g. intake of a new computer). Custody stays with the depot until collected/used. |
| **Shift / mission completion** | Each `Shift` / `AdHocMission` with `end_date` in the past and status `ASSIGNED` → `COMPLETED`. (Nothing flips these otherwise.) |
| **Leaver cleanup (backstop)** | Any **inactive** person (`active = false`) still holding `CONNECTED` ports or signed equipment → release the ports and return the equipment to inventory (records audit/transfer rows). Normally done at deactivation; this sweep is the safety net. |
| **SUPPORT roster (quarterly)** | If the upcoming quarter's SUPPORT coverage isn't laid out yet, **generate it** — tile every day (weekday singles + Fri–Sat weekend pairs) — and **assign ahead** to eligible Sadir by Justice-Table fairness (GD-2). Idempotent: skips a quarter already done. Checked on every run; acts when a new quarter is near. |
| **Keva year reset** | On a new calendar year, for each Keva member: roll this year's deviation from fair share into `week_long_carryover` / `single_day_carryover` (`carryover += done − fair_share`, **signed** — positive = did more than peers → owes fewer next year, negative = owes more), reset the counts to 0, and re-anchor `period_start` to Jan 1. Subject to the impossible-debt guard (no shortfall for the permanently-unable) — see HC-GD-4 / R2-4. |

> **Do not reset the Sadir burden pools.** The Keva year reset touches only Keva counts/carryover. `shifts_burden_points` / `support_burden_points` are **cumulative and never reset** — that's what makes SC-GD-4 cross-quarter compensation work.

**Trigger (decided):** run the routine **on app startup, guarded to once per day** (compare a stored "last maintenance date" to today). No external scheduler required for the local deployment. Optionally, Windows Task Scheduler can also run `scripts/maintenance.py` daily — but the startup guard makes the system self-sufficient.

> Why idempotent + guarded rather than a real scheduler: it keeps a local, chat-only app self-contained (no daemon to install or keep alive) while guaranteeing the time-driven transitions happen at least once per day, and never double-apply.

---

*Schema and stack are confirmed (Python + LangChain + SQLAlchemy + SQLite, local, chat-only). Resolved: R2-1 (maintenance routine), R2-2 (HC-GD-7), R2-3 (SUPPORT coverage), R2-4 (defer under-served — bidirectional carryover), R2-6 (carryover policy), R2-7 (ticket resolution flow, chat-driven). The daily maintenance routine (§14) and the `resolve_ticket` flow (§3) are fully specified and pending build. Remaining open item: R2-9 (audit/transfer writes — first uses now specified: ticket resolution and decommissioning), best handled while building the Logistics/Network tools. R2-8 (computer state machine incl. the terminal `DECOMMISSIONED` state) is now defined; only the tool-level transition guard remains to build. The project structure template (`PROJECT_STRUCTURE.md`) lays out where each domain, tool, service, and test will live as we build.*
