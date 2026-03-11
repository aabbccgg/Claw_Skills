# Transition model and loop progression

## Explicit state machine

Allowed transitions:

| From | Event | To |
|---|---|---|
| `running` | worker spawned and successor wake durably committed | `awaiting-review` |
| `awaiting-review` | result ingested and next action chosen | `running` / `paused` / `complete` |
| `running` | ambiguity / retry exhaustion / dead loop / deadline / quota suspension | `paused` |
| `paused` | explicit user resume or quota-restored wake | `running` |
| `running` | global completion criteria met and terminal cleanup committed | `complete` |

Forbidden transitions:
- `complete -> *`
- `paused -> running` without an explicit resume event
- `awaiting-review -> awaiting-review` after successful ingestion
- `running -> complete` before terminal cleanup path is prepared

Coordinator rules:
- After any successful worker ingestion, the same wake must choose exactly one next transition before END.
- Existing-agent dispatch and existing-agent result ingestion are separate phases. Do not dispatch and synchronously wait for the final worker result in the same wake.

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
