# Canonical examples

## 1. Coordinator wake cron.add payload

```json
{
  "action": "add",
  "job": {
    "name": "auto-iterate-coordinator-wake",
    "schedule": {"kind": "at", "at": "2026-03-10T05:20:00Z"},
    "agentId": "<own_agent_id>",
    "payload": {
      "kind": "agentTurn",
      "timeoutSeconds": 1800,
      "message": "[auto-iterate] coordinator wake\nIteration: iter-20260310-130200\nRound: 3\nStatus: awaiting-review\nState path: /abs/path/STATE.md\nWorkdir: /abs/workdir\nCurrent loop: refine-code\nCurrent branch: backend\nSubagents: [child:abc]\nCurrent wake id: job_123\nNext action: poll\nReport_to: {channel: telegram, target: \"-100123\", threadId: \"17\"}\n⚠️ RULES: ONE CYCLE->END. Use cron tool, not shell. Commit state before report. Heavy work stays in worker."
    },
    "delivery": {"mode": "none"},
    "sessionTarget": "isolated"
  }
}
```

## 2. Watchdog cron.add payload

```json
{
  "action": "add",
  "job": {
    "name": "auto-iterate-watchdog",
    "schedule": {"kind": "every", "everyMs": 600000},
    "agentId": "<own_agent_id>",
    "payload": {
      "kind": "agentTurn",
      "timeoutSeconds": 1800,
      "message": "[auto-iterate] watchdog wake\nState path: /abs/path/STATE.md\nRole: watchdog\nRepair only. No heavy work. No user-task execution."
    },
    "delivery": {"mode": "none"},
    "sessionTarget": "isolated"
  }
}
```

## 3. Worker brief

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

## 4. Script invocation examples

```bash
# Validate state structure before commit or cleanup
python3 scripts/validate_state.py /abs/path/STATE.md --json

# Validate protocol invariants
python3 scripts/validate_protocol.py /abs/path/STATE.md --json

# Check transition validity
python3 scripts/check_transition.py /abs/path/STATE.md --event worker-result --to running --json

# Evaluate loops and branch readiness
python3 scripts/evaluate_progress.py /abs/path/STATE.md --json

# Detect dead-loop / no-fix-rounds stalls
python3 scripts/check_stall.py /abs/path/STATE.md --json

# Compute next poll delay
python3 scripts/compute_next_poll.py --complexity moderate --poll-streak 2

# Render a user-visible status message
python3 scripts/render_progress.py /abs/path/STATE.md --mode progress
```

## 5. User-visible report templates

Routing rule: the coordinator sends these messages directly to `origin.report_to` via `message(action="send")`. User-visible text contains only user-meaningful content.

### Progress

```text
🔄 [auto-iterate] Round 3 | Loop: fix-rawdata-error (2:03 PM)

Developer 🔄 Working on the fix
• Completed: dark mode ✅, admin whitelist ✅
• In progress: rawData.some error fix

Next: wait for developer completion, then hand off to tester
⏰ Next check: 2:09 PM
```

### Pause

```text
⏸️ [auto-iterate] Round 4 | Loop: refine-code (3:30 PM)

Reason: Claude quota suspension
Expected resume: 4:15 PM (quota reset + 90s)
Current progress: 3/5 loops done, backend branch waiting to continue

Status window: paused until explicit resume or quota recovery
```

### Resume

```text
▶️ [auto-iterate] Round 4 | Loop: refine-code (4:16 PM)

Status: automatic iteration resumed
Reason: Claude quota restored / coordinator recovered control
Current progress: backend branch resumed, preparing tester verification

Next: continue Round 4 development and verification
⏰ Next check: 4:24 PM
```

### Repair alert

```text
⚠️ [auto-iterate] Round 3 | Loop: round3 (2:20 PM)

Status: coordinator wake failed, watchdog repaired the chain
Handled: recreated the coordinator wake, retained the old wake for cleanup
Impact: iteration state was preserved and will continue from the latest committed STATE

Next: wait for the new coordinator wake to resume polling
⏰ Next check: 2:28 PM
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
