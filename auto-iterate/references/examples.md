# Canonical examples

## 1. Coordinator wake add

```json
{
  "action": "add",
  "schedule": {"kind": "at", "at": "2026-03-10T05:20:00Z"},
  "agentId": "<own_agent_id>",
  "payload": {
    "kind": "agentTurn",
    "timeoutSeconds": 300,
    "message": "[auto-iterate] coordinator wake\nIteration: iter-20260310-130200\nRound: 3\nStatus: awaiting-review\nState path: /abs/path/STATE.md\nWorkdir: /abs/workdir\nCurrent loop: refine-code\nCurrent branch: backend\nSubagents: [child:abc]\nCurrent wake id: job_123\nWorkflow deadline: 2026-03-10T08:02:00Z\nNext action: poll\nReport_to: {channel: telegram, target: \"-100123\", threadId: \"17\"}\n⚠️ RULES: ONE CYCLE->END. Use cron tool, not shell. Commit state before report. Heavy work stays in subagent."
  },
  "delivery": {"mode": "none"},
  "sessionTarget": "isolated"
}
```

## 2. Watchdog wake add

```json
{
  "action": "add",
  "schedule": {"kind": "every", "everyMs": 600000},
  "agentId": "<own_agent_id>",
  "payload": {
    "kind": "agentTurn",
    "timeoutSeconds": 180,
    "message": "[auto-iterate] watchdog wake\nState path: /abs/path/STATE.md\nRole: watchdog\nRepair only. No heavy work. No user-task execution."
  },
  "delivery": {"mode": "none"},
  "sessionTarget": "isolated",
  "deleteAfterRun": false
}
```

## 3. Subagent spawn brief

```text
Task: Execute one branch of the iteration.
Iteration: iter-20260310-130200
Loop: refine-code
Branch: backend
State path: /abs/path/STATE.md (read-only)
Workdir: /abs/workdir
Target: tests pass and review comments resolved
Return YAML envelope:
- status: success|no-change|blocked|failed
- summary: short text
- artifacts: [paths]
- criteria_assessment: met|not-met|unclear
- next_action_hint: spawn|advance|pause|complete|retry
Do not edit orchestration state. Do not schedule cron.
```

## 4. Result envelope

```yaml
status: success
summary: Fixed failing serializer tests and updated migration.
artifacts:
  - backend/app/serializers.py
  - backend/tests/test_serializer.py
criteria_assessment: not-met
next_action_hint: advance
```

## 5. Progress report templates

Use this format for all user-visible progress messages. Adapt content to the current state; keep the structure.

Routing rule: the coordinator sends these messages directly to `origin.report_to` via `message(action="send")`. User-visible text must contain only content meaningful to the user — no routing metadata.

### During subagent execution (polling)

```text
🔄 [auto-iterate] Round 3 | Loop: fix-rawdata-error (2:03 PM)

Developer 🔄 Working on the fix
• Completed: dark mode ✅, admin whitelist ✅
• In progress: rawData.some error fix

Next: wait for developer completion, then hand off to tester
⏰ Next check: 2:09 PM
📊 Time remaining: ~1h45m (deadline 3:48 PM)
```

### After subagent completion + advancing

```text
🔄 [auto-iterate] Round 2 (12:03 PM)

Developer ✅ Completed and committed (ae9dca7)
• Dashboard: gain/loss CSS classes, 3Y period, defaultPeriod
• Watchlist: batch price fetch, price column, EmptyState, collapsed search panel
• tsc ✅ | pytest 97 passed ✅

Tester 🔄 R2 verification dispatched and running…

⏰ Next check: 12:11 PM
📊 Time remaining: ~2h15m (deadline 2:18 PM)
```

### Template fields (required)

| Field | Source |
|-------|--------|
| Header | `🔄 [auto-iterate] Round {round}` + optional `Loop: {loop_id}` + `({HH:MM} local)` |
| Actor lines | One per subagent/role. Use ✅ done, 🔄 running, ❌ failed, ⏸️ paused, ▶️ resumed, ⚠️ repair |
| Bullet details | Commit hash, specific changes, test results — keep concise |
| Next | The decided next action from DECIDE step |
| ⏰ Next check | `next_expected_wake_at` in the user's local time |
| 📊 Time remaining | `workflow_deadline_at - now`, with deadline time shown |

### Pause

```text
⏸️ [auto-iterate] Round 4 | Loop: refine-code (3:30 PM)

Reason: Claude quota suspension
Expected resume: 4:15 PM (quota reset + 90s)
Current progress: 3/5 loops done, backend branch waiting to continue

📊 Time remaining: ~18m (deadline 3:48 PM)
```

### Resume

```text
▶️ [auto-iterate] Round 4 | Loop: refine-code (4:16 PM)

Status: automatic iteration resumed
Reason: Claude quota restored / coordinator recovered control
Current progress: backend branch resumed, preparing tester verification

Next: continue Round 4 development and verification
⏰ Next check: 4:24 PM
📊 Time remaining: ~1h12m (deadline 5:28 PM)
```

### Watchdog / repair alert

```text
⚠️ [auto-iterate] Round 3 | Loop: round3 (2:20 PM)

Status: coordinator wake failed, watchdog repaired the chain
Handled: recreated the coordinator wake, retained the old wake for cleanup
Impact: iteration state was preserved and will continue from the latest committed STATE

Next: wait for the new coordinator wake to resume polling
⏰ Next check: 2:28 PM
📊 Time remaining: ~1h58m (deadline 4:18 PM)
```

### Final completion

```text
✅ [auto-iterate] Complete! (3:42 PM)

Completed 4 rounds and 6 branches successfully
• Core fixes: serializer, migration, dark mode
• Tests: 97 passed ✅, 0 failed
• Commits: ae9dca7 → f3b1c02

Cleanup: coordinator wake, watchdog, and 1 pending wake removed
Total runtime: 2h40m
```

---

## 6. Telegram routing examples

These are internal routing objects for the coordinator to use with `message(action="send")`. They are **not** part of the user-visible message body.

DM:

```json
{"channel":"telegram","target":"12345678"}
```

Group topic:

```json
{"channel":"telegram","target":"-1009876543210","threadId":"42"}
```
