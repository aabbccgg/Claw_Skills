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

### During subagent execution (polling)

```text
🔄 [auto-iterate] Round 3 | Loop: fix-rawdata-error (14:03 PM)

Developer 🔄 正在修复中
• 已完成: 深色模式 ✅, 管理员白名单 ✅
• 进行中: rawData.some 错误修复

下一步: 等待 developer 完成后交给 tester
⏰ 下次检查: 14:09 PM
📊 剩余时间: ~1h45m (deadline 15:48)
```

### After subagent completion + advancing

```text
🔄 [auto-iterate] Round 2 (12:03 PM)

Developer ✅ 已完成并提交 (ae9dca7)
• Dashboard: gain/loss CSS classes、3Y 周期、defaultPeriod
• Watchlist: 批量价格获取、价格列、EmptyState、搜索面板折叠
• tsc ✅ | pytest 97 pass ✅

Tester 🔄 已分派 R2 验证任务，正在执行…

⏰ 下次检查: 12:11 PM
📊 剩余时间: ~2h15m (deadline 14:18)
```

### Template fields (required)

| Field | Source |
|-------|--------|
| Header | `🔄 [auto-iterate] Round {round}` + optional `Loop: {loop_id}` + `({HH:MM} local)` |
| Actor lines | One per subagent/role. Use ✅ done, 🔄 running, ❌ failed, ⏸️ paused |
| Bullet details | Commit hash, specific changes, test results — keep concise |
| 下一步 | The decided next action from DECIDE step |
| ⏰ 下次检查 | `next_expected_wake_at` in user's local time |
| 📊 剩余时间 | `workflow_deadline_at - now`, with deadline time shown |

### Pause

```text
⏸️ [auto-iterate] Round 4 | Loop: refine-code (15:30 PM)

原因: Claude 用量超限自动暂停
预计恢复: 16:15 PM (quota reset + 90s)
当前进度: 3/5 loops done, backend branch 等待恢复后继续

📊 剩余时间: ~18m (deadline 15:48)
```

### Final completion

```text
✅ [auto-iterate] 完成! (15:42 PM)

共 4 轮迭代, 6 branches 全部通过
• 核心修复: serializer、migration、dark mode
• 测试: 97 pass ✅, 0 fail
• 提交: ae9dca7 → f3b1c02

已清理: coordinator wake + watchdog + 1 pending cleanup
总耗时: 2h40m
```

---

## 6. Telegram routing examples

DM:

```json
{"channel":"telegram","target":"12345678"}
```

Group topic:

```json
{"channel":"telegram","target":"-1009876543210","threadId":"42"}
```
