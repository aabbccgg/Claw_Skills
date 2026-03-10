---
name: auto-iterate
description: Execute user-defined iterative workflows (single, nested, sequential, or parallel) until explicit completion criteria are met. REQUIRED when user requests 自动迭代, 循环迭代, 迭代, 循环执行, 重复直到, “iterate until”, or “loop until”.
metadata:
  {
    "openclaw":
      {
        "emoji": "🔄",
      },
  }
---

# Auto-Iterate

Use this skill as an orchestration protocol for **user-defined loops** (not a fixed template).

<!-- REVIEW [S-05]: Procedure order and trigger logic are currently scattered across §§1, 4, 5, 6, 7, and 8. CHANGE: Insert a new opening section before `## Non-Negotiables` so the reader sees the activation criteria and top-level control flow first. PROPOSED INSERTION TEXT:
## 1. Purpose and Trigger
Use this skill only for user-directed iterative workflows with explicit stop conditions. Treat the user’s requested loop definition as authoritative; do not invent hidden goals or autonomous follow-on work.

Start the skill only when all prerequisites are true:
- The user explicitly requested looping / iteration / repeat-until behavior.
- There is at least one executable step, function, or branch definition.
- There is at least one explicit, testable completion criterion.
- The reporting destination is known and can be persisted as `report_to`.

If any prerequisite is missing, stop and ask for clarification. Do not create state, spawn subagents, or schedule cron until the admission contract is satisfied.

Top-level execution order:
1. Validate trigger and inputs.
2. Establish ownership and canonical state.
3. Run the coordinator state machine until `complete` or `paused`.
4. Perform terminal cleanup.
-->

<!-- REVIEW [S-01]: There is no explicit role/ownership model, which makes it unclear who may mutate state, schedule/remove cron, or send authoritative reports. CHANGE: Insert a dedicated ownership section immediately after the proposed Purpose and Trigger section. PROPOSED INSERTION TEXT:
## 2. System Roles and Ownership
Define exactly four actors:
1. **Coordinator** — the only actor allowed to mutate `STATE.md`, transition workflow state, schedule/remove cron jobs, and emit final authoritative reports.
2. **Subagent** — performs heavy work only; it must not modify orchestration state directly.
3. **Cron wake session** — an isolated coordinator invocation that resumes exclusively from persisted state.
4. **Interactive origin session** — the human-facing setup turn that validates inputs, records `report_to`, and establishes the first wake chain.

Ownership rules:
- `STATE.md` has a single writer: the active coordinator.
- Subagents are read-only with respect to orchestration state.
- Cron exists only to wake the coordinator for one cycle.
- User-visible routing must always come from persisted `report_to`, never inferred from ambient session context.
-->

## Non-Negotiables

<!-- REVIEW [S-05]: MOVE this section to §3 in the restructured version (`Hard Rules`). -->

- Use `STATE.md` as single source of truth.

<!-- REVIEW [S-03]: `STATE.md` is declared authoritative, but the current format is a loose markdown bullet list that is too ambiguous for crash-safe orchestration. CHANGE: Tighten this rule so state is machine-parseable and deterministic. PROPOSED REPLACEMENT TEXT:
- Use `STATE.md` as single source of truth. `STATE.md` must contain exactly one fenced YAML document matching the canonical schema in §4. Do not store orchestration state in freehand prose, ad-hoc bullets, or chat memory.
-->

- Continue only via cron self-wake using the **`cron` tool** (never `exec("openclaw cron ...")`).

<!-- REVIEW [C-04]: The skill repeats the forbidden shell-out pattern in multiple places, which reinforces the anti-pattern instead of replacing it with one canonical positive rule. CHANGE: Normalize the wording around the allowed mechanism. PROPOSED REPLACEMENT TEXT:
- Schedule and remove wakes only through first-class tool calls: `cron(action="add")` and `cron(action="remove")`. Do not shell out to cron via `exec`.
-->

- Set `delivery: {mode: "none"}` on **every** cron job.
- Set `payload.timeoutSeconds: 300` on every cron job. This is wake session runtime cap, **not** polling delay.
- Heavy execution (e.g., 5+ file edits) must run in subagent.
- Report only via `message(action="send")`.
- Spawned subagents must use `runTimeoutSeconds: 7200`.
- **Every `sessions_spawn` must be followed by a cron wake in the same turn.** No cron = no monitoring = broken loop.

<!-- REVIEW [F-06]: This rule states the requirement but not the atomic commit order around spawn/state/cron. That leaves room for orphaned subagents or lost wake chains. CHANGE: Replace this with an explicit transaction rule. PROPOSED REPLACEMENT TEXT:
- Every subagent spawn must occur inside one coordination transaction: acquire coordinator lock → persist pending work + spawned session id → add successor cron wake → persist returned cron job id → release lock. Ending the turn after spawn without a durable next wake is invalid.
-->

- When spawning subagents via `sessions_spawn`, always pass your own `agentId` (same as cron).
- Max total runtime per task: 3h (`deadline_at`). Exceeding it pauses loop and reports.

<!-- REVIEW [C-02]: `deadline_at` is described here as a workflow-wide cap, but §5 later resets it on advance. That is a semantic conflict between a global deadline and a rolling lease. CHANGE: Split the concepts. PROPOSED REPLACEMENT TEXT:
- Max total workflow runtime: 3h (`workflow_deadline_at = started_at + 3h`). Do **not** reset it. If a per-round or per-wake timeout is needed, store it in a separate field such as `coordination_lease_expires_at` or `await_timeout_at`.
-->

- Re-read this skill every 3 rounds.
- On init, add heartbeat entry `[auto-iterate:<id>]`.

<!-- REVIEW [C-03]: Heartbeat is introduced, but there is no operating contract for what it contains, when it is updated, or who is responsible for removing it. CHANGE: Turn heartbeat into an explicit liveness record. PROPOSED REPLACEMENT TEXT:
- On init, create heartbeat entry `[auto-iterate:<id>]` containing at least `state_path`, `status`, `last_coordinator_at`, and `next_expected_wake_at`. Update it on every successful coordinator cycle; remove it only after terminal cleanup is durably recorded.
-->

- Every cron wake message must be **self-contained**: include state path, subagent session key, workdir, report_to, and the self-propagating constraint line (see §6).

<!-- REVIEW [C-05]: The wake-message contract is incomplete for isolated recovery because it omits lineage, active cron identity, deadlines, and the next expected action. CHANGE: Expand the required fields. PROPOSED REPLACEMENT TEXT:
- Every cron wake message must be self-contained: include iteration id, round, absolute state path, workdir, current loop/branch id, subagent session key, `report_to`, current cron job id, workflow deadline, heartbeat tag, and the self-propagating constraint line (see §9).
-->

---

## 1) Admission Gate — REQUIRED BEFORE ROUND 1

<!-- REVIEW [S-05]: MOVE this section to §1 in the restructured version (`Purpose and Trigger`). -->

Do **not** start iteration until both are present:

1. **At least 1 executable step/function**
2. **At least 1 explicit completion criterion**

If either is missing: block execution, ask user for missing info, and wait.

Minimum acceptable structure:
- Steps: `func1 -> func2 -> ...` (or loop definitions)
- Criteria: testable completion condition(s)

---

## 2) Loop Topology & Execution Semantics

<!-- REVIEW [S-05]: MOVE this section to §6 in the restructured version (`Initialization` / topology validation feeding the coordinator cycle). -->

Infer mode from wording:
- Sequential: `先...再...`, `做完A后做B`
- Parallel: `同时`, `并行`, `一起推进`

If ambiguous/conflicting, ask explicitly.

Validate each loop has:
- ordered function list
- loop-local exit condition
- dependency/parallel-safety constraints

Execution:

<!-- REVIEW [S-04]: Parallel execution is described only in prose, but the schema has no first-class way to represent branches, branch-local progress, or merge policy. CHANGE: Make branch structure explicit. PROPOSED REPLACEMENT TEXT:
Execution:
- Single loop: run all functions in order, then evaluate exit condition.
- Nested loop: enter child loop → run until child exit → return to parent.
- Parallel loop: require `branches[]` with stable `branch_id` values; each branch must track `funcs`, `status`, `current_func`, `subagent_session`, `retry_count`, `no_fix_rounds`, and `last_progress_at`.
- Parallel loop must also declare `merge_policy`: `all-success` | `quorum` | `custom-user-criterion`.
- Spawn at most one active subagent per branch.
- Parent loop advances only when its declared merge policy evaluates true.
- Multiple loops:
  - Sequential mode: loop1 → loop2 → ...
  - Parallel mode: progress actionable loops concurrently each wake.
-->

- Single loop: run all functions in order, then evaluate exit condition.
- Nested loop: enter child loop → run until child exit → return to parent.
- Parallel branches: if independent/safe, run branch subagents in parallel, then merge outputs.

<!-- REVIEW [M-05]: A single global retry counter cannot represent health of independent parallel branches. CHANGE: Add per-branch resilience accounting. PROPOSED REPLACEMENT TEXT:
- Parallel branches: if independent/safe, run named branch subagents in parallel, track `retry_count` and `no_fix_rounds` per branch, then merge outputs using the loop’s declared `merge_policy`.
-->

- Multiple loops:
  - Sequential mode: loop1 → loop2 → ...
  - Parallel mode: progress actionable loops concurrently each wake.

---

## 3) STATE.md Schema (Required)

<!-- REVIEW [S-05]: MOVE this section to §4 in the restructured version (`State Model`). -->

State dir:
`~/.openclaw/<your_agent_workspace>/iterations/<YYYYMMDD-HHMMSS-desc>/`

`STATE.md` must include:

<!-- REVIEW [S-03]: Replace the loose markdown pseudo-schema with one canonical fenced YAML document so isolated cron wakes can parse it deterministically. CHANGE: Replace the schema block below. PROPOSED REPLACEMENT TEXT:
```yaml
id: <iteration_id>
task: <user task summary>
target: <global completion criteria>
status: running|awaiting-review|paused|complete
started_at: <ISO8601>
workflow_deadline_at: <ISO8601>  # fixed = started_at + 3h; never reset
current: <human-readable current action>
round: <int>
loops_mode: sequential|parallel>
origin:
  session_kind: interactive-dm|interactive-group|isolated-cron
  session_id: <session_id>
  report_to:
    channel: <channel>
    target: <user_or_group_id>
    threadId: <topic_id optional>
coordination:
  state_version: <int>
  lock_owner: <session_id|null>
  lock_acquired_at: <ISO8601|null>
  last_committed_at: <ISO8601>
  current_cron_job_id: <job_id|null>
  next_cron_job_id: <job_id|null>
  pending_transition: idle|spawned|awaiting-review|advancing|pausing|completing
  poll_streak: <int>
  heartbeat_tag: "[auto-iterate:<id>]"
loops:
  - id: <loop_id>
    parent: <null|loop_id>
    kind: single|nested|parallel
    funcs: [<func...>]
    exit_condition: <text>
    status: pending|running|paused|complete
    round: <int>
    current_func: <index/name|null>
    branches: []
subagents:
  active: []
  last_result: null
progress:
  no_fix_rounds: <int>
  retry_count: <int>
```
-->

```md
- id: <iteration_id>
- task: <user task summary>
- target: <global completion criteria>
- status: running|paused|complete|awaiting-review
- started_at: <ISO8601>
- deadline_at: <ISO8601, started_at+3h>
- current: <human-readable current action>
- round: <int>
- loops_mode: sequential|parallel
- loops:
  - id: <loop_id>
    parent: <null|loop_id>
    funcs: [<func...>]
    exit_condition: <text>
    round: <int>
    status: pending|running|paused|complete
    current_func: <index/name>
- active_loops: [<loop_id>...]
- subagent_session: <latest session id|null>
- last_subagent_result: <summary|null>
- no_fix_rounds: <int>
- retry_count: <int>  # subagent crash/timeout respawn count, max 4
- cron_job_id: <current cron job id|null>  # for cleanup on advance/complete
- complexity: trivial|simple|moderate|complex
- heartbeat_tag: "[auto-iterate:<id>]"
- report_to:
    channel: <channel>
    target: <user_or_group_id>
    threadId: <topic_id optional>
```

<!-- REVIEW [M-04]: The current schema has no single-writer or versioning discipline, so overlapping wakes can race and clobber each other. CHANGE: Add explicit coordination-lock metadata and a write rule. PROPOSED REPLACEMENT TEXT:
Add to the canonical schema:
```yaml
coordination:
  state_version: <int>
  lock_owner: <session_id|null>
  lock_acquired_at: <ISO8601|null>
  last_committed_at: <ISO8601>
  current_cron_job_id: <job_id|null>
  next_cron_job_id: <job_id|null>
  pending_transition: idle|spawned|awaiting-review|advancing|pausing|completing
```
Write rule: only the session holding `lock_owner` may mutate `STATE.md`, and every successful write increments `state_version`. Stale writers must abort, re-read, and recompute.
-->

`report_to`:
- DM: `{channel, target}`
- Group topic: `{channel, target, threadId}`

<!-- REVIEW [F-04]: `report_to` is stored, but the schema does not preserve how the interactive/group session hands off to later isolated cron wakes. CHANGE: Persist origin/handoff context explicitly. PROPOSED REPLACEMENT TEXT:
Add to the canonical schema:
```yaml
origin:
  session_kind: interactive-dm|interactive-group|isolated-cron
  session_id: <session_id>
  report_context_locked: true
```
This prevents isolated cron wakes from guessing routing from ambient context.
-->

<!-- REVIEW [S-02]: The document defines fields, but it never defines the allowed lifecycle transitions that govern them. CHANGE: Insert a formal state-machine section immediately after this section. PROPOSED INSERTION TEXT:
## 5. State Machine
Allowed states: `running`, `awaiting-review`, `paused`, `complete`.

Allowed transitions:
- `running -> awaiting-review`: coordinator spawned one or more subagents and durably committed the successor cron wake.
- `awaiting-review -> running`: coordinator ingested subagent result(s), selected the next executable action, and committed updated loop progress.
- `running -> paused`: ambiguity, deadline, retry policy, watchdog, or dead-loop policy triggered.
- `awaiting-review -> paused`: stalled/failed subagent exceeded retry or liveness policy.
- `running -> complete`: global completion criteria are satisfied and terminal cleanup is committed.

Forbidden transitions:
- `complete -> *`
- `paused -> running` without an explicit resume event
- `awaiting-review -> awaiting-review` after successful result ingestion

Coordinator rule: every transition must update `current`, loop/branch status, counters, and `pending_transition` before any user-visible report is emitted.
-->

---

## 4) Init Procedure

<!-- REVIEW [S-05]: MOVE this section to §6 in the restructured version (`Initialization`). -->

1. Create state dir + `STATE.md`.
2. Write validated steps/criteria and loop topology.
3. Add heartbeat entry `[auto-iterate:<id>]`.
4. Send start message via `message(action="send")` using `report_to`.

<!-- REVIEW [F-04]: The initial handoff from the interactive/group session to later isolated cron sessions is undefined. CHANGE: Persist origin metadata and lock `report_to` before the first wake exists. PROPOSED REPLACEMENT TEXT:
4. Persist `origin.session_kind`, `origin.session_id`, and locked `report_to` routing from the interactive setup turn.
5. Schedule the first coordinator wake with `sessionTarget: "isolated"`; every later wake must resume from persisted state rather than ambient session context.
-->

5. Schedule first cron wake.

<!-- REVIEW [F-06]: Initialization order is non-atomic: it can send a start message before the wake chain is durable. CHANGE: Replace the section with a transaction-safe setup sequence. PROPOSED REPLACEMENT TEXT:
1. Validate inputs and derive `report_to`.
2. Create the state directory.
3. Acquire the coordination lock and write initial canonical state (`status: running`, topology, deadlines, routing, counters).
4. Create the heartbeat entry.
5. Schedule the first isolated cron wake and persist the returned cron job id.
6. Only after state + heartbeat + cron are durable, send the start message.
-->

---

## 5) Cron Wake Coordinator (One Wake = One Coordination Cycle, with Recovery)

<!-- REVIEW [S-05]: MOVE this section to §7 in the restructured version (`Coordinator Cycle`). -->

Per wake, do exactly:

1. Read `STATE.md` first.
2. If `status=complete` (including stale wake) → `NO_REPLY`.
3. Run recovery branch in §7.
4. Check and update state.
5. Send progress report.
6. Decide one of: spawn subagent(s) / advance round or loop / pause / complete. **Mandatory post-spawn cron**: If you spawned a subagent, you MUST schedule a cron wake before ending the turn.

<!-- REVIEW [F-01]: Result ingestion does not currently force a next-step transition. The coordinator can absorb a result and still remain in limbo. CHANGE: Make next-transition selection mandatory. PROPOSED REPLACEMENT TEXT:
6. After ingesting any completed subagent result, you MUST choose and commit exactly one next transition before reporting or ending the turn: `spawn`, `advance`, `pause`, or `complete`. Remaining in `awaiting-review` after successful ingestion is invalid.
-->

7. **Cleanup before advance**: when advancing to a new task/loop, remove the current cron job (`cron(action="remove", jobId=<cron_job_id>)`), reset `deadline_at` to `now + 3h`, update `cron_job_id` in STATE.md.

<!-- REVIEW [F-02]: Cron replacement order is backwards. Removing the current wake before the replacement is durable can break the chain entirely. CHANGE: Reverse the handoff order. PROPOSED REPLACEMENT TEXT:
7. Two-phase cron handoff: (a) add the successor cron wake, (b) persist its id as `next_cron_job_id`, (c) atomically promote it to `current_cron_job_id`, and only then (d) remove the superseded cron job. Never remove the live wake chain before the replacement is durable.
-->

<!-- REVIEW [M-02]: The skill needs an explicit mechanism, not just reordered prose, to survive partial cleanup failures. CHANGE: Track active and successor cron identities separately. PROPOSED REPLACEMENT TEXT:
Add to the coordinator contract:
- Maintain both `current_cron_job_id` and `next_cron_job_id` during handoff.
- If removal of the old cron fails after the new cron is durable, mark cleanup pending and retry later.
- Do not collapse both roles into one nullable field during handoff.
-->

8. Schedule next cron wake if still running/awaiting-review.
9. End turn.

<!-- REVIEW [F-05]: Reporting is currently ordered before commitment, which allows externally visible progress that was never durably recorded. CHANGE: Reorder the cycle so state and wake handoff are committed before progress reporting. PROPOSED REPLACEMENT TEXT:
Per wake, do exactly:
1. Read state and acquire/revalidate the coordination lock.
2. If terminal, perform idempotent cleanup checks and exit.
3. Run recovery/watchdog checks.
4. Ingest any completed subagent result(s) and compute the next required transition immediately.
5. Commit updated state (`current`, loop/branch status, counters, pending transition).
6. Schedule or refresh the successor cron wake if the loop remains non-terminal.
7. Remove superseded cron jobs only after the successor wake is durable.
8. Send the progress report from committed state.
9. End turn.
-->

Do not run heavy edits (e.g., 5+ file edits) in coordinator; delegate to subagent.

<!-- REVIEW [M-03]: The coordinator delegates heavy work, but the skill never defines the subagent contract or liveness expectations. CHANGE: Insert a dedicated subagent section after the coordinator section. PROPOSED INSERTION TEXT:
## 8. Subagent Contract
When delegating heavy work, pass a structured brief containing: iteration id, loop id, branch id (if any), absolute workdir, absolute state path (read-only for subagents), target criteria, and the expected output schema.

Subagents must not mutate orchestration state directly. They return a structured result envelope such as:
```yaml
status: success|no-change|blocked|failed
summary: <short human-readable summary>
artifacts: [<paths or identifiers>]
criteria_assessment: met|not-met|unclear
next_action_hint: spawn|advance|pause|complete
```

Liveness SLA:
- Persist `started_at` for each active subagent.
- If no completion is observed by `started_at + expected_wait_window`, mark the subagent `stalled`.
- Retries are coordinator-driven; subagents do not self-reschedule the loop.
-->

---

## 6) Cron Contract + Delay Decay (REQUIRED)

<!-- REVIEW [S-05]: MOVE this section to §9 in the restructured version (`Cron Contract & Delay Decay`). -->

Cron self-wake must use `cron(action="add")` only (never `exec("openclaw cron ...")`) with:
- `schedule.kind: "at"` (UTC timestamp)
- `payload.kind: "agentTurn"`
- `payload.timeoutSeconds: 300`
- `delivery: {mode: "none"}`
- `sessionTarget: "isolated"`
- `agentId: "<own_agentId>"` (read from runtime info)

<!-- REVIEW [C-01]: The tool/API contract is underspecified. The skill lists desired fields but does not define what must be persisted from return values or what constitutes success. CHANGE: Add a canonical contract immediately here. PROPOSED INSERTION TEXT:
Canonical tool contract:
- `cron(action="add")` must return a durable `{jobId, runAt}` pair; persist both before ending the turn.
- `cron(action="remove")` is idempotent best-effort cleanup; failure after successor scheduling must not invalidate the loop.
- `sessions_spawn` must return a stable session id that is persisted before moving to `awaiting-review`.
- `message(action="send")` is notification only; it does not count as state commitment.
-->

Coordinator wake is strictly: **check → report (`message(action="send")`) → spawn/advance → schedule → END**.

### Delay base by complexity

- trivial: **120s**
- simple: **240s**
- moderate: **360s**
- complex: **480s**

### Delay decay within a round

When polling the same subagent within one round, interval shortens on consecutive wakes:
- 1st poll: 100% of base
- 2nd poll: 75% of base
- 3rd+ poll: 50% of base
- floor: min 60s
- `delay = max(60, round(base * factor))`

Reset to 100% when advancing to the next round.

### Wake message template

Each wake = fresh isolated session with no history. Message must include:
- iteration id + round number
- state path (absolute)
- subagent session key
- workdir
- target criteria
- report_to

<!-- REVIEW [C-05]: The wake template still lacks enough context for deterministic isolated recovery. CHANGE: Replace the informal list with a canonical self-contained template. PROPOSED REPLACEMENT TEXT:
### Wake message template
Each wake = fresh isolated session with no history. Message must include exactly:
```text
Iteration: <id>
Round: <round>
Status: <status>
State path: <absolute path>
Workdir: <absolute workdir>
Current loop: <loop_id|null>
Current branch: <branch_id|null>
Subagent session: <session_id|null>
Current cron job: <current_cron_job_id|null>
Workflow deadline: <workflow_deadline_at>
Next action on wake: <poll|ingest|advance|cleanup>
Report_to: <serialized report_to>
Heartbeat tag: [auto-iterate:<id>]
⚠️ RULES(copy this line verbatim into every child cron): ONE ROUND→END. cron(action="add")→YES, exec("openclaw cron")→NO. message(action="send")→YES. delivery={mode:"none"}. Heavy work→spawn subagent.
```
-->

And this line **verbatim** (self-propagating constraint):

`⚠️ RULES(copy this line verbatim into every child cron): ONE ROUND→END. cron(action="add")→YES, exec("openclaw cron")→NO. message(action="send")→YES. delivery={mode:"none"}. Heavy work→spawn subagent.`

---

## 7) Crash / Restart Recovery (State Recovery)

<!-- REVIEW [S-05]: MOVE this section to §10 in the restructured version (`Recovery and Watchdog`). -->

At wake start, always recover from persisted state:

1. Read `STATE.md`.
2. If `status=awaiting-review`:
   - Check `subagent_session` via `sessions_history`.
   - If subagent completed: ingest result, clear awaiting flag. If round produced 0 fixes → increment `no_fix_rounds`; otherwise reset `no_fix_rounds` to 0. Continue coordinator flow.

<!-- REVIEW [F-01]: Successful result ingestion must force a transition choice, not merely "continue coordinator flow." CHANGE: Tighten the completion bullet. PROPOSED REPLACEMENT TEXT:
- If subagent completed: ingest the result, recompute exit conditions, update `no_fix_rounds`, and commit exactly one next transition (`running`, `paused`, or `complete`) before any report is sent.
-->

   - If still running/pending: schedule next wake at delay-decay scheduling, end turn.
   - If missing/failed/crashed: increment `retry_count`. If `retry_count >= 4` → pause and report. Otherwise respawn equivalent subagent.
3. If stale wake and already complete: `NO_REPLY`.

This recovery path is mandatory for crashed/missed sessions.

<!-- REVIEW [F-03]: Recovery currently assumes the wake chain is already alive, but the broken-chain case is exactly when recovery is needed. CHANGE: Reframe recovery so wake-chain verification/repair happens first. PROPOSED REPLACEMENT TEXT:
At wake start, always recover from persisted state:
1. Read `STATE.md`.
2. If there is no durable active wake (`current_cron_job_id` missing) or the expected wake window has been missed, create a recovery wake immediately and persist it before deeper inspection.
3. If `status=awaiting-review`, inspect the persisted active subagent sessions.
4. If a subagent completed, ingest results, choose the next transition, and commit state.
5. If a subagent is still running, schedule the next poll wake using delay decay and end turn.
6. If a subagent is missing/failed/stalled, apply retry policy or pause.
-->

<!-- REVIEW [M-01]: There is no coordinator watchdog to detect silent coordinator failure or wake-chain drift. CHANGE: Add a watchdog subsection inside Recovery. PROPOSED INSERTION TEXT:
### Watchdog
Maintain `watchdog_due_at = last_coordinator_at + max(2 * current_delay, 10m)`.
If any wake observes `now > watchdog_due_at`, treat the loop as unhealthy:
- recreate the successor wake if needed
- increment `watchdog_tripped_count`
- record the incident in state
- pause only if automatic repair fails or repeats beyond policy
This makes coordinator liveness an explicit mechanism instead of an assumption.
-->

---

## 8) Completion / Pause Rules

<!-- REVIEW [S-05]: MOVE this section to §11 in the restructured version (`Completion / Pause / Cleanup`). -->

Set `status=complete` only when user criteria are met.

**On complete or pause**: remove all related cron jobs (`cron(action="remove", jobId=<cron_job_id>)`), remove heartbeat entry, then send final report.

<!-- REVIEW [M-06]: Terminal cleanup is underspecified for multi-cron handoff and parallel branches. A single `cron_job_id` field is not enough. CHANGE: Make terminal cleanup idempotent and comprehensive. PROPOSED REPLACEMENT TEXT:
**On complete or pause**: remove every job referenced by `current_cron_job_id`, `next_cron_job_id`, and any branch-local wake ids, clear the heartbeat entry, mark cleanup status in state, then send the final report. Terminal cleanup must be idempotent.
-->

<!-- REVIEW [C-03]: Heartbeat lifecycle is still only hinted at. CHANGE: Tie heartbeat behavior to state transitions and recovery. PROPOSED REPLACEMENT TEXT:
Add to terminal-state handling:
- Update heartbeat on every successful coordinator commit.
- Mark heartbeat `status=stalled` whenever watchdog repair is in progress.
- Remove heartbeat only after terminal cleanup is durably committed.
-->

Pause (`status=paused`) and report when:
- dead loop (`no_fix_rounds>=3` and no meaningful fixes)
- per task runtime exceeded 3h
- ambiguity blocks requiring user decision
- retry_count >= 4

Only the session that sets `status=complete` sends final completion report.

<!-- REVIEW [C-01]: The skill would be easier to maintain if it ended with canonical request/result/report templates instead of forcing future editors to infer them from prose. CHANGE: Add a final templates section. PROPOSED INSERTION TEXT:
## 12. Canonical Templates
### Canonical cron add request
```json
{
  "action": "add",
  "schedule": {"kind": "at", "at": "<UTC timestamp>"},
  "payload": {
    "kind": "agentTurn",
    "timeoutSeconds": 300,
    "prompt": "<self-contained wake message>"
  },
  "delivery": {"mode": "none"},
  "sessionTarget": "isolated",
  "agentId": "<own_agentId>"
}
```

### Canonical subagent result envelope
```yaml
status: success|no-change|blocked|failed
summary: <text>
artifacts: []
criteria_assessment: met|not-met|unclear
next_action_hint: spawn|advance|pause|complete
```

### Canonical progress report
```text
[auto-iterate:<id>] round <n>
status: <running|awaiting-review|paused|complete>
current: <current action>
completed: <what changed this round>
next: <next transition>
```
-->

## Review Summary

| Finding | Section | Action | Priority |
|---|---|---|---|
| S-01 | Opening / new §2 | Insert explicit roles and ownership model | High |
| S-02 | After §3 State Model | Add formal state machine with allowed/forbidden transitions | High |
| S-03 | Non-Negotiables + §3 | Replace loose markdown state with canonical single YAML document | High |
| S-04 | §2 Loop Topology + §4 State Model | Add first-class branch representation and merge semantics | High |
| S-05 | Whole document structure | Reorder scattered sections into the proposed 12-part structure | High |
| F-01 | §5 Coordinator + §7 Recovery | Force deterministic next-step transition after result ingestion | High |
| F-02 | §5 Coordinator | Reverse cron replacement order to preserve the wake chain | High |
| F-03 | §7 Recovery | Repair/verify wake chain explicitly during recovery | High |
| F-04 | §3 State Model + §4 Init | Define interactive/group-to-isolated-cron handoff and locked routing | High |
| F-05 | §5 Coordinator | Commit state before user-visible reporting | High |
| F-06 | Non-Negotiables + §4 Init | Make spawn/state/cron an atomic coordination transaction | High |
| C-01 | §6 Cron Contract + §12 Templates | Specify request/response and payload contracts for core tools | Medium |
| C-02 | Non-Negotiables + §3 State Model | Split workflow deadline from rolling coordination leases | High |
| C-03 | Non-Negotiables + §11 Cleanup | Operationalize heartbeat lifecycle and stalled-state handling | Medium |
| C-04 | Non-Negotiables + §9 Cron Contract | Consolidate repeated forbidden-pattern warnings into one canonical rule | Low |
| C-05 | Non-Negotiables + §9 Wake Template | Expand wake template with lineage, deadlines, and next action | Medium |
| M-01 | §10 Recovery | Add explicit coordinator watchdog | High |
| M-02 | §7 Coordinator / §9 Cron Contract | Add two-phase cron handoff with current/next job ids | High |
| M-03 | New §8 Subagent Contract | Define subagent liveness SLA and result envelope | Medium |
| M-04 | §4 State Model | Add single-writer lock discipline and state versioning | High |
| M-05 | §2 Loop Topology / parallel branches | Add per-branch retry and no-fix accounting | Medium |
| M-06 | §11 Completion / Pause | Define idempotent terminal cleanup for multi-cron state | High |
