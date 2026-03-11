# Recovery and watchdog procedures

## Coordinator recovery order

Run in this order on every isolated coordinator wake:

1. Read `STATE.md`.
2. Exit if `status: complete`.
3. Validate or acquire the writer lease.
4. Verify liveness:
   - `current_wake_job_id` exists
   - `next_expected_wake_at` is not badly overdue
5. If the wake chain is broken, add a replacement coordinator wake immediately and persist it before deeper work.
6. If `coordination.alert_needed: true`, preserve it for the next recovered coordinator REPORT step; the coordinator clears it during PERSIST in the same cycle that emits the `⚠️` repair alert during REPORT.
7. Inspect active workers.
8. Ingest finished results.
9. Choose exactly one next transition.
10. Persist full state.
11. Schedule successor wake if still non-terminal.
12. Remove old wake ids only after the replacement wake is durable.
13. Report from committed state.

## Broken wake chain repair

Treat the chain as broken if any is true:
- `current_wake_job_id` is null while workflow is non-terminal
- `now > next_expected_wake_at` by more than one poll interval
- state says `awaiting-review` but no poll wake exists

Repair sequence:
1. Add a fresh isolated coordinator wake.
2. Persist the new id as `next_wake_job_id`.
3. Promote it to `current_wake_job_id`.
4. Push the old id, if any, into `cleanup_pending[]`.
5. Update `next_expected_wake_at`.
6. Continue with normal coordinator logic.

## Worker failure handling

Classify each active worker as:
- `running`
- `success`
- `no-change`
- `blocked`
- `failed`
- `timed-out`
- `stalled`

Suggested handling:
- `success` / `no-change` / `blocked`: ingest and decide next transition
- `running`: keep polling
- `failed` / `timed-out` / `stalled`: increment retry counters for the owning loop or branch

Existing-agent note:
- A `sessions_send(..., timeoutSeconds=0)` enqueue is dispatch success, not worker completion.
- A missing final result in the same wake is normal; persist `awaiting-review` and poll later.
- Do not rewrite state to `dispatch failed` unless the enqueue itself failed.

Pause if retries are exhausted for the active branch or loop.

## Watchdog policy

Install one recurring watchdog at init. Keep it independent from the coordinator wake chain.

Watchdog checks:
- `last_cycle_at` freshness
- overdue `next_expected_wake_at`
- missing `current_wake_job_id`
- stale `awaiting-review` with no recent `last_checked_at` on active workers
- repeated cleanup failures in `cleanup_pending[]`

Watchdog repair rules:
1. Recreate the coordinator wake when missing or overdue.
2. Persist repair data.
3. Increment `watchdog_tripped_count`.
4. Avoid duplicate user reports if repair succeeds silently.
5. Set `coordination.alert_needed: true` in state when repair is triggered. Do not send user messages directly.
6. Exception: if `watchdog_tripped_count >= 3` and the coordinator has still not recovered, send one alert using the `⚠️` watchdog-repair template from `references/examples.md`, then set `coordination.alert_sent: true` to prevent duplicates.
7. Otherwise, leave `coordination.alert_needed: true` for the next recovered coordinator cycle to report.

Repair verification checklist:
- `coordination.current_wake_job_id` points to the replacement wake
- `coordination.next_expected_wake_at` is refreshed
- superseded wake ids, if any, are retained in `cleanup_pending[]`
- `coordination.alert_needed` remains true until a recovered coordinator reports the repair

If any verification item is missing, the repair is incomplete. Keep watchdog alive, preserve repair state, and retry instead of assuming the chain is healthy.

## Quota suspension integration

Before expensive spawns or respawns that will use Claude-family models, verify quota directly from runtime-available provider metadata. Do not depend on external skill state.

If suspended:
1. Set `status: paused`, `resume.mode: quota-auto`, `resume.blocked_by: claude-quota`.
2. Persist `resume.resume_at` from provider reset metadata, or `now + 1h` as fallback.
3. Persist all loop/branch context needed to continue: `progress.active_loop_ids`, current function, pending worker session keys, any partial results.
4. Add a resume coordinator wake at or after `resume.resume_at`.
5. Keep the watchdog alive.
6. Report the pause using the `⏸️` pause template.

Resume sequence:
1. Wake at `resume.resume_at`. Check `resume.blocked_by: claude-quota` in state.
2. Re-verify quota directly.
3. If clear: clear `resume.*`, transition `paused -> running`, report using the `▶️` resume template, and continue from `progress.active_loop_ids` and current functions.
4. If still blocked: update `resume.resume_at`, reschedule, and report using the `⏸️` pause template only if the resume time materially changed.

## Terminal cleanup

Cleanup is idempotent. Keep retrying until both `cleanup.wake_cleanup_complete` and `cleanup.terminal_report_sent` are true.

Sequence:
1. Move `current_wake_job_id` and `next_wake_job_id` into `cleanup_pending[]`. Persist.
2. Remove each id in `cleanup_pending[]`, excluding `watchdog_job_id`. Persist after each removal. Retain failed ids in `cleanup_pending[]`.
3. Set `cleanup.wake_cleanup_complete: true` and persist.
4. If the final report has not yet been delivered, send it using the `✅` final completion template.
5. If final report delivery failed or `cleanup.terminal_report_sent` is still false, the watchdog or next recovered coordinator wake must retry the final report before shutdown.
6. After the final report succeeds, set `cleanup.terminal_report_sent: true` and persist.
7. After both flags are true, remove `watchdog_job_id`. If removal fails, the watchdog detects `terminal_report_sent: true` on its next run and removes itself without alerting.
