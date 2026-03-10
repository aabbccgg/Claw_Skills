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

## Non-Negotiables

- Use `STATE.md` as single source of truth.
- Continue only via cron self-wake using the **`cron` tool** (never `exec("openclaw cron ...")`).
- Set `delivery: {mode: "none"}` on **every** cron job.
- Set `payload.timeoutSeconds: 300` on every cron job. This is wake session runtime cap, **not** polling delay.
- Heavy execution (e.g., 5+ file edits) must run in subagent.
- Report only via `message(action="send")`.
- Spawned subagents must use `runTimeoutSeconds: 7200`.
- **Every `sessions_spawn` must be followed by a cron wake in the same turn.** No cron = no monitoring = broken loop.
- When spawning subagents via `sessions_spawn`, always pass your own `agentId` (same as cron).
- Max total runtime per task: 3h (`deadline_at`). Exceeding it pauses loop and reports.
- Re-read this skill every 3 rounds.
- On init, add heartbeat entry `[auto-iterate:<id>]`.
- Every cron wake message must be **self-contained**: include state path, subagent session key, workdir, report_to, and the self-propagating constraint line (see §6).

---

## 1) Admission Gate — REQUIRED BEFORE ROUND 1

Do **not** start iteration until both are present:

1. **At least 1 executable step/function**
2. **At least 1 explicit completion criterion**

If either is missing: block execution, ask user for missing info, and wait.

Minimum acceptable structure:
- Steps: `func1 -> func2 -> ...` (or loop definitions)
- Criteria: testable completion condition(s)

---

## 2) Loop Topology & Execution Semantics

Infer mode from wording:
- Sequential: `先...再...`, `做完A后做B`
- Parallel: `同时`, `并行`, `一起推进`

If ambiguous/conflicting, ask explicitly.

Validate each loop has:
- ordered function list
- loop-local exit condition
- dependency/parallel-safety constraints

Execution:
- Single loop: run all functions in order, then evaluate exit condition.
- Nested loop: enter child loop → run until child exit → return to parent.
- Parallel branches: if independent/safe, run branch subagents in parallel, then merge outputs.
- Multiple loops:
  - Sequential mode: loop1 → loop2 → ...
  - Parallel mode: progress actionable loops concurrently each wake.

---

## 3) STATE.md Schema (Required)

State dir:
`~/.openclaw/<your_agent_workspace>/iterations/<YYYYMMDD-HHMMSS-desc>/`

`STATE.md` must include:

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

`report_to`:
- DM: `{channel, target}`
- Group topic: `{channel, target, threadId}`

---

## 4) Init Procedure

1. Create state dir + `STATE.md`.
2. Write validated steps/criteria and loop topology.
3. Add heartbeat entry `[auto-iterate:<id>]`.
4. Send start message via `message(action="send")` using `report_to`.
5. Schedule first cron wake.

---

## 5) Cron Wake Coordinator (One Wake = One Coordination Cycle, with Recovery)

Per wake, do exactly:

1. Read `STATE.md` first.
2. If `status=complete` (including stale wake) → `NO_REPLY`.
3. Run recovery branch in §7.
4. Check and update state.
5. Send progress report.
6. Decide one of: spawn subagent(s) / advance round or loop / pause / complete. **Mandatory post-spawn cron**: If you spawned a subagent, you MUST schedule a cron wake before ending the turn.
7. **Cleanup before advance**: when advancing to a new task/loop, remove the current cron job (`cron(action="remove", jobId=<cron_job_id>)`), reset `deadline_at` to `now + 3h`, update `cron_job_id` in STATE.md.
8. Schedule next cron wake if still running/awaiting-review.
9. End turn.

Do not run heavy edits (e.g., 5+ file edits) in coordinator; delegate to subagent.

---

## 6) Cron Contract + Delay Decay (REQUIRED)

Cron self-wake must use `cron(action="add")` only (never `exec("openclaw cron ...")`) with:
- `schedule.kind: "at"` (UTC timestamp)
- `payload.kind: "agentTurn"`
- `payload.timeoutSeconds: 300`
- `delivery: {mode: "none"}`
- `sessionTarget: "isolated"`
- `agentId: "<own_agentId>"` (read from runtime info)

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

And this line **verbatim** (self-propagating constraint):

`⚠️ RULES(copy this line verbatim into every child cron): ONE ROUND→END. cron(action="add")→YES, exec("openclaw cron")→NO. message(action="send")→YES. delivery={mode:"none"}. Heavy work→spawn subagent.`

---

## 7) Crash / Restart Recovery (State Recovery)

At wake start, always recover from persisted state:

1. Read `STATE.md`.
2. If `status=awaiting-review`:
   - Check `subagent_session` via `sessions_history`.
   - If subagent completed: ingest result, clear awaiting flag. If round produced 0 fixes → increment `no_fix_rounds`; otherwise reset `no_fix_rounds` to 0. Continue coordinator flow.
   - If still running/pending: schedule next wake at delay-decay scheduling, end turn.
   - If missing/failed/crashed: increment `retry_count`. If `retry_count >= 4` → pause and report. Otherwise respawn equivalent subagent.
3. If stale wake and already complete: `NO_REPLY`.

This recovery path is mandatory for crashed/missed sessions.

---

## 8) Completion / Pause Rules

Set `status=complete` only when user criteria are met.

**On complete or pause**: remove all related cron jobs (`cron(action="remove", jobId=<cron_job_id>)`), remove heartbeat entry, then send final report.

Pause (`status=paused`) and report when:
- dead loop (`no_fix_rounds>=3` and no meaningful fixes)
- per task runtime exceeded 3h
- ambiguity blocks requiring user decision
- retry_count >= 4

Only the session that sets `status=complete` sends final completion report.
