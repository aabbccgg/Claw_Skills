# Script interfaces

Use this file instead of reading full script source when you only need the invocation contract.

## validate_state.py
- Purpose: validate `STATE.md` structure and required fields
- Args: `state_path [--json]`
- Output:
  - exit `0` when valid, nonzero when invalid
  - JSON mode: `{ok, errors, warnings, statePath}`

## validate_protocol.py
- Purpose: validate orchestration invariants beyond raw schema shape
- Args: `state_path [--json]`
- Output:
  - exit `0` when valid, nonzero when invalid
  - JSON mode: `{ok, errors, warnings}`

## check_transition.py
- Purpose: validate a candidate state transition against canonical event vocabulary
- Args: `state_path --event <canonical-event> [--to <status>] [--json]`
- Canonical events:
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
- Output:
  - exit `0` when valid, nonzero when invalid
  - JSON mode: `{ok, from, event, to?, allowedTargets, errors}`

## evaluate_progress.py
- Purpose: compute actionable loops, branch readiness, merge readiness, and branch conflicts
- Args: `state_path [--json]`
- Output:
  - JSON mode: `{loopsMode, status, firstIncompleteTopLevel, actionableLoops, allLoops}`

## check_stall.py
- Purpose: detect dead-loop / repeated no-fix conditions and reset suggestions
- Args: `state_path [--threshold N] [--json]`
- Output:
  - JSON mode: `{ok, shouldPause, threshold, findings, resetSuggested, recommendedEvent, recommendedTo}`

## compute_next_poll.py
- Purpose: compute deterministic next-poll delay
- Args:
  - direct mode: `--complexity <level> [--poll-streak N] [--json]`
  - state mode: `--state-path <STATE.md> [--json]`
- Output:
  - plain mode: delay seconds
  - JSON mode: `{complexity, pollStreak, baseSeconds, factor, delaySeconds}`

## render_progress.py
- Purpose: render user-visible progress text from committed state
- Args: `state_path [--mode progress|pause|resume|repair|final]`
- Output:
  - plain text only, ready for `message(action="send")`

## Cron capability contract
- Cron path: native cron first, `exec` + `openclaw cron ...` CLI fallback second.
- Preferred path: native OpenClaw `cron` tool.
- Fallback path: `exec` + `openclaw cron ...` CLI only when native `cron` is unavailable.
- Never improvise arbitrary shell-based cron management outside that fallback.
- If neither is available, the wake must persist runtime limitation and stop so watchdog can repair.

## test_fixtures.py
- Purpose: regression-check all fixture states across validators/renderers
- Args: none
- Output:
  - JSON object with `{summary, results}`
  - nonzero exit if any unexpected fixture failure occurs
