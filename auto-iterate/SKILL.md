---
name: auto-iterate
description: Execute user-directed iterative workflows until explicit completion criteria are met. Use for 自动迭代, 循环迭代, 迭代, 循环执行, 重复直到, “iterate until”, or “loop until”, including single loops, nested loops, sequential multi-loop plans, and parallel branch orchestration with isolated cron coordination, watchdog recovery, quota-aware pause/resume, and direct reporting to the original DM or group topic.
metadata:
  {
    "openclaw":
      {
        "emoji": "🔄",
      },
  }
---

# Auto-Iterate

Use this skill as a low-freedom orchestration protocol. Treat the user's loop definition and exit criteria as authoritative.

Cron path: native cron first, exec+openclaw cron CLI fallback second.

## 1. Admit or stop

Start only when all are true:
- The user explicitly requested looping or repeat-until behavior.
- There is at least one executable step, function, or branch definition.
- There is at least one explicit completion criterion.
- The reporting destination can be persisted as `origin.report_to`.
- Required tools for the selected mode are available under effective tool policy.

Before starting any automatic iterative workflow, ask the user for clarification if the loop body, parallel loops, nested loops, or the task itself contains ambiguity, unclear logic, missing decisions, or conflicting instructions. Do not start the automated iteration until those ambiguities are resolved.

Mode:
- **Spawned-worker mode** — required. Requires `cron`, `message`, `sessions_spawn`, `sessions_history`. Use `sessions_spawn(..., runTimeoutSeconds=1800)` unless a shorter worker budget is explicitly justified.

Fallback:
- If spawned-worker mode is unavailable, do not start automatic iteration.

Always initialize every canonical schema field explicitly. Do not rely on implicit defaults.

## 2. Fix the roles

Use exactly these actors:
- **Origin session** — validate inputs, persist routing, initialize state, install coordinator wake and watchdog, send kickoff.
- **Coordinator** — an isolated cron wake only. Sole writer to `STATE.md`. Sole authority to transition state, monitor workers, schedule wakes, and send user-visible updates.
- **Worker** — spawned subagent only. Never edits orchestration state.
- **Watchdog** — isolated recurring cron wake that repairs liveness only.

Never let a human-facing chat session become the long-running coordinator after init.

## 3. Initialize in one safe transaction

Initialization order is binding:
1. Create the iteration directory.
2. Write initial `STATE.md` with every canonical schema field explicitly initialized.
3. Use `coordination.poll_complexity = moderate` unless the task clearly needs another polling tier.
4. Add the first isolated coordinator wake and persist its job id.
5. Add the watchdog wake and persist its job id.
6. Validate state and protocol.
7. Only after state + coordinator wake + watchdog are durable, send the kickoff message.

If any step fails before durability is reached, stop and repair state instead of sending kickoff.

## 4. Keep one source of truth

Store orchestration state in exactly one fenced YAML document at `STATE.md`. Read from disk on every coordinator or watchdog wake. Never trust chat history.

Core statuses are `running`, `awaiting-result`, `paused`, and `complete`.

Use `scripts/validate_state.py` whenever state may be inconsistent, after major edits, before terminal cleanup, and whenever a coordinator suspects drift between expected and persisted state.

## 5. Route messages one way

Persist `origin.report_to` on init and never rewrite it.

The coordinator sends progress, milestone, pause, resume, repair, and completion messages directly to `origin.report_to` via `message(action="send")`.

Do not let workers or watchdog send user-visible progress directly, except for the narrow watchdog emergency exception defined in `references/recovery.md`.

Use `scripts/render_progress.py` to generate user-visible messages from committed state. Keep the progress message minimal: header + optional milestone + optional worker status + in-progress summary + next action + next check. 

## 6. Run one coordination cycle per wake

Follow this order exactly:

`READ -> RECOVER -> DECIDE -> PERSIST -> SCHEDULE -> REPORT -> END`

Hard rules:
- Lease TTL is 120 seconds.
- Commit state before report.
- Add successor wake before removing superseded wake.
- Make every wake message self-contained.
- Use `payload.timeoutSeconds = 1800` for coordinator and watchdog isolated cron jobs unless a clearly simpler job justifies less.
- Long business work belongs in workers, not in the coordinator or watchdog.
- In isolated coordinator wakes, do not spend the cycle on long recap, broad re-planning, or user-facing explanation before dispatch/poll/persist/schedule.
- A non-terminal coordinator cycle is invalid if it ends without at least one concrete progress action: dispatching a worker, ingesting worker output, persisting a transition, or durably scheduling the successor wake.

Coordinator workflow:
1. Read `STATE.md`.
2. Run `scripts/validate_state.py <state_path>` to validate structure.
3. Run `scripts/validate_protocol.py <state_path>` to validate protocol invariants.
4. Choose the minimal mode for this wake:
   - `ingest-only` if a worker result already exists and only needs ingestion
   - `repair-only` if the wake chain is broken
   - `dispatch-only` if no worker exists for the current step
   - otherwise normal poll/advance
5. Keep the wake narrow. Do not broadly re-read docs, examples, fixtures, or CLI help unless validation itself fails.
6. In `ingest-only`, prioritize result ingestion before any redispatch or broader repair.
7. Run `scripts/evaluate_progress.py <state_path> --json` to determine actionable loops, branch readiness, and merge readiness.
8. Run `scripts/check_stall.py <state_path> --json` to determine whether dead-loop or no-fix-rounds policy requires pause.
9. Run `scripts/check_transition.py <state_path> --event <canonical-event> --to <status> --json` for every candidate non-terminal transition. Do not bypass this check.
10. Persist the full next state. When a loop completes or the workflow advances to a new loop, optionally append a milestone item to `progress.pending_reports`.
11. Compute deterministic next-poll delay with `scripts/compute_next_poll.py --state-path <state_path>`.
12. Schedule the successor wake if non-terminal.
13. Render the correct report text with `scripts/render_progress.py <state_path> --mode <progress|pause|resume|repair|final>`. If `progress.pending_reports` is non-empty, prefer the oldest queued milestone/progress item over a generic progress report.
14. Send one short user-visible report from committed state.
15. If a queued pending report was successfully delivered, persist queue cleanup before END. This is the only allowed post-report cleanup persist.
16. End.

If the wake reached END without real progress and without a durable successor wake, treat the cycle as failed and rely on watchdog repair rather than emitting a long explanatory recap.

Use `references/flow.md` as the binding source for the explicit state machine, canonical transition vocabulary, loop progression semantics, and dead-loop policy.

## 7. Use spawned workers only

Worker path:
- Spawn via `sessions_spawn`.
- Track in `subagents[]`.
- Poll via `sessions_history`.
- Treat auto-announces as best-effort diagnostics only.

If the user provides an agent identifier, agent name, or profile-like agent reference for a worker role, resolve that request as an agent-profile selection. Spawn an isolated worker that reuses the matched agent profile (`agentId`, default model, and static persona).

Agent-profile reuse rules:
- Inspect the runtime-available agent list (for example via `agents_list`) or the user's explicitly named agent identifiers and resolve the requested worker profile dynamically.
- Reuse only the static agent profile for the fresh spawned worker. Do not inherit live session history, pending tasks, or transient context.
- If the requested profile match is ambiguous, unclear, missing, or conflicts with the task structure, ask the user for clarification before starting the automated iteration. Do not silently guess.
- A user-provided agent identifier, agent name, or profile reference for a worker role overrides the default generic spawned-worker choice, but it still resolves to a fresh spawned worker with the matched profile.

Worker dispatch contract:
- Dispatch in one wake.
- Validate `running --worker-dispatched--> awaiting-result`.
- Immediately persist worker-dispatched state: `status=awaiting-result`, `subagents[].status=accepted`, `started_at`, and worker session metadata.
- Schedule the successor wake and END.
- In later wakes, ingest results only via `sessions_history` and validate `awaiting-result --worker-result--> running|paused|complete`.
- Lack of a same-wake final result is normal. Do not misclassify dispatch as failure after a worker was successfully spawned and recorded.

## 8. Keep the watchdog alive until reporting is done

Install one recurring isolated watchdog with `delivery: {mode: "none"}`.

Watchdog duties:
- Detect missing or overdue coordinator wakes.
- Recreate missing wakes.
- Retain obsolete wake ids in `cleanup_pending[]`.
- Set `coordination.alert_needed: true` when repair is triggered.
- Stay alive until both `cleanup.wake_cleanup_complete` and `cleanup.terminal_report_sent` are true.

Use `references/recovery.md` for watchdog rules, repair verification, and the narrow direct-alert exception.

## 9. Pause and resume on quota safely

Before expensive Claude-family worker spawns or respawns, verify quota from runtime-available provider metadata.

If quota is suspended:
- Set `status: paused`, `resume.mode: quota-auto`, `resume.blocked_by: claude-quota`.
- Persist `resume.resume_at` from provider reset metadata, or use a conservative fallback.
- Persist enough loop and branch context to resume without external skill state.
- Validate `running -> paused` with `scripts/check_transition.py`.
- Schedule a resume wake.
- Render and send the pause message.

On resume:
- Re-check quota.
- If clear, clear `resume.*`, validate `paused -> running`, render the resume message, and continue.
- If still blocked, update `resume.resume_at`, reschedule, and only re-report if the resume time materially changed.

## 10. Finish in an idempotent way

On terminal completion or terminal pause:
1. Run `scripts/validate_state.py <state_path>` and `scripts/validate_protocol.py <state_path>`.
2. Move current and next wake ids into `cleanup_pending[]`.
3. Remove non-watchdog wake ids, retrying failed removals later.
4. Mark `cleanup.wake_cleanup_complete: true`.
5. Render the final completion message with `scripts/render_progress.py <state_path> --mode final` and send it if not yet delivered.
6. If final delivery fails, keep the watchdog alive and require the watchdog or next recovered coordinator wake to retry final reporting before shutdown.
7. Mark `cleanup.terminal_report_sent: true` only after successful delivery.
8. Remove the watchdog after both cleanup flags are true.

## 11. Read only what you need

Read these references as needed:
- `references/state-schema.md` — canonical YAML schema and field semantics.
- `references/flow.md` — explicit state machine, loop progression, and dead-loop policy.
- `references/recovery.md` — wake repair, alert lifecycle, quota pause/resume, terminal cleanup.
- `references/examples.md` — cron payload examples, worker briefs, report templates, and script examples.
- `references/script-interfaces.md` — short invocation contracts for the orchestration scripts; prefer this over reading full script source when you only need args/output semantics.

Use these scripts when helpful:
- `scripts/validate_state.py` — validate `STATE.md` structure and required fields.
- `scripts/validate_protocol.py` — validate protocol invariants that go beyond schema shape.
- `scripts/check_transition.py` — validate candidate status transitions against the orchestration state machine.
- `scripts/evaluate_progress.py` — compute actionable loops, branch readiness, and merge readiness.
- `scripts/check_stall.py` — detect dead loops or repeated no-fix rounds.
- `scripts/compute_next_poll.py` — compute deterministic next-poll delay.
- `scripts/render_progress.py` — render progress, pause, resume, repair, or final messages from state.
