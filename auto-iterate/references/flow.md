# Transition model and loop progression

## Explicit state machine

Allowed transitions:

| From | Event | To |
|---|---|---|
| `running` | `worker-dispatched` | `awaiting-review` |
| `awaiting-review` | `worker-result` | `running` / `paused` / `complete` |
| `awaiting-review` | `worker-failed` | `running` / `paused` |
| `awaiting-review` | `worker-timeout` | `running` / `paused` |
| `running` | `pause-requested` / `dead-loop` / `quota-suspended` / `repair-failed` | `paused` |
| `paused` | `user-resume` / `quota-restored` | `running` |
| `running` | `complete-requested` | `complete` |

Forbidden transitions:
- `complete -> *`
- `paused -> running` without an explicit resume event
- `awaiting-review -> awaiting-review` after successful worker result ingestion
- `running -> complete` before terminal cleanup path is prepared

Canonical event vocabulary:
- `worker-dispatched`
- `worker-result`
- `worker-failed`
- `worker-timeout`
- `pause-requested`
- `dead-loop`
- `quota-suspended`
- `quota-restored`
- `user-resume`
- `complete-requested`
- `repair-failed`

Do not use ambiguous aliases such as `spawn`, `dispatch`, `worker-spawned`, or `result-ingested` in coordinator prompts or tooling.

Coordinator rules:
- After any successful worker result ingestion, the same wake must choose exactly one next transition before END.
- Worker dispatch and worker result ingestion are separate phases. Do not dispatch and synchronously wait for the final worker result in the same wake.

## Loop progression semantics

### Single loop
- Execute ordered `funcs`.
- Re-evaluate `exit_condition` after each worker result.
- If `exit_condition` is met, transition to `complete` or advance to the next top-level loop.

### Nested loops
- A child loop must satisfy its own `exit_condition` before the parent loop may advance.
- While a child loop is active, the parent loop is not actionable for advance.
- Parent `current_func` must remain at the child boundary while the child loop is active.

### Sequential multi-loop
- Only the first incomplete top-level loop is actionable.
- Loop `n+1` must not start until loop `n` is `complete`.

### Parallel top-level loops
- Multiple top-level loops may be actionable in the same wake.
- Keep worker tracking, retries, and merge decisions isolated per loop.

### Parallel branches inside a loop
- At most one active worker per branch.
- Evaluate `merge_policy` before loop-level advance:
  - `all-success`: every branch complete
  - `quorum`: majority complete
  - `custom-user-criterion`: coordinator must defer merge until the custom criterion is explicitly met

## Dead-loop policy

Use `no_fix_rounds` and `no_fix_rounds_total` as stall counters.

The coordinator must run `scripts/check_stall.py <state_path> --json` before deciding whether a loop should pause for stall.

Increment counters when:
- worker result is `no-change`
- or criteria remain unchanged after nominal success

Reset counters when meaningful progress is observed.

Pause when:
- branch `no_fix_rounds >= 3`
- or `progress.no_fix_rounds_total >= 3`
- unless the user explicitly requested continued brute-force iteration

Use `scripts/check_stall.py` to turn this policy into a deterministic pause recommendation.
