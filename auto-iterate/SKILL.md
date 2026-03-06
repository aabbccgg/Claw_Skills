---
name: auto-iterate
description: >
  REQUIRED for multi-iteration tasks. Loops a workflow until criteria met.
  Triggers: "自动迭代", "迭代", "循环执行", "重复直到", "iterate until done", "loop until".
---

# Auto-Iterate

**Round** = execute + review + fix. **Stop** = user criteria AND P0=0 P1=0.
State dir: `~/.openclaw/workspace/iterations/<YYYYMMDD-HHMMSS-desc>/`.
STATE.md = single source of truth.
P0 blocks round (retry once; fails → pause). P2: fix or skip.

## Rules

1. Read+update STATE.md each turn. Required fields: task, target, current, status, subagent_session, last_subagent_result. Max 2h total → pause. Re-read this skill every 3 rounds (round%3==0).
2. Inline review by default. Subagent only when isolation/model/user requires it.
3. Validate: ≥1 step + ≥1 criterion. Ask if missing.

## Loop

**Init**: create task dir + STATE.md + heartbeat entry (`[auto-iterate:<id>]`) + report start.
**Round**: execute step → spawn subagent review → cron self-wake → on wake: check result → **report progress** → complete or increment+loop.
**Complete**: set STATE.md status=complete + remove heartbeat/cron + **report final result**.

## Reporting

Always use `message(action="send")` for progress and completion — cron isolated sessions have no chat delivery.
Store `report_to` in STATE.md at init:
```
- **report_to**: {channel: "telegram", target: "<chat_id>", threadId: "<topic_id>"}
```
Report each round: `message(action="send", target="<chat_id>", message="⚡ Round 3/7 — <status>")`.
**Only the session that sets status=complete sends the final report.** Already complete → NO_REPLY.

## Cron Wake

⚠️ Subagent auto-announce does NOT trigger an agent turn. Only cron self-wake drives loop continuation.
Always use `sessionTarget="isolated"` — keeps each wake stateless and avoids polluting any persistent session.

### One round per cron wake

One round per wake: check subagent → report → next step → spawn subagent → cron → END TURN.

### Stale wake detection

On wake: read STATE.md FIRST. If `status=complete` → `NO_REPLY`, do nothing.

### Schedule timestamp

Compute `at` dynamically: `date -u -d '+Ns' '+%Y-%m-%dT%H:%M:%SZ'` (N = delay seconds). Never hardcode.

### Cron template (all agents)

⚠️ Use the `cron` tool directly. Do NOT use `exec` / CLI (`openclaw cron add ...`) — CLI calls can be aborted mid-execution, breaking the loop.

Read own agentId from runtime info (e.g. `main`, `general`), pass as `agentId` on the job:

```
cron(action="add", schedule={kind:"at", at:"<UTC timestamp>"},
  agentId="<own_agentId>",
  payload={kind:"agentTurn", message:"...", timeoutSeconds:300},
  delivery={mode:"none"},
  sessionTarget="isolated")
```

Message template:
```
[auto-iterate:<id>] Wake: check round N

State: <path>
Subagent: <key>
Workdir: <path>
Target: <criteria>
Round: N
Report to: {channel, target, threadId}

Steps: 1.Read STATE (if complete→NO_REPLY) 2.sessions_history 3.Report progress via message(action=send) 4.If !done: next step+subagent+STATE+cron 5.If done: set complete+final report
```
Each cron wake = **fresh isolated session** — agentTurn message MUST be self-contained.

### Delay

Trivial 5s, simple 15s, moderate 45s, complex 90s.
Decay on pending: R1=100% R2=75% R3+=50% of initial (min 5s); >20 retries → pause.

## Subagent Timeout

Always set `runTimeoutSeconds: 3600` (60 min) on spawned subagents. Prevents infinite cron polling if subagent hangs.

## Edge Cases

Dead loop: 3+ rounds with issues but 0 fixed, or no issues but criteria unmet → pause.
Recovery: read STATE.md; if `awaiting-review`: check subagent via `sessions_history` and reschedule wake.
