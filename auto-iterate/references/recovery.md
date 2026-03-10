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
6. Inspect active subagents.
7. Ingest finished results.
8. Choose exactly one next transition.
9. Persist full state.
10. Schedule successor wake if still non-terminal.
11. Remove old wake ids only after the replacement wake is durable.
12. Report from committed state.

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

## Subagent failure handling

Classify each active subagent as one of:
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

Pause if retries are exhausted for the active branch or loop.

## Dead-loop handling

Mark a loop or branch unhealthy when repeated rounds produce no meaningful change.

Suggested policy:
- increment `no_fix_rounds` when a result is `no-change` or when criteria remain unchanged after a nominal success
- reset `no_fix_rounds` when there is meaningful progress
- pause when `no_fix_rounds >= 3` unless the user explicitly requested continued brute-force iteration

## Watchdog policy

Install one recurring watchdog at init. Keep it independent from the coordinator wake chain.

Watchdog checks:
- `last_cycle_at` freshness
- overdue `next_expected_wake_at`
- missing `current_wake_job_id`
- stale `awaiting-review` with no recent `last_checked_at` on active subagents
- repeated cleanup failures in `cleanup_pending[]`

Watchdog repair rules:
1. Recreate the coordinator wake when missing or overdue.
2. Persist repair data.
3. Increment `watchdog_tripped_count`.
4. Avoid duplicate user reports if repair succeeds silently.
5. Send a user-visible alert only when repair fails repeatedly or the workflow must pause.

## Quota suspension integration

Before expensive spawns or respawns, run the `claude-auto-resume` skill.

If it indicates suspension:
1. Set `status: paused`.
2. Record `resume.mode: quota-auto` and `resume.blocked_by: claude-quota`.
3. Persist `resume.resume_at`.
4. Add a resume coordinator wake for `resume.resume_at` or later.
5. Keep the watchdog alive.
6. Report the pause once.

Resume sequence:
1. Wake at `resume.resume_at`.
2. Re-check quota.
3. If clear, set `paused -> running`, clear the block, and continue.
4. If still blocked, update `resume.resume_at`, reschedule, and report only if the expected resume time materially changed.

## Terminal cleanup

Cleanup is idempotent. Keep trying until state says it is complete.

Remove all known wake ids:
- `current_wake_job_id`
- `next_wake_job_id`
- `watchdog_job_id`
- every id in `cleanup_pending[]`

Then:
1. set `cleanup.wake_cleanup_complete: true`
2. send the final report if not yet sent
3. set `cleanup.terminal_report_sent: true`

If any removal fails, leave the id in `cleanup_pending[]` and retry on the next watchdog or terminal wake.
