---
name: claude-auto-resume
description: >
  Monitor Claude API usage to prevent rate limit failures. Trigger periodically or before heavy tasks.
  Triggers: "claude用量检测", "claude用量监控", "检测claude用量", "查询claude剩余token",
  "claude配额满自动恢复", "claude防超额", "check claude quota", "claude rate limit".
  Auto-suspends if 5h quota ≥95% or 7d quota ≥98%, schedules cron wake for auto-resume after reset.
---

# Claude Auto-Resume

**Goal**: Prevent hard crashes from rate limits. Monitor → warn → suspend → auto-resume.

State dir: `~/.openclaw/workspace/claude-quota/`.
STATE.md = single source of truth for suspended tasks.

## Thresholds

| Window | Suspend | Header |
|--------|---------|--------|
| 5h | ≥ 95% | `anthropic-ratelimit-unified-5h-utilization` |
| 7d | ≥ 98% | `anthropic-ratelimit-unified-7d-utilization` |

Reset timestamps from: `anthropic-ratelimit-unified-5h-reset` / `anthropic-ratelimit-unified-7d-reset`.

## API Key Discovery

Try in order — use the first that works:
1. `exec`: `echo $ANTHROPIC_API_KEY`
2. `gateway(action="config.get")` → look for anthropic key in provider config
3. Ask user

## Check Quota

```bash
curl -s -i "https://api.anthropic.com/v1/messages" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model": "claude-sonnet-4-20250514", "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}'
```

Use cheapest model available for the ping. Parse response headers via `grep -i "anthropic-ratelimit-unified"`.

### Parse Result

Extract these four values:
- `5h_util` — float (0.0–1.0)
- `7d_util` — float (0.0–1.0)
- `5h_reset` — ISO timestamp or epoch
- `7d_reset` — ISO timestamp or epoch

## Report (always)

After parsing, report current status to user:

```
📊 Claude 用量:
• 5h: {5h_util*100}% (reset: {5h_reset})
• 7d: {7d_util*100}% (reset: {7d_reset})
• Status: ✅ OK / ⚠️ Approaching limit / 🛑 Suspended
```

If called as standalone check (no running task) and below thresholds → report and done.

## Suspend Flow

If `5h_util >= 0.95` OR `7d_util >= 0.98`:

### 1. Save State

Create `~/.openclaw/workspace/claude-quota/STATE.md`:
```markdown
# Claude Quota Suspend State
- **status**: suspended
- **suspended_at**: <ISO timestamp>
- **reason**: 5h={5h_util} / 7d={7d_util}
- **reset_at**: <whichever reset is sooner>
- **safe_resume_at**: <reset_at + 90s>
- **task_context**: <what was being done, if any>
- **report_to**: {channel: "<channel>", target: "<chat_id>", threadId: "<topic_id>"}
```

### 2. Schedule Cron Wake

⚠️ Use the `cron` tool directly. Do NOT use `exec` / CLI.

Compute safe resume time: `reset_at + 90 seconds` (safety margin).

```
cron(action="add", job={
  schedule: {kind: "at", at: "<safe_resume_at UTC ISO>"},
  agentId: "<own_agentId>",
  payload: {kind: "agentTurn", message: "[claude-auto-resume] Wake: quota reset check\n\nState: ~/.openclaw/workspace/claude-quota/STATE.md\nReport to: {channel, target, threadId}\n\nSteps:\n1. Read STATE.md (if status=complete → NO_REPLY)\n2. Re-run quota check (curl)\n3. If below thresholds → set status=complete, report ✅ to user\n4. If still over → update STATE.md, schedule new cron wake with next reset+90s\n5. Never abandon — always reschedule or complete"},
  sessionTarget: "isolated"
})
```

Each cron wake = **fresh isolated session** — message MUST be self-contained.

### 3. Notify User

Use `message(action="send")` for notification:

```
⚠️ Claude 配额接近上限:
• 5h: {5h_util*100}% / 7d: {7d_util*100}%
• 已自动暂停任务，等待配额重置
• 预计恢复时间: {safe_resume_at}
• 回复 **continue** 可强制恢复（可能导致请求失败）
```

### 4. Stop current execution

Do not proceed with any heavy task. End turn.

## Resume Flow (cron wake)

On cron wake:
1. Read STATE.md — if `status=complete` → `NO_REPLY`
2. Re-check quota via curl
3. **Below thresholds**: set `status=complete` in STATE.md → report to user: `✅ Claude 配额已恢复，可以继续工作`
4. **Still over**: update STATE.md with new reset times → schedule another cron wake → report: `⏳ 配额仍未恢复，已重新调度，预计 {new_safe_resume_at}`

## Manual Resume

If user says "continue" / "强制恢复" / "force resume" while suspended:
1. Set STATE.md `status=complete`
2. Remove pending cron job if possible
3. Warn user: rate limit errors may occur
4. Proceed with task

## Integration with Other Skills

When used alongside `auto-iterate` or long-running tasks:
- Check quota **before** spawning expensive subagent rounds
- If approaching limits, suspend the outer loop too (save its state)
- On resume, restore outer loop state and continue

## Edge Cases

- **No API key found**: Report to user, do not block — they may be using a different provider/proxy
- **Curl fails**: Retry once after 5s. If still fails, warn user and continue (non-blocking)
- **Multiple suspends**: Only one STATE.md — latest suspend overwrites. Cron wakes check fresh state
- **Already complete on wake**: Stale wake → `NO_REPLY`, do nothing
