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
- The required tools for the chosen orchestration mode are available under current tool policy.

Required modes:
- **Spawned-worker mode** (default, reliable): requires `cron`, `message`, `sessions_spawn`, `sessions_history`.
- **Existing-agent mode** (optional): additionally requires `sessions_send`, visibility to the target session via `sessions_history`, and a dedicated automation-safe target session.

Fallback rules:
- If existing-agent mode is unavailable, fall back to spawned-worker mode.
- If spawned-worker mode is unavailable, do not start automatic iteration; pause or ask for a different execution plan.

If any required item is missing, stop and ask. Do not create state, spawn subagents, or schedule cron.

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
- Use persisted `origin.report_to` for all user-visible messages. The coordinator sends progress / pause / resume / completion messages directly to `origin.report_to` via `message(action="send")`. Never infer routing from ambient session context, and never require relay through the origin session.
- Use first-class tools for scheduling and messaging: `cron(action="add"|"remove")`, `sessions_spawn`, `sessions_history`, `message(action="send")`.
- Use the coordination fields from the canonical schema: `state_version`, `writer_session`, `lease_expires_at`, `current_wake_job_id`, `next_wake_job_id`, `watchdog_job_id`, `cleanup_pending`, `last_cycle_at`, `next_expected_wake_at`, `pending_transition`, `alert_needed`, and `alert_sent`.
- Lease TTL is 120 seconds. On every successful PERSIST, set `coordination.lease_expires_at = now + 120s`. To claim the write lease: `coordination.writer_session == current_session` or `now > coordination.lease_expires_at`. A watchdog may only claim the lease when `next_expected_wake_at` is also overdue. If another session holds a fresh lease, exit without writing.
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
3. Select orchestration mode:
   - prefer spawned-worker mode
   - use existing-agent mode only if session visibility and tool policy are confirmed for the target session
4. Write initial `STATE.md` with:
   - `status: running`
   - zeroed counters
   - locked `origin.report_to`
   - fixed deadline
   - `execution_mode: spawned-worker | existing-agent`
   - empty `subagents[]`
5. Add the first isolated coordinator wake and persist its job id.
6. Add one independent watchdog cron with `deleteAfterRun: false` and persist its job id.
7. Only after state + coordinator wake + watchdog are durable, send the kickoff message.

## 7. Run the coordinator cycle exactly once per wake

### READ
1. Read `STATE.md`.
2. Exit quietly if `status: complete`.
3. Claim the write lease: if `coordination.writer_session == current_session` or `now > coordination.lease_expires_at`, write `writer_session = current_session` and `lease_expires_at = now + 120s`. Otherwise exit without writing.
4. Re-read if the wake payload and the persisted state disagree; state wins.

### RECOVER
5. Repair liveness first:
   - If `coordination.current_wake_job_id` is missing, or `now > coordination.next_expected_wake_at`, create a replacement wake immediately and persist it.
   - If cleanup of an old wake failed earlier, keep its id in `coordination.cleanup_pending[]` and retry later.
6. Inspect each active subagent via `sessions_history`:
   - `success`, `no-change`, `blocked`, or timeout with usable output: ingest it.
   - still running: keep polling.
   - failed, missing, or stalled: mark failure and apply retry policy.
7. If `coordination.alert_needed: true`, emit the `⚠️` watchdog-repair alert template from committed state at the next safe REPORT step, then clear `alert_needed`. If the watchdog used the narrow direct-alert exception, leave `alert_sent: true` and do not duplicate the alert.
8. If a result was ingested, recompute loop exit conditions and choose the next transition now. Do not defer that decision.

### DECIDE
9. Choose exactly one next action:
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
10. Write the full updated state:
   - `status`
   - current loop, branch, and function
   - counters
   - subagent records
   - `pending_transition`
   - `last_cycle_at`
   - `next_expected_wake_at`
   - pause or resume fields

### SCHEDULE
11. If the workflow remains non-terminal, schedule the successor coordinator wake:
   - `schedule.kind: "at"`
   - `payload.kind: "agentTurn"`
   - `payload.timeoutSeconds: 300`
   - `delivery: {mode: "none"}`
   - `sessionTarget: "isolated"`
   - self-contained wake message
12. Persist the new wake id as `coordination.next_wake_job_id`, promote it to `current_wake_job_id`, then remove the superseded wake id. If removal fails, retain it in `cleanup_pending[]`.
13. If a subagent was spawned, ensure the successor wake is already durable before ending the turn.

### REPORT
14. Send one user-visible status message from committed state directly to `origin.report_to` via `message(action="send")`. Use the matching template from `references/examples.md` §5: 🔄 progress while running, ⏸️ pause on suspension, ▶️ resume on recovery, ⚠️ watchdog-repair alert on chain failure, ✅ final completion on terminal state. Every message must contain only user-meaningful content: header with round + loop + local time, actor/status lines with emoji, bullet details (commits, test results, repair actions), next step, next check time (`⏰`) when applicable, and remaining time to deadline (`📊`) when applicable. Never include routing metadata.

### END
15. Release the lease and end the turn. Never do a second cycle inside the same wake.

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

Existing-agent mode is optional, not the default. Treat it as best-effort orchestration, not the preferred worker path.

Use existing-agent mode only when all are true:
- the target session key is already known
- current tool policy and `tools.sessions.visibility` allow `sessions_history` on that session
- the target session is dedicated and automation-safe (not mixed with unrelated human chat)
- the target agent can be instructed not to send direct user-facing progress
- the target agent can be instructed to minimize reply-back ping-pong and suppress any direct announce behavior that would bypass the coordinator

If any condition is false, use `sessions_spawn` instead.

When existing-agent mode is allowed, send the task via `sessions_send`. Track that session in `subagents[]` with `run_id: null` and `child_session_key` set to its known session key. Poll output via `sessions_history` using the same delay and retry policy as spawned subagents.

Dispatch message must be self-contained: include iteration id, round, workdir, exact task, expected output format, and state path (read-only reference — the external agent must not edit `STATE.md` or schedule cron). It must also instruct the target agent to keep output coordinator-ingestible and to avoid unnecessary ping-pong replies.

If the target session produces noisy ping-pong, uncontrolled announce behavior, or output that cannot be cleanly ingested, abort existing-agent mode, persist the failure reason, and fall back to `sessions_spawn`.

The coordinator ingests and rewrites all external-agent output before sending to `origin.report_to`. External agents never report to the user directly.

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
- set `coordination.alert_needed: true` in state when repair is triggered

The watchdog never sends user-visible messages directly. Single exception: if `watchdog_tripped_count >= 3` and the coordinator has still not recovered, the watchdog may send one alert using the `⚠️` watchdog-repair template from `references/examples.md` §5, then set `coordination.alert_sent: true` to prevent duplicates.

The watchdog remains active until both `cleanup.wake_cleanup_complete: true` and `cleanup.terminal_report_sent: true`. After both flags are set, the watchdog removes itself.

A healthy workflow keeps both of these current:
- `coordination.last_cycle_at`
- `coordination.next_expected_wake_at`

## 10. Handle Claude quota suspension

Before any expensive spawn or respawn that will use a Claude-family model, verify quota directly from runtime-available provider metadata.

If quota is suspended:
1. Set `status: paused`, `resume.mode: quota-auto`, `resume.blocked_by: claude-quota`.
2. Persist `resume.resume_at` from provider reset metadata when available.
3. If reset metadata is unavailable, set a conservative fallback: `resume.resume_at = now + 1h` and do not allow further expensive Claude-family spawns before that time.
4. Persist all loop and branch context needed to continue after resume: active loop id, current function, pending subagent session keys, and any partial results. State must be complete enough for any coordinator wake to resume without external skill state.
5. Schedule a resume coordinator wake at or after `resume.resume_at`.
6. Report the pause using the `⏸️` Pause template from `references/examples.md` §5.
7. End the turn.

On the resume wake:
1. Check `resume.blocked_by: claude-quota` in state.
2. Re-verify quota directly.
3. If clear: clear `resume.*` fields, transition `paused -> running`, report using the `▶️` Resume template from `references/examples.md` §5, and continue the coordinator cycle from `active_loop_ids` and current functions.
4. If still suspended: update `resume.resume_at`, reschedule, and report using the `⏸️` Pause template from `references/examples.md` §5 only if the expected resume time materially changed.

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

Use this routing behavior:
- the coordinator is the only authoritative sender
- the coordinator sends directly to `origin.report_to`
- the origin session is the task entrypoint, not a relay hop
- subagents, other external agents, and watchdog do not send user-visible messages to the user directly (see §9 for the narrow watchdog exception)

Do not let subagents guess the user destination. If subagent output must reach the user, the coordinator rewrites and relays it.

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
1. Move `current_wake_job_id` and `next_wake_job_id` into `cleanup_pending[]`. Persist.
2. Remove each id in `cleanup_pending[]`, excluding `watchdog_job_id`. Persist after each removal. Retain any failed ids in `cleanup_pending[]` for retry on the next watchdog run.
3. Set `cleanup.wake_cleanup_complete: true` and persist.
4. Send the final report using the `✅` Final completion template from `references/examples.md` §5.
5. Set `cleanup.terminal_report_sent: true` and persist.
6. After both flags are true, remove `watchdog_job_id`. If removal fails, the watchdog detects `terminal_report_sent: true` on its next run and removes itself without alerting.

Read references when needed:
- `references/state-schema.md` — canonical YAML schema
- `references/examples.md` — cron, spawn, wake, and routing templates
- `references/recovery.md` — failure handling, watchdog repair, and quota-resume rules
