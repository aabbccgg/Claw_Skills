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
      "message": "[auto-iterate] coordinator wake\nIteration: iter-20260310-130200\nRound: 3\nStatus: awaiting-review\nState path: /abs/path/STATE.md\nWorkdir: /abs/workdir\nCurrent loop: refine-code\nCurrent branch: backend\nSubagents: [child:abc]\nCurrent wake id: job_123\nNext action: poll\nReport_to: {channel: telegram, target: \"-100123\", threadId: \"17\"}\n⚠️ RULES: ONE CYCLE->END. Native cron first; use exec+openclaw cron only as explicit fallback. Commit state before report. Heavy work stays in worker."
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
    "schedule": {"kind": "every", "everyMs": 180000},
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

## 4. CLI cron fallback examples

Cron path is native first, CLI fallback second. Use these only when the native `cron` tool is unavailable but `exec` can run `openclaw cron ...`. The flags below match the current OpenClaw CLI shape (`openclaw cron add --help`).

```bash
# Add one-shot coordinator wake
WAKE_MESSAGE="$(cat /abs/path/wake-message.txt)"
openclaw cron add \
  --name auto-iterate-coordinator-wake \
  --at 2026-03-10T05:20:00Z \
  --session isolated \
  --agent <own_agent_id> \
  --no-deliver \
  --timeout-seconds 1800 \
  --message "$WAKE_MESSAGE"

# Add recurring watchdog wake
WATCHDOG_MESSAGE="$(cat /abs/path/watchdog-message.txt)"
openclaw cron add \
  --name auto-iterate-watchdog \
  --every 180000 \
  --session isolated \
  --agent <own_agent_id> \
  --no-deliver \
  --timeout-seconds 1800 \
  --message "$WATCHDOG_MESSAGE"

# Remove a wake
openclaw cron remove <job-id>
```

If CLI fallback fails, persist runtime limitation and stop instead of continuing with a broken chain.

## 5. Script invocation examples

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

## 6. User-visible report templates

Routing rule: the coordinator sends these messages directly to `origin.report_to` via `message(action="send")`. User-visible text contains only user-meaningful content.

### Progress

```text
🔄 Round 3 | Loop: fix-rawdata-error

Milestone: dark mode done; tester handoff queued
• In progress: rawData.some error fix
Next: wait for tester verification
⏰ Next check: 2:09 PM
```

### Pause

```text
⏸️ Round 4 | Loop: refine-code

Reason: Claude quota suspension
Current: backend branch waiting to continue
Expected resume: 4:15 PM
⏰ Next check: 4:15 PM
```

### Resume

Resume reports may include `Reason:` when the committed state provides a meaningful resume note (for example quota recovery context). If no such note exists, omit the line.

```text
▶️ Round 4 | Loop: refine-code

Status: automatic iteration resumed
Reason: quota restored / coordinator recovered control
Current: backend branch resumed
Next: continue Round 4 development and verification
⏰ Next check: 4:24 PM
```

### Repair alert

Repair reports may include `Handled:` (Count>1)

```text
⚠️ Round 3 | Loop: round3

Status: coordinator wake chain repaired
Handled: repair count = 2
Next: resume coordinator polling
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
