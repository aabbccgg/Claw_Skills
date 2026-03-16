# Canonical examples

## 1. Coordinator wake cron.add payload

Compute the coordinator next-poll delay first with `python3 scripts/compute_next_poll.py --state-path /abs/path/STATE.md --json`, then fill the successor wake time dynamically.

```json
{
  "action": "add",
  "job": {
    "name": "auto-iterate-coordinator-wake",
    "schedule": {"kind": "at", "at": "<computed-successor-wake-at-iso>"},
    "agentId": "<own_agent_id>",
    "payload": {
      "kind": "agentTurn",
      "timeoutSeconds": 1800,
      "message": "[auto-iterate] coordinator wake\nIteration: <iteration_id>\nRound: <round>\nStatus: running|awaiting-result|paused|complete\nState path: /abs/path/STATE.md\nWorkdir: /abs/workdir\nCurrent loop: <loop_id|none>\nCurrent branch: <branch_id|none>\nSubagents: <active_subagent_refs|[]>\nCurrent wake id: <current_wake_job_id|pending>\nNext action: dispatch|poll|ingest|repair|pause|complete\nReport_to: {channel: <channel>, target: \"<target>\", threadId: \"<thread_id_or_omit>\"}\n⚠️ RULES: ONE CYCLE->END. Native cron first; use exec+openclaw cron only as explicit fallback. Commit state before report. Heavy work stays in worker."
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
Iteration: <iteration_id>
Loop: <loop_id>
Branch: <branch_id>
State path: /abs/path/STATE.md (read-only)
Workdir: /abs/workdir
Target: <exit_condition|branch_goal>
Return YAML envelope:
- status: success|no-change|blocked|failed
- summary: short text
- artifacts: [paths]
- criteria_assessment: met|not-met|unclear
- next_action_hint: spawn|advance|pause|complete|retry
Do not edit orchestration state. Do not schedule cron.
```


## 3a. Agent-profile reuse example

When the user provides an agent identifier, agent name, or profile-like agent reference for a worker role, resolve that profile first and still spawn a fresh isolated worker. Do not reuse a live session.

```text
User instruction: use agent "developer" for the developer role
Step 1: call agents_list and save the JSON result
Step 2: run `python3 scripts/resolve_agent_profile.py --requested developer --agents-json /tmp/agents.json --json`
Expected resolver result:
- matchedProfile: developer
- spawnable: true
- spawnAgentId: developer
- expectedPrimaryModel: anthropic/claude-opus-4-6
Dispatch action: sessions_spawn(runtime=subagent, agentId="developer", mode=run, ...)
Execution mode: spawned-worker
Persist after dispatch:
- requested_agent_profile: developer
- expected_primary_model: anthropic/claude-opus-4-6
- effective_model: anthropic/claude-opus-4-6
Rule: reuse the matched static agent profile only; do not inherit live session history. If the worker actually runs on a different model, persist `model_fallback_reason` instead of silently ignoring the mismatch.
```

## 4. CLI cron fallback examples

Cron path is native first, CLI fallback second. Use these only when the native `cron` tool is unavailable but `exec` can run `openclaw cron ...`. Compute the coordinator next-poll delay first with `python3 scripts/compute_next_poll.py --state-path /abs/path/STATE.md --json`, then fill the successor wake time dynamically. The flags below match the current OpenClaw CLI shape (`openclaw cron add --help`).

```bash
# Add one-shot coordinator wake
WAKE_MESSAGE="$(cat /abs/path/wake-message.txt)"
openclaw cron add \
  --name auto-iterate-coordinator-wake \
  --at <computed-successor-wake-at-iso> \
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
🔄 Round 3 | Loop: fix-rawdata-error (2:09 PM)

Milestone (milestone): dark mode done; tester handoff queued

Worker 🔄 Accepted
• In progress: tester verification is running for commit 5d31ffe

Next: wait for tester verification
⏰ Next check: 2:09 PM
```

### Pause

```text
⏸️ Round 4 | Loop: refine-code (4:15 PM)

Reason: Claude quota suspension
Current: backend branch waiting to continue
Expected resume: 4:15 PM
⏰ Next check: 4:15 PM
```

### Resume

Resume reports may include `Reason:` when the committed state provides a meaningful resume note (for example quota recovery context). If no such note exists, omit the line.

```text
▶️ Round 4 | Loop: refine-code (4:24 PM)

Status: automatic iteration resumed
Reason: quota restored
Current: resumed after quota reset
Next: continue branch after quota restore
⏰ Next check: 4:24 PM
```

### Repair alert

Repair reports may include `Handled:` (Count>1)

```text
⚠️ Round 3 | Loop: round3 (2:28 PM)

Status: coordinator wake chain repaired
Handled: repair count = 2
Next: resume coordinator polling
⏰ Next check: 2:28 PM
```

### Final completion

```text
✅ Round 4 | Loop: final-report (3:42 PM)

Completed 4 rounds and 6 loop(s)
• Final result: all checks passed
• Completed: serializer, migration, dark mode
• Commits: ae9dca7 → f3b1c02
• Tests: 97 passed
• Cleanup: wake cleanup=done, report=sent
```
