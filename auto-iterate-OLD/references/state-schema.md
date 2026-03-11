# Canonical STATE.md schema

Use exactly one fenced YAML block in `STATE.md`.

```yaml
id: <iteration-id>
task: <short user task summary>
target: <explicit global completion criteria>
status: running|awaiting-review|paused|complete
started_at: <ISO8601>
workflow_deadline_at: <ISO8601>
workdir: <absolute path>
current: <short human-readable current action>
round: <int>
loops_mode: sequential|parallel
execution_mode: spawned-worker|existing-agent

origin:
  session_kind: interactive-dm|interactive-group|isolated-cron
  session_id: <session id>
  report_to:
    channel: telegram
    target: <user id or group id>
    threadId: <topic id or null>
  report_context_locked: true

coordination:
  state_version: <int>
  writer_session: <session id or null>
  lease_expires_at: <ISO8601 or null>
  pending_transition: idle|spawn|advance|pause|complete|resume
  last_cycle_at: <ISO8601>
  next_expected_wake_at: <ISO8601 or null>
  current_wake_job_id: <job id or null>
  next_wake_job_id: <job id or null>
  watchdog_job_id: <job id or null>
  cleanup_pending: []
  watchdog_tripped_count: <int>
  alert_needed: <bool>
  alert_sent: <bool>
  poll_streak: <int>

loops:
  - id: <loop id>
    parent: <loop id or null>
    kind: single|nested|parallel
    status: pending|running|paused|complete
    round: <int>
    funcs:
      - <step name>
    current_func: <step name or null>
    exit_condition: <text>
    merge_policy: all-success|quorum|custom-user-criterion|null
    branches:
      - branch_id: <branch id>
        status: pending|running|paused|complete
        funcs:
          - <step name>
        current_func: <step name or null>
        retry_count: <int>
        no_fix_rounds: <int>
        active_subagent: <child_session_key or null>
        last_progress_at: <ISO8601 or null>

subagents:
  - child_session_key: <session key>
    run_id: <run id or null for existing-agent mode>
    loop_id: <loop id>
    branch_id: <branch id or null>
    status: accepted|running|success|no-change|blocked|failed|timed-out|stalled
    started_at: <ISO8601>
    timeout_at: <ISO8601>
    last_checked_at: <ISO8601 or null>
    summary: <short text or null>
    criteria_assessment: met|not-met|unclear|null
    next_action_hint: spawn|advance|pause|complete|retry|null

progress:
  active_loop_ids: []
  last_subagent_result: <short text or null>
  last_failure_reason: <text or null>
  total_retry_count: <int>
  no_fix_rounds_total: <int>

resume:
  mode: none|quota-auto|user-resume
  blocked_by: none|claude-quota|user-input|repair-failed
  resume_at: <ISO8601 or null>
  note: <text or null>

cleanup:
  terminal_report_sent: <bool>
  wake_cleanup_complete: <bool>
```

## Field notes

- `workflow_deadline_at` is fixed at init: `started_at + 3h`. Never reset it.
- `execution_mode` records the selected orchestration mode for this workflow. Prefer `spawned-worker`; use `existing-agent` only when visibility and policy constraints are explicitly satisfied.
- `coordination.state_version` increments on every successful write.
- `coordination.writer_session` + `lease_expires_at` implement the single-writer lease.
- `coordination.current_wake_job_id` is the live coordinator wake.
- `coordination.next_wake_job_id` exists only during add-before-remove handoff.
- `coordination.cleanup_pending[]` retains obsolete wake ids that still need removal.
- `coordination.alert_needed` marks that the coordinator should emit a repair-related user-visible status message.
- `coordination.alert_needed` is cleared by the coordinator during PERSIST in the same cycle that will emit the repair alert during REPORT.
- `coordination.alert_sent` prevents duplicate watchdog repair alerts when the watchdog must use the narrow direct-alert exception.
- `progress.last_failure_reason` stores the latest orchestration or worker-mode failure reason, including existing-agent mode fallback causes.
- `loops[].branches[]` is required for parallel branches. Use stable branch ids.
- `subagents[]` is append/update history for workers. Do not collapse to one field.
- `resume.*` captures pauses caused by quota or explicit user-blocked states.
- `cleanup.*` makes terminal reporting and wake removal idempotent.

## Write discipline

1. Read state.
2. Acquire or confirm the writer lease.
3. Recompute the full next state.
4. Increment `state_version`.
5. Write the entire YAML block.
6. Only then send user-visible reports.

## Minimal STATE.md wrapper

~~~md
```yaml
<canonical state here>
```
~~~
