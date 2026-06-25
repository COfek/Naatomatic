# Agent Tools Design Documentation

This document organizes and lists all agent tools defined under the `tools/` directory, detailing their implementation designs, constraints, and business logic from the system design specification (`DESIGN.md`).

---

## I. System-Wide Tool Design Principles

### 1. Agent vs. Engine Boundary
* **State Mutability:** The database (`naatomatic.db`) is the single source of truth. Every mutating tool runs in a transaction.
* **Validation Layer:** Hard constraints (`HC-*`) are enforced at the service/database layer (via a Validator/Rules engine). The agent proposes actions via a tool call, and the constraint engine validates and either commits or rolls back the transaction.
* **Role-Based Access Control (RBAC):** Every mutating tool checks `ctx.actor_personal_number` to ensure they have the necessary role.
  * Baseline (any authenticated member): Can open/cancel own tickets and query own details.
  * `NETWORK_MANAGER`: Scoped to Network domain tools.
  * `LOGISTICS_OFFICER`: Scoped to Logistics domain tools.
  * `SHIFT_MANAGER`: Scoped to Guard Duty and AdHoc scheduling tools.

### 2. "No Fabricated Arguments" Rule
* The LLM worker must **never guess or invent required tool arguments** (e.g. wall jack ID, classification, catalog number). 
* If a parameter is missing in the user request, the agent must ask a follow-up question instead of calling the tool with a default or simulated value.
* The tool validations backstop this by rejecting invalid or non-existent identifiers.

### 3. Fuzzy Reference Resolution ("Did you mean?")
* When an identifier is provided but not found, the tool returns the top 3–5 nearest candidates instead of hard-failing or guessing:
  * **Numeric IDs** (e.g., ticket ID, port ID) → nearest absolute difference among the active/actionable set.
  * **String IDs** (e.g., catalog number, personal number, jack label) → closest by shared prefix or edit distance.
* The agent displays these suggestions to the user to choose from.

---

## II. Shared Domain Concepts

### 1. Ticket Lifecycle & Resolution Flow
* **States:** `OPEN` ⇄ `ON_HOLD` → `RESOLVED` (terminal status).
* **Resolution Action:** When a manager calls `resolve_ticket`, the tool:
  1. Identifies the ticket by ID (uses fuzzy resolution if missing).
  2. Runs validation gates (e.g., checks `HC-LOG-2` or `HC-NET-1` against the requester).
  3. Applies the assignment:
     * **Logistics:** Set `signed_to = requester`, clear `reserved_for`, transition status to `IN_USE` or `READY_FOR_PICKUP`, and set `handover_pending = true`.
     * **Network:** Map `WallJack` to `Port`, and set the port status to `CONNECTED` and `allocated_to = requester`.
  4. Closes the ticket (`status = RESOLVED`, stamp `resolved_at`).
  5. Records transfer records/audit logs and commits the transaction.

### 2. Default Holder (Depot Sentinel)
* Sentinel personal number **`1234567`** represents the equipment depot.
* Broken or in-formatting items are signed to `1234567` (releasing them from real soldiers).
* Hard constraints `HC-LOG-1/2` are bypassed for this sentinel ID.

### 3. Leaver Cleanup
* When a personnel member is deactivated (`active = false`), the system must immediately release all their `CONNECTED` ports and return all their signed equipment to the depot (setting computer status to `READY_TO_USE` and clearing monitor custody).

---

## III. Domain Tool Specifications

### 1. General Knowledge Domain
**Module:** [general_knowledge_tools.py](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/general_knowledge_tools.py)  
**Access:** Read-only. Privacy-scoped (users can query their own details, but cannot request another's private data).

#### [explain](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/general_knowledge_tools.py#L12)
* **Description:** Retrieve and explain static knowledge files from `knowledge/` or details of a system mechanic.
* **Arguments:**
  * `topic: str` (file stem, e.g. `02-open-closed-networks`)

---

### 2. Network Infrastructure Domain
**Module:** [network_tools.py](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/network_tools.py)  
**Key Constraints:**
* **HC-NET-1:** A person may hold at most one connected/allocated port of each classification (`CIVILIAN`, `GLOBAL`, `SECRET`, `TOP_SECRET`) at a time.
* **HC-NET-2:** A `CONNECTED` port must have an `allocated_to`; a `DISCONNECTED` port must not.

#### [create_network_request](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/network_tools.py#L12)
* **Type:** Mutating (User baseline)
* **Description:** Opens a `NETWORK_REQUEST` ticket.
* **Arguments:**
  * `wall_jack_id: int`
  * `desired_classification: Literal["CIVILIAN", "GLOBAL", "SECRET", "TOP_SECRET"]`

#### [resolve_network_ticket](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/network_tools.py#L17)
* **Type:** Mutating (`NETWORK_MANAGER`)
* **Description:** Resolves the ticket, maps the wall jack to the designated port, allocates it to the requester, and sets the port to `CONNECTED`.
* **Arguments:**
  * `ticket_id: int`
  * `port_id: int`

#### [release_port](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/network_tools.py#L22)
* **Type:** Mutating (`NETWORK_MANAGER`)
* **Description:** Frees a port (state to `DISCONNECTED`, clears `allocated_to`, sets `WallJack.port_id = null`, and audits).
* **Arguments:**
  * `port_id: int`

#### [count_free_ports](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/network_tools.py#L26)
* **Type:** Read-Only
* **Description:** Counts `DISCONNECTED` ports (optionally by switch/classification).
* **Arguments:**
  * `classification: str | None = None`

#### [get_ticket_status](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/network_tools.py#L30)
* **Type:** Read-Only
* **Description:** Returns the status and history of a ticket.
* **Arguments:**
  * `ticket_id: int`

#### [query_infrastructure](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/network_tools.py#L34)
* **Type:** Read-Only
* **Description:** Lists switches, ports, and wall jacks.
* **Arguments:**
  * `switch: str | None = None`

---

### 3. Logistics Domain
**Module:** [logistics_tools.py](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py)  
**Key Constraints:**
* **HC-LOG-1:** Max 2 monitors per person.
* **HC-LOG-2:** Max 1 computer of each classification per person.
* **Computer Lifecycle Transitions:**
  * `(new)` → `FORMATTING`
  * `FORMATTING` → `READY_TO_USE` (unreserved), `READY_FOR_PICKUP` (reserved), or `DECOMMISSIONED` (IT failure)
  * `READY_TO_USE` → `IN_USE` or `BROKEN`
  * `IN_USE` → `READY_TO_USE` (on return) or `BROKEN`
  * `BROKEN` → `FORMATTING` (repair attempt) or `DECOMMISSIONED`
  * `READY_FOR_PICKUP` → `IN_USE` (handed to `reserved_for`) or `READY_TO_USE` (released to inventory)

#### [sign_equipment](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L28)
* **Type:** Mutating (`LOGISTICS_OFFICER` - REFERENCE IMPLEMENTATION)
* **Description:** Signs an item to a soldier. Checks `HC-LOG-1/2`. Sets `handover_pending = true` until accepted in Kitbag.
* **Arguments:**
  * `catalog_number: str`
  * `personnel_id: int`

#### [return_equipment](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L76)
* **Type:** Mutating
* **Description:** Returns item to storage. Flipped to `READY_TO_USE`, clears `signed_to`.
* **Arguments:**
  * `catalog_number: str`

#### [create_equipment_request](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L94)
* **Type:** Mutating (User baseline)
* **Description:** Opens request ticket. Validates projected caps against current holdings + reservations.
* **Arguments:**
  * `kind: Literal["MONITOR", "COMPUTER"]`
  * `classification: str | None = None`
  * `description: str | None = None`

#### [list_my_open_tickets](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L143)
* **Type:** Read-Only
* **Description:** Lists open requests for the current user.
* **Arguments:** None

#### [resolve_equipment_ticket](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L168)
* **Type:** Mutating (`LOGISTICS_OFFICER`)
* **Description:** Signs over item, links ticket, closes it, sets `handover_pending = true`.
* **Arguments:**
  * `ticket_id: int`
  * `catalog_number: str`

#### [set_equipment_status](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L173)
* **Type:** Mutating (`LOGISTICS_OFFICER`)
* **Description:** Enforces legal state machine transitions. Flipped to depot `1234567` if status becomes `BROKEN` or `FORMATTING`.
* **Arguments:**
  * `catalog_number: str`
  * `status: str`

#### [decommission_item](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L177)
* **Type:** Mutating (`LOGISTICS_OFFICER`)
* **Description:** Flipped to `DECOMMISSIONED` (terminal), clears custody, records removal transfer, and audits.
* **Arguments:**
  * `catalog_number: str`

#### [query_inventory](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L181)
* **Type:** Read-Only
* **Description:** Queries available equipment (excludes decommissioned/in-use).
* **Arguments:**
  * `kind: str | None = None`
  * `classification: str | None = None`

#### [generate_logistics_dashboard](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/logistics_tools.py#L220)
* **Type:** Read-Only
* **Description:** Returns JSON summary metrics and triggers rendering of a PNG chart file.
* **Arguments:**
  * `metric: str` (equipment_shortage, ticket_status_distribution, inventory_by_category, broken_by_type, tickets_over_time)
  * `chart_type: Literal["bar", "horizontal_bar", "line", "pie"]`
  * `date_range: dict | None = None`
  * `group_by: str | None = None`
  * `top_n: int = 10`
  * `filters: dict`

---

### 4. Guard Duty Domain
**Module:** [guard_duty_tools.py](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py)  
**Key Constraints:**
* **HC-GD-0:** Candidate must match targeted population/rank.
* **HC-GD-5 (Availability):** Cannot assign over `APPROVED` constraints marked `CRITICAL` (wedding, medical, etc.). Low/Medium/High blocks are soft constraints (`SC-GD-5`) overridden as a last resort.
* **HC-GD-6:** Must have the corresponding flag set (`can_do_week_long`, `can_do_single_day`, `can_do_support`). Note that `SUPPORT` is Sadir-only.
* **HC-GD-7:** No overlapping assignments (at most one active shift, support, or ad-hoc mission on a given date).
* **HC-GD-9:** Must be range-qualified (`last_range_qualification` within the last 6 months) for armed guard shifts.
* **Keva Quotas:** `HC-GD-1` (2 `WEEK_LONG` / year) and `HC-GD-2` (4 `SINGLE_DAY` / year). Balanced using carryover (`HC-GD-4`) which calculates deviation vs. fair share: `effective_requirement = base - carryover`. Carryover is bidirectional, but restricted by the **impossible-debt guard** (no shortfall accrues if `can_do_*` is false).
* **Sadir Burden Pools:** Two separate cumulative pools balanced independently: **Shifts** (week-long = 7, single-day = 1, ad-hoc = 0.5 * days) and **Support** (weekday = 1, weekend Fri-Sat = 2).

#### [create_shifts](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L14)
* **Type:** Mutating (`SHIFT_MANAGER`)
* **Description:** Parses a batch text or CSV/Excel file of dates and lengths, echoes them back for confirmation, and creates shift records.
* **Arguments:**
  * `source: str`

#### [create_shift](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L18)
* **Type:** Mutating (`SHIFT_MANAGER`)
* **Description:** Creates a single shift.
* **Arguments:**
  * `type: Literal["WEEK_LONG", "SINGLE_DAY", "SUPPORT"]`
  * `start_date: str`

#### [assign_shift](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L23)
* **Type:** Mutating (`SHIFT_MANAGER`)
* **Description:** Manually assigns a primary and reserve assignee.
* **Arguments:**
  * `shift_id: int`
  * `personnel_id: int`

#### [auto_assign](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L27)
* **Type:** Mutating (`SHIFT_MANAGER`)
* **Description:** Assigns a batch of shifts sequentially, prioritizing the lowest burden/most-owed personnel. Sets primary and reserve assignees.
* **Arguments:**
  * `shift_ids: list`

#### [suggest_assignment](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L31)
* **Type:** Read-Only
* **Description:** Previews the top matching primary and reserve candidates for a shift.
* **Arguments:**
  * `shift_id: int`

#### [swap_shifts](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L35)
* **Type:** Mutating (`SHIFT_MANAGER`)
* **Description:** Swaps two assignments. Must be **same population** and **same shift type** (no cross-population, no cross-type swaps). Re-validates eligibility and overlaps.
* **Arguments:**
  * `shift_a: int`
  * `shift_b: int`

#### [add_date_block](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L39)
* **Type:** Mutating (User baseline)
* **Description:** Adds unavailability constraint (starts `PENDING`). Rejected immediately if it overlaps a shift already assigned to the user. Must be submitted before the planning period begins (forward-looking).
* **Arguments:**
  * `start_date: str`
  * `end_date: str`
  * `reason: str`
  * `level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]`

#### [review_date_blocks](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L44)
* **Type:** Read-Only (`SHIFT_MANAGER`)
* **Description:** Lists `PENDING` date blocks.
* **Arguments:** None

#### [approve_date_block](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L48)
* **Type:** Mutating (`SHIFT_MANAGER`)
* **Description:** Approves a date block. Re-checks conflicts; if a shift was assigned in those dates while pending, approval is refused.
* **Arguments:**
  * `block_id: int`

#### [list_my_shifts](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L52)
* **Type:** Read-Only
* **Description:** Lists current user's past and upcoming shifts.
* **Arguments:**
  * `include_past: bool = True`

#### [get_justice_table](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L56)
* **Type:** Read-Only
* **Description:** Lists cumulative points and carryovers.
* **Arguments:**
  * `population: str | None = None`

#### [generate_support_roster](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L60)
* **Type:** Mutating (`SHIFT_MANAGER` / maintenance)
* **Description:** Generates daily and weekend (Fri-Sat) support slots for a quarter and auto-assigns Sadir personnel based on the Support pool.
* **Arguments:**
  * `quarter: str`

#### [check_support_coverage](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/guard_duty_tools.py#L64)
* **Type:** Read-Only
* **Description:** Scans support assignments in a range and flags gaps or overlaps.
* **Arguments:**
  * `start_date: str`
  * `end_date: str`

---

### 5. AdHoc Missions Domain
**Module:** [adhoc_tools.py](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/adhoc_tools.py)  
**Key Constraints:**
* **HC-GD-0, HC-GD-5, HC-GD-6, HC-GD-7:** Same population/rank matching, date block checks, eligibility flag (`can_do_adhoc`), and overlap validations apply.
* **Burden Points:** Contributes **0.5 * `days`** to the assignee's **Shifts** burden pool (shares pool with guard duty).
* **Keva:** Tracking only; ad-hoc missions never offset Keva guard quotas.

#### [create_adhoc_mission](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/adhoc_tools.py#L10)
* **Type:** Mutating (`SHIFT_MANAGER`)
* **Description:** Creates an ad-hoc mission record.
* **Arguments:**
  * `title: str`
  * `start_date: str`
  * `days: int = 1`

#### [assign_adhoc_mission](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/adhoc_tools.py#L15)
* **Type:** Mutating (`SHIFT_MANAGER`)
* **Description:** Assigns personnel, validating availability and balancing via the Shifts burden pool.
* **Arguments:**
  * `mission_id: int`
  * `personnel_id: int`

#### [suggest_adhoc_assignment](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/adhoc_tools.py#L19)
* **Type:** Read-Only
* **Description:** Previews recommended candidates for the mission.
* **Arguments:**
  * `mission_id: int`

#### [mark_adhoc_completed](file:///c:/Users/yonil/Documents/AgentsTraining/Naatomatic/tools/adhoc_tools.py#L23)
* **Type:** Mutating
* **Description:** Sets mission status to `COMPLETED`.
* **Arguments:**
  * `mission_id: int`
