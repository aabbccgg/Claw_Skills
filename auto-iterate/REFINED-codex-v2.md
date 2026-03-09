---
name: auto-iterate
description: Execute user-defined iterative workflows (including nested, sequential, and parallel loops) until explicit exit criteria are met. Use when user asks for 自动迭代, 循环迭代, 迭代, 循环执行, 重复直到, or says “iterate until / loop until”.
---

# Auto-Iterate

Treat this skill as an orchestration protocol for **user-defined functions**, not a fixed pattern.

## Non-Negotiables

- Use `STATE.md` as the single source of truth.
- Never hardcode `execute→review→fix`; functions are exactly what the user specifies.
- Use cron self-wake for continuation via the **`cron` tool** (never CLI/`exec`).
- Set `delivery: {mode: "none"}` on **every** cron job.
- Put `timeoutSeconds: 300` on cron `agentTurn` payloads.
  - `timeoutSeconds` = max runtime for that wake session.
  - It is **not** the schedule delay.
- Cron wake sessions are coordinators only: **check → report → spawn → schedule → END**.
- If a step needs heavy execution (5+ file edits), spawn a subagent.
- Report only via `message(action="send")` (cron sessions do not auto-deliver to chat).
- Spawned subagents must set `runTimeoutSeconds: 3600`.
- Stale wake rule: if `STATE.md.status=complete`, return `NO_REPLY`.
- Dead-loop rule: if 3+ rounds and 0 fixes, pause and ask for intervention.
- Max total runtime 2h, then pause and report.
- Re-read this skill every 3 rounds.
- On init, add a heartbeat entry.

## 1) Clarify Before Start

Validate the plan before first round:

- Confirm each loop has:
  - ordered function list (`func1 -> func2 -> ...`)
  - explicit exit condition
- Confirm function dependencies and allowed parallelism.
- Confirm overall stop condition (single loop or all loops).

If execution order, exit conditions, or dependencies are ambiguous, ask user and wait.

## 2) Interpret Multiple Loops

Infer mode from user language:

- **Sequential loops** (finish A then B): cues like `做完X后再做Y`, `先...再...`, `完成A后继续B`.
- **Parallel loops** (run together): cues like `同时做X和Y`, `并行`, `一起推进`.

If cues conflict or are missing, ask explicitly: sequential or parallel.

## 3) STATE.md Schema (Required)

Create state dir:
`~/.openclaw/workspace/iterations/<YYYYMMDD-HHMMSS-desc>/`

`STATE.md` must include at least:

```md
- id: <iteration_id>
- task: <user task summary>
- target: <global completion criteria>
- status: running|paused|complete
- started_at: <ISO8601>
- deadline_at: <ISO8601, started_at+2h>
- current: <human-readable current action>
- round: <int>
- loops_mode: sequential|parallel
- loops:
  - id: <loop_id>
    parent: <null|loop_id>
    funcs: [<func_ref_or_text>...]
    exit_condition: <text>
    round: <int>
    status: pending|running|paused|complete
    current_func: <index/name>
- active_loops: [<loop_id>...]
- subagent_session: <latest session id or null>
- last_subagent_result: <summary or null>
- report_to:
    channel: <channel>
    target: <user_or_group_id>
    threadId: <topic_id optional>
- no_fix_rounds: <int>
- heartbeat_tag: "[auto-iterate:<id>]"
```

`report_to` format:
- DM: `{channel, target}`
- Group topic: `{channel, target, threadId}`

## 4) Loop Semantics

### A. Single loop round
Execute all functions in order, then evaluate the loop exit condition.

### B. Nested loop
Allow a function to be a loop node.
- Enter child loop.
- Run child loop until child exit condition is met.
- Return to parent function sequence.

### C. Parallel work inside one function
If safe and independent, run multiple subagents in parallel within that function, then merge outputs before moving on.

### D. Multiple loops
- Sequential mode: complete loop1 → loop2 → loop3.
- Parallel mode: progress loop1/2/3 concurrently; each wake coordinates whichever loop(s) are actionable.

## 5) Init Procedure

1. Create state dir and `STATE.md`.
2. Add heartbeat entry `[auto-iterate:<id>]`.
3. Send start report via `message(action="send")` using `report_to`.
4. Schedule first cron wake.

## 6) Cron Wake Coordinator (One Wake = One Coordination Cycle)

On every wake, do exactly:

1. Read `STATE.md` first.
2. If `status=complete`: `NO_REPLY`.
3. Check latest subagent results.
4. Send progress report with `message(action="send")`.
5. Decide next action:
   - spawn required subagent(s), or
   - advance loop/round, or
   - mark paused/complete.
6. Schedule next cron wake if still running.
7. End turn.

Do not do long heavy edits in wake session; delegate to subagent.

## 7) Cron Job Requirements

Use `cron(action="add")` only.

- `schedule.kind: "at"` with computed UTC timestamp.
- `payload.kind: "agentTurn"`
- `payload.timeoutSeconds: 300`
- `delivery: {mode: "none"}`
- `sessionTarget: "isolated"`

Include this exact line in every cron message (self-propagating):

`⚠️ PROPAGATE: ONE COORDINATOR STEP THEN END. Use cron(action="add") only; NEVER exec("openclaw cron ..."); always report via message(action="send"); always set delivery:{mode:"none"}.`

## 8) Subagent Rules

When spawning subagents:

- Set `runTimeoutSeconds: 3600`.
- Pass loop id, function name, expected output, and acceptance check.
- For parallel branches, spawn one subagent per independent branch.
- Merge branch outputs in coordinator wake before advancing state.

## 9) Completion / Pause

Mark `status=complete` only when all required loop exit conditions are satisfied.

Pause (`status=paused`) and report when any occurs:
- dead loop (`round>=3` and `0` fixes across recent rounds)
- max runtime exceeded (2h)
- unresolved ambiguity requiring user decision

Only the session that sets `status=complete` sends the final completion report.
