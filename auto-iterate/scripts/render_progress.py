#!/usr/bin/env python3
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
import yaml


def load_yaml(path: Path):
    text = path.read_text()
    m = re.search(r"```yaml\n(.*?)\n```", text, re.S)
    body = m.group(1) if m else text
    return yaml.safe_load(body)


def parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v.endswith('Z'):
        v = v[:-1] + '+00:00'
    return datetime.fromisoformat(v)


def fmt_local(dt):
    if not dt:
        return None
    return dt.astimezone().strftime('%-I:%M %p')


def human_delta(a, b):
    if not a or not b:
        return None
    secs = max(0, int((b - a).total_seconds()))
    h, rem = divmod(secs, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f'~{h}h{m:02d}m'
    return f'~{m}m'


def status_icon(status):
    return {
        'accepted': '🔄', 'running': '🔄', 'success': '✅', 'no-change': '✅',
        'blocked': '⏸️', 'failed': '❌', 'timed-out': '❌', 'stalled': '⚠️',
    }.get(status, '🔄')


def status_text(status):
    return {
        'accepted': 'Accepted', 'running': 'Running', 'success': 'Completed',
        'no-change': 'Completed (no change)', 'blocked': 'Blocked', 'failed': 'Failed',
        'timed-out': 'Timed out', 'stalled': 'Stalled',
    }.get(status, status or 'Running')


def pick_loop_label(state):
    active = ((state.get('progress') or {}).get('active_loop_ids') or [])
    if active:
        return ', '.join(active)
    return state.get('current') or 'current-loop'


def pick_mode(state, explicit=None):
    if explicit:
        return explicit
    status = state.get('status')
    cleanup = state.get('cleanup', {}) or {}
    coord = state.get('coordination', {}) or {}
    if cleanup.get('terminal_report_sent') or status == 'complete':
        return 'final'
    if coord.get('alert_needed'):
        return 'repair'
    if status == 'paused':
        return 'pause'
    return 'progress'


def worker_lines(state, limit=3):
    subs = state.get('subagents', []) or []
    if not subs:
        current = state.get('current') or 'orchestration cycle'
        return ['Coordinator 🔄 Running', f'• Current: {current}']
    active_first = sorted(
        subs,
        key=lambda s: (
            s.get('status') not in {'accepted', 'running'},
            s.get('branch_id') or '',
            s.get('loop_id') or '',
        ),
    )
    lines = []
    for sub in active_first[:limit]:
        label = sub.get('branch_id') or sub.get('loop_id') or 'Worker'
        lines.append(f"{label} {status_icon(sub.get('status'))} {status_text(sub.get('status'))}")
        summary = sub.get('summary')
        if summary:
            lines.append(f"• {summary}")
    return lines


def header(icon, state, now):
    return f"{icon} [auto-iterate] Round {state.get('round', '?')} | Loop: {pick_loop_label(state)} ({fmt_local(now)})"


def footer(state, now):
    coord = state.get('coordination', {}) or {}
    deadline = parse_dt(state.get('workflow_deadline_at'))
    next_check = parse_dt(coord.get('next_expected_wake_at'))
    out = []
    if next_check:
        out.append(f"⏰ Next check: {fmt_local(next_check)}")
    rem = human_delta(now, deadline)
    if rem and deadline:
        out.append(f"📊 Time remaining: {rem} (deadline {fmt_local(deadline)})")
    return out


def extend_items(lines, label, items, limit=4):
    if items:
        lines.append(f"• {label}: {', '.join(items[:limit])}")


def render_progress(state, now):
    progress = state.get('progress', {}) or {}
    lines = [header('🔄', state, now), '']
    lines.extend(worker_lines(state))
    extend_items(lines, 'Completed', progress.get('completed_items') or [])
    extend_items(lines, 'In progress', progress.get('in_progress_items') or [])
    if progress.get('test_summary'):
        lines.append(f"• Tests: {progress['test_summary']}")
    if progress.get('commit_refs'):
        lines.append(f"• Commits: {' → '.join(progress['commit_refs'][:4])}")
    lines.append('')
    lines.append(f"Next: {state.get('current') or 'continue current iteration flow'}")
    lines.extend(footer(state, now))
    if progress.get('last_failure_reason'):
        lines.append(f"Note: {progress['last_failure_reason']}")
    return '\n'.join(lines)


def render_pause(state, now):
    resume = state.get('resume', {}) or {}
    progress = state.get('progress', {}) or {}
    lines = [header('⏸️', state, now), '']
    lines.append(f"Reason: {resume.get('blocked_by') or 'paused'}")
    if resume.get('note'):
        lines.append(f"Note: {resume['note']}")
    resume_at = parse_dt(resume.get('resume_at'))
    if resume_at:
        lines.append(f"Expected resume: {fmt_local(resume_at)}")
    if progress.get('last_subagent_result'):
        lines.append(f"Current progress: {progress['last_subagent_result']}")
    extend_items(lines, 'Completed', progress.get('completed_items') or [])
    lines.append('')
    lines.extend(footer(state, now))
    return '\n'.join(lines)


def render_resume(state, now):
    progress = state.get('progress', {}) or {}
    lines = [header('▶️', state, now), '']
    lines.append('Status: automatic iteration resumed')
    if progress.get('last_subagent_result'):
        lines.append(f"Current progress: {progress['last_subagent_result']}")
    extend_items(lines, 'Completed', progress.get('completed_items') or [])
    lines.append('')
    lines.append(f"Next: {state.get('current') or 'continue current iteration flow'}")
    lines.extend(footer(state, now))
    return '\n'.join(lines)


def render_repair(state, now):
    coord = state.get('coordination', {}) or {}
    lines = [header('⚠️', state, now), '']
    lines.append('Status: watchdog repaired the coordinator chain')
    lines.append(f"Handled: repair count = {coord.get('watchdog_tripped_count', 0)}")
    lines.append('Impact: iteration state was preserved and will continue from the latest committed STATE')
    lines.append('')
    lines.append(f"Next: {state.get('current') or 'resume coordinator polling'}")
    lines.extend(footer(state, now))
    return '\n'.join(lines)


def render_final(state, now):
    progress = state.get('progress', {}) or {}
    cleanup = state.get('cleanup', {}) or {}
    loops = state.get('loops', []) or []
    lines = [header('✅', state, now), '']
    lines.append(f"Completed {state.get('round', '?')} rounds and {len(loops)} loop(s)")
    if progress.get('last_subagent_result'):
        lines.append(f"• Final result: {progress['last_subagent_result']}")
    extend_items(lines, 'Completed', progress.get('completed_items') or [])
    if progress.get('commit_refs'):
        lines.append(f"• Commits: {' → '.join(progress['commit_refs'][:4])}")
    if progress.get('test_summary'):
        lines.append(f"• Tests: {progress['test_summary']}")
    lines.append(f"• Cleanup: wake cleanup={'done' if cleanup.get('wake_cleanup_complete') else 'pending'}, report={'sent' if cleanup.get('terminal_report_sent') else 'pending'}")
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state_path')
    ap.add_argument('--mode', choices=['progress', 'pause', 'resume', 'repair', 'final'])
    args = ap.parse_args()
    state = load_yaml(Path(args.state_path).expanduser())
    now = datetime.now(timezone.utc)
    mode = pick_mode(state, args.mode)
    text = {
        'progress': render_progress,
        'pause': render_pause,
        'resume': render_resume,
        'repair': render_repair,
        'final': render_final,
    }[mode](state, now)
    print(text)


if __name__ == '__main__':
    main()
