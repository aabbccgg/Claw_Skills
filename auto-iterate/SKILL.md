---
name: auto-iterate
description: Execute user-directed iterative workflows until explicit completion criteria are met. Use for 自动迭代, 循环迭代, 迭代, 循环执行, 重复直到, “iterate until”, or “loop until”, including single loops, nested loops, sequential multi-loop plans, and parallel branch orchestration with cron-based polling, watchdog recovery, and quota-aware resume.
---

# Auto-Iterate

Use this skill as a strict orchestration protocol for iteration. Treat the user's loop definition and exit criteria as authoritative.

## 1. Start only after admission succeeds

Require all of these before creating state:
- The user explicitly asked for looping / repeat-until behavior.
- There is at least one executable step, function, or branch definition.
- There is at least one explicit, testable completion criterion.
- The reporting destination can be persisted as `origin.report_to`.

If any item is missing, stop and ask. Do not create state, spawn subagents, or schedule cron.

## 2. Fix the roles

Use exactly these actors:
- **Interactive origin session** — validate inputs, persist routing, write initial state, install the first coordinator wake and watchdog, send kickoff. It is not the long-running coordinator.
- **Coordinator** — an isolated cron wake only. It is the only writer to `STATE.md`. It alone may transition state, spawn or monitor subagents, schedule or remove wakes, and send authoritative user-visible reports.
- **Subagent** — heavy execution only. It must not mutate orchestration state.
- **Watchdog** — an isolated recurring cron wake that repairs liveness only. It does not do heavy work or user-task execution.

Never let a group session, DM session, or subagent become the coordinator after initialization.

## 3. Obey the hard rules

- Keep all orchestration state in `STATE.md` as exactly one fenced YAML document. No prose state.
- Read state from disk on every coordinator or watchdog wake. Never trust chat history.
- Use persisted `origin.report_to` for all user-visible messages. Never infer routing from ambient session context.
- Use first-class tools for scheduling and messaging: `cron(action="add"|"remove")`, `sessions_spawn`, `sessions_history`, `message(action="send")`.
- Use the coordination fields from the canonical schema: `state_version`, `writer_session`, `lease_expires_at`, `current_wake_job_id`, `next_wake_job_id`, `watchdog_job_id`, `cleanup_pending`, `last_cycle_at`, `next_expected_wake_at`, and `pending_transition`.
- If a fresh foreign lease exists, treat the wake as stale: re-read state and exit.
- Run one coordination cycle per wake, in this exact order: `READ -> RECOVER -> DECIDE -> PERSIST -> SCHEDULE -> REPORT -> END`.
- Commit state before reporting. `message(action="send")` never counts as persistence.
- When spawning subagents, persist the subagent record first, schedule the successor wake in the same turn, persist the returned wake id, then report.
- Replace coordinator wakes with add-before-remove. Persist the new wake id before removing the superseded one.
- Keep `workflow_deadline_at = started_at + 3h` fixed. Use separate poll or resume timestamps for shorter waits.
- Delegate heavy execution to subagents. Keep coordinator and watchdog turns small and deterministic.
- Make every wake message self-contained: include iteration id, round, absolute state path, workdir, active loop or branch, active subagent ids, current wake id, workflow deadline, `report_to`, and next intended action.

## 4. Create the state bundle

Use a dedicated directory:

`~/.openclaw/<agent_workspace>/iterations/<YYYYMMDD-HHMMSS-slug>/`

Create:
- `STATE.md` — canonical YAML state
- optional artifacts or summaries produced by the loop

Read `references/state-schema.md` before the first write and whenever the schema is in doubt.

Track, at minimum:
- identity, workdir, task summary, and explicit target
- `status`: `running | awaiting-review | paused | complete`
- locked `origin.report_to`
- fixed workflow deadline
- coordination fields: version, lease, wake ids, watchdog id, cleanup queue, next expected wake, pending transition
- loop topology: loops, branches, merge policy, current function
- `subagents[]` records, one entry per active or completed worker
- progress counters: retries, no-fix rounds, last result summary
- pause and resume fields for quota suspension or user-blocked states

## 5. Use the explicit state machine

Allowed transitions:

| From | Event | To |
|---|---|---|
| `running` | coordinator spawns work and durably commits successor wake | `awaiting-review` |
| `awaiting-review` | coordinator ingests result and chooses the next action | `running` / `paused` / `complete` |
| `running` | user ambiguity, retry exhaustion, dead loop, deadline, or quota suspension | `paused` |
| `paused` | explicit resume event: user resume or quota-restored wake | `running` |
| `running` | global completion criteria met and terminal cleanup committed | `complete` |

Forbidden transitions:
- `complete -> *`
- `paused -> running` without an explicit resume event
- `awaiting-review -> awaiting-review` after successful result ingestion

After ingesting any successful subagent result, choose exactly one next transition before ending the wake. Never stay in limbo.

## 6. Initialize in one safe transaction

1. Normalize the loop topology:
   - single loop
   - nested loop
   - multiple loops in `sequential` or `parallel` mode
   - parallel branches with stable `branch_id` values and declared `merge_policy`
2. Create the state directory.
3. Write initial `STATE.md` with:
   - `status: running`
   - zeroed counters
   - locked `origin.report_to`
   - fixed deadline
   - empty `subagents[]`
4. Add the first isolated coordinator wake and persist its job id.
5. Add one independent watchdog cron with `deleteAfterRun: false` and persist its job id.
6. Only after state + coordinator wake + watchdog are durable, send the kickoff message.

## 7. Run the coordinator cycle exactly once per wake

### READ
1. Read `STATE.md`.
2. Exit quietly if `status: complete`.
3. Claim the write lease. If another session already holds a fresh lease, exit.
4. Re-read if the wake payload and the persisted state disagree; state wins.

### RECOVER
5. Repair liveness first:
   - If `coordination.current_wake_job_id` is missing, or `now > coordination.next_expected_wake_at`, create a replacement wake immediately and persist it.
   - If cleanup of an old wake failed earlier, keep its id in `coordination.cleanup_pending[]` and retry later.
6. Inspect each active subagent via `sessions_history`:
   - `success`, `no-change`, `blocked`, or timeout with usable output: ingest it.
   - still running: keep polling.
   - failed, missing, or stalled: mark failure and apply retry policy.
7. If a result was ingested, recompute loop exit conditions and choose the next transition now. Do not defer that decision.

### DECIDE
8. Choose exactly one next action:
   - `spawn`
   - `advance` within the current loop
   - `advance` to the next loop or parent loop
   - `pause`
   - `complete`

Decision rules:
- Single loop: run ordered functions, then evaluate exit condition.
- Nested loop: child loop must reach its exit condition before parent advances.
- Sequential multi-loop: advance loop `n+1` only after loop `n` is complete.
- Parallel branches: at most one active subagent per branch; merge only when the loop's `merge_policy` is satisfied.
- Parallel top-level loops: advance every actionable loop on the same wake, but keep per-loop state separate.

### PERSIST
9. Write the full updated state:
   - `status`
   - current loop, branch, and function
   - counters
   - subagent records
   - `pending_transition`
   - `last_cycle_at`
   - `next_expected_wake_at`
   - pause or resume fields

### SCHEDULE
10. If the workflow remains non-terminal, schedule the successor coordinator wake:
   - `schedule.kind: "at"`
   - `payload.kind: "agentTurn"`
   - `payload.timeoutSeconds: 300`
   - `delivery: {mode: "none"}`
   - `sessionTarget: "isolated"`
   - self-contained wake message
11. Persist the new wake id as `coordination.next_wake_job_id`, promote it to `current_wake_job_id`, then remove the superseded wake id. If removal fails, retain it in `cleanup_pending[]`.
12. If a subagent was spawned, ensure the successor wake is already durable before ending the turn.

### REPORT
13. Send one progress message from committed state to `origin.report_to`. Use the report templates from `references/examples.md` §5. Every report must include: header with round + loop + local time, actor status lines with emoji (✅🔄❌⏸️), bullet details (commits, test results), next step, next check time (`⏰`), and remaining time to deadline (`📊`).

### END
14. Release the lease and end the turn. Never do a second cycle inside the same wake.

## 8. Poll subagents and branches correctly

Use `subagents[]`, not a singular session field.

For each subagent record, persist:
- `child_session_key`
- `run_id`
- `loop_id`
- `branch_id` or `null`
- `status`
- `started_at`
- `timeout_at`
- `last_checked_at`
- `summary`
- `criteria_assessment`
- `next_action_hint`

Apply retries per loop or per branch, not globally across unrelated branches.

Recommended polling delay by complexity:
- trivial: 120s
- simple: 240s
- moderate: 360s
- complex: 480s

Within the same branch or serial step, decay polling to `100% -> 75% -> 50%`, with a 60s floor. Reset the streak when advancing to a new round or new branch.

Treat subagent auto-announcements as best-effort diagnostics only. The coordinator still polls and still sends authoritative user messages.

## 9. Install and use the watchdog

Install one recurring watchdog cron when the workflow starts. Keep it separate from the coordinator wake chain.

Watchdog job:
- runs in an isolated session
- uses `delivery: {mode: "none"}`
- is non-deleting / recurring
- reads only persisted state

Watchdog duties:
- detect missed coordinator wakes
- detect stale `awaiting-review` states with no recent polling
- recreate missing coordinator wakes
- retain old wake ids in `cleanup_pending[]` until safely removed
- increment `coordination.watchdog_tripped_count`
- report only when repair failed or the workflow must pause

A healthy workflow keeps both of these current:
- `coordination.last_cycle_at`
- `coordination.next_expected_wake_at`

## 10. Integrate Claude quota suspension

Before any expensive spawn or respawn, run the `claude-auto-resume` skill.

If Claude quota is suspended:
1. Set `status: paused`.
2. Set `resume.mode: quota-auto`.
3. Set `resume.blocked_by: claude-quota`.
4. Persist `resume.resume_at` from the quota skill's safe resume time.
5. Schedule an outer-loop resume wake at or after `resume.resume_at`.
6. Report the pause to `origin.report_to`.
7. End the turn.

On the resume wake:
- re-check quota through the `claude-auto-resume` skill
- if clear, transition `paused -> running` and continue
- if still suspended, update `resume.resume_at`, reschedule, and report once

Keep the watchdog active during quota pauses.

## 11. Route all user-visible messages through persisted routing

Persist `origin.report_to` on init and never rewrite it.

Use one of:
- DM: `{channel: telegram, target: "<user id>"}`
- group topic: `{channel: telegram, target: "-100...", threadId: "<topic id>"}`

Send:
- kickoff
- progress
- pause / resume
- final completion

Do not let subagents guess the user destination. If subagent output must reach the user, the coordinator relays it.

## 12. Finish cleanly

Complete only when the user's explicit criteria are met.

Pause when any of these happens:
- ambiguity requires user input
- retries are exhausted for the active loop or branch
- the workflow deadline is reached
- repeated no-fix rounds show the loop is dead
- automatic repair failed
- quota suspension requires waiting

On `complete` or terminal `paused`:
1. Persist terminal state first.
2. Remove every known wake id: current, next, watchdog, and anything in `cleanup_pending[]`.
3. Mark cleanup completion in state.
4. Send the final report once.

Read references when needed:
- `references/state-schema.md` — canonical YAML schema
- `references/examples.md` — cron, spawn, wake, and routing templates
- `references/recovery.md` — failure handling, watchdog repair, and quota-resume rules
