---
name: claude-auto-resume
description: Monitor Claude usage to prevent rate limit failures. Trigger this skill periodically or before heavy tasks, or when asked "claude用量检测", "claude用量监控", "检测claude用量", "查询claude剩余token", "claude配额满自动恢复", "claude防超额" etc. Automatically suspends execution if 5h quota is >=95% or 7d quota is >=98% utilized, waiting for reset (Pro/Web accounts) or user recharge (API Tokens).
---

# Claude Auto-Resume & Rate Limit Management

This skill instructs the agent on how to manage Claude's usage limits dynamically, ensuring long-running tasks do not fail abruptly due to rate limits or insufficient balance. 

Depending on the credential type being used, the agent MUST follow these specific quota-handling rules whenever usage is checked or a rate limit is approaching:

**Monitoring Strategy**:
Send a minimal-cost request to check real-time rate limit headers:
```bash
# You MUST replace <PROVIDER_URL> with the actual API base URL (Default: https://api.anthropic.com)
# You MUST replace <MODEL_NAME> with the specific Claude model being used.
curl -s -i "<PROVIDER_URL>/v1/messages" \
  -H "x-api-key: $YOUR_API_TOKEN" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model": "<MODEL_NAME>", "max_tokens": 1, "messages": [{"role": "user", "content": "Ping"}]}'
```

Parse the following `unified` HTTP headers:
- `anthropic-ratelimit-unified-5h-utilization` (value like `0.95` means 95%)
- `anthropic-ratelimit-unified-7d-utilization` (value like `0.98` means 98%)
- `anthropic-ratelimit-unified-5h-reset` (timestamp of when the 5h limit resets)
- `anthropic-ratelimit-unified-7d-reset` (timestamp of when the 7d limit resets)

**Action Rule: Default Suspend, Auto-Resume via Cron Wake, and Allow Manual Resume**
If the 5h utilization percentage reaches **95%**, or the 7d utilization percentage reaches **98%**:
1. Immediately **pause the current task** and save your current task state to a `STATE.md` working file so it can be resumed later.
2. Extract the exact **Reset time** corresponding to the exhausted limit (`anthropic-ratelimit-unified-*-reset` timestamp in UNIX epoch seconds). **Then add a safety margin of 60 to 120 seconds** (1-2 minutes) to this timestamp to ensure the quota has fully refreshed before waking up. Let's call this `Safe_Reset_Time`.
3. Configure a system cron wake to schedule an automatic resumption exactly at this buffered time. You MUST explicitly use the `run_command` tool to add a cron job via the `openclaw` CLI or the appropriate internal scheduling command (e.g., `openclaw cron add --time "<Safe_Reset_Time>" --message "Quota refreshed. Resume task: claude-auto-resume"`). This ensures the task recovers without user intervention once quotas are safely refreshed.
4. Send a notification to the user stating: "⚠️ API rate limit reached a critical threshold (5h >= 95% or 7d >= 98%). The task is automatically suspended until the quota resets. You can explicitly reply with **'continue'** to bypass this and force-resume the task immediately."
5. Enter a blocked state (using `notify_user` with `BlockedOnUser: true`) securely waiting. The agent will either be woken up automatically by the Cron trigger at `<Safe_Reset_Time>`, or manually by the user typing "continue".

---
**CRITICAL**: The fundamental purpose of this skill is to ensure continuous execution without hard crashes. Never abandon a task simply because a limit was reached—always fallback to explicit cron-waking or user prompting as defined above.
