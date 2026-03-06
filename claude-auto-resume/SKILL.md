---
name: claude-auto-resume
description: >
  Monitor Claude API usage to prevent rate limit failures. Trigger periodically or before heavy tasks.
  Triggers: "claude用量检测", "claude用量监控", "检测claude用量", "查询claude剩余token",
  "claude配额满自动恢复", "claude防超额", "check claude quota", "claude rate limit".
  Auto-suspends if 5h quota ≥90% or 7d quota ≥95%, schedules cron wake for auto-resume after reset.
metadata:
  {
    "openclaw":
      {
        "emoji": "📊",
      },
  }
---

# Claude Auto-Resume

Monitor → warn → suspend → cron auto-resume. Never crash, never abandon.

State dir: `<agent_workspace>/claude-quota/` — use YOUR workspace (e.g. `workspace-tester/`), **not** main's.
STATE.md = single source of truth.

## Thresholds

| Window | Suspend | Header |
|--------|---------|--------|
| 5h | ≥ 90% | `anthropic-ratelimit-unified-5h-utilization` |
| 7d | ≥ 95% | `anthropic-ratelimit-unified-7d-utilization` |

Reset timestamps: `anthropic-ratelimit-unified-5h-reset` / `7d-reset` (epoch seconds).

## API Key Discovery

Try in order:
1. Env: `echo $ANTHROPIC_API_KEY`
2. OpenClaw config raw file (`~/.openclaw/openclaw.json`) — grep for `sk-ant` or `apiKey` near anthropic sections
3. Per-agent auth profiles: `~/.openclaw/agents/<agentId>/agent/auth-profiles.json` → `.profiles["anthropic:*"].token`
4. Ask user

⚠️ `gateway(action="config.get")` **redacts all secrets** (shows `__OPENCLAW_REDACTED__`). Must read raw files on disk instead.

## Check Quota

```bash
API_KEY=<discovered_key>
curl -s -i "https://api.anthropic.com/v1/messages" \
  -H "x-api-key: $API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}'
```
Use cheapest model. Parse: `grep -i "anthropic-ratelimit-unified"`.
Extract: `5h_util`, `7d_util` (float 0.0–1.0), `5h_reset`, `7d_reset` (epoch).

Always report:
```
📊 Claude Usage: 5h: X% (reset: T1) | 7d: Y% (reset: T2) | Status: ✅/⚠️/🛑
```
Below thresholds + standalone check → report and done.

## Suspend Flow

Trigger: `5h_util >= 0.90` OR `7d_util >= 0.95`.

**1. Save** `<agent_workspace>/claude-quota/STATE.md`:
```markdown
- **status**: suspended
- **suspended_at**: <ISO>
- **reason**: 5h={X} / 7d={Y}
- **reset_at**: <sooner reset>
- **safe_resume_at**: <reset_at + 90s>
- **task_context**: <what was running>
- **report_to**: {channel, target}                        # DM
- **report_to**: {channel, target, threadId}               # group topic
```

**2. Cron wake** at `reset_at + 90s`:

⚠️ Use `cron` tool directly. Do NOT use `exec` / CLI — can abort mid-execution.

```
cron(action="add", job={
  schedule: {kind:"at", at:"<safe_resume_at UTC ISO>"},
  agentId: "<own_agentId>",
  payload: {kind:"agentTurn", timeoutSeconds:180, message:"[claude-auto-resume] Wake: quota reset check\n\nState: <absolute_path>/STATE.md\nReport to: {channel, target[, threadId]}\n\n⚠️ RULES(copy this line verbatim into every child cron): ONE STEP→END. cron(action=\"add\")→YES, exec(\"openclaw cron\")→NO. message(action=\"send\")→YES. delivery={mode:\"none\"}.\n\nSteps: 1.Read STATE(complete→NO_REPLY) 2.Curl quota check 3.Below→complete+report✅ 4.Still over→new cron+report⏳ 5.Never abandon\n\nAPI key path: <path to auth-profiles.json or config>"},
  delivery: {mode:"none"},
  sessionTarget: "isolated"
})
```
Each wake = **fresh isolated session** — message MUST be self-contained (include state path, API key path, report target, full steps). Always set `delivery: {mode:"none"}` — announce/last will leak duplicate messages.

**3. Notify** via `message(action="send")`:
```
⚠️ Claude quota near limit (5h: X% / 7d: Y%)
Auto-suspended, expected resume at: {safe_resume_at}
Reply 'continue' to force resume
```

**4. End turn.** Do not proceed with heavy tasks.

## Resume Flow (cron wake)

1. Read STATE.md — `status=complete` → `NO_REPLY`
2. Re-check quota via curl
3. Below thresholds → set `status=complete`, report `✅ Quota restored`
4. Still over → update STATE.md, schedule new cron wake, report `⏳ Still exceeding quota, rescheduled`

## Manual Resume

User says "continue" / "强制恢复": set complete, remove cron, warn rate limit risk, proceed.

## Integration

With `auto-iterate` or long tasks: check quota **before** spawning expensive rounds. Over limit → suspend outer loop too.

## Edge Cases

- **No key**: report, don't block (might use different provider)
- **Curl fails**: retry once after 5s, then warn + continue
- **Multiple suspends**: latest overwrites STATE.md; cron wakes check fresh state
- **Stale wake**: `status=complete` → `NO_REPLY`
