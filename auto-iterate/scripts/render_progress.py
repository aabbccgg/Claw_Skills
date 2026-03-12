#!/usr/bin/env python3
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
import yaml


ACTIVE_WORKER_STATUSES = {"accepted", "running"}


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
        'accepted': '🔄', 'running': '🏃', 'success': '✅', 'no-change': '✅',
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


def format_pause_reason(blocked_by):
    return {
        'claude-quota': 'Claude quota suspension',
        'user-input': 'User input required',
        'repair-failed': 'Repair failed',
        'none': 'paused',
        None: 'paused',
    }.get(blocked_by, str(blocked_by or 'paused'))


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


def pick_primary_worker(state):
    subs = state.get('subagents', []) or []
    active_subs = [sub for sub in subs if sub.get('status') in ACTIVE_WORKER_STATUSES]
    if not active_subs:
        return None
    ordered = sorted(active_subs, key=lambda s: (s.get('started_at') or '', s.get('child_session_key') or ''))
    primary = ordered[0]
    summary = str(primary.get('summary') or '').strip()
    if not summary:
        summary = None
    return {
        'status': primary.get('status') or 'running',
        'icon': status_icon(primary.get('status')),
        'status_text': status_text(primary.get('status')),
        'summary': summary,
    }


def header(icon, state, now):
    return f"{icon} Round {state.get('round', '?')} | Loop: {pick_loop_label(state)} ({fmt_local(now)})"


def footer(state, now):
    del now
    coord = state.get('coordination', {}) or {}
    next_check = parse_dt(coord.get('next_expected_wake_at'))
    out = []
    if next_check:
        out.append(f"⏰ Next check: {fmt_local(next_check)}")
    return out


def extend_items(lines, label, items, limit=4):
    if items:
        lines.append(f"• {label}: {', '.join(items[:limit])}")


def pick_pending_report(progress, allowed_types=None):
    pending_reports = progress.get('pending_reports') or []
    allowed = set(allowed_types) if allowed_types else None
    for item in pending_reports:
        if not isinstance(item, dict):
            continue
        kind = item.get('type', 'milestone')
        summary = item.get('summary') or item.get('key')
        if not summary:
            continue
        if allowed and kind not in allowed:
            continue
        return {'type': kind, 'summary': summary}
    return None


def render_pending_milestone(progress, allowed_types=None):
    item = pick_pending_report(progress, allowed_types)
    if not item:
        return None
    return f"Milestone ({item['type']}): {item['summary']}"


def pick_current_line(state):
    progress = state.get('progress', {}) or {}
    if progress.get('last_subagent_result'):
        return str(progress['last_subagent_result']).strip().rstrip('.')
    worker = pick_primary_worker(state)
    if worker and worker.get('summary'):
        return worker['summary'].rstrip('.')
    in_progress = progress.get('in_progress_items') or []
    if in_progress:
        return str(in_progress[0]).strip().rstrip('.')
    if state.get('current'):
        return str(state['current']).strip().rstrip('.')
    return None


def pick_in_progress_line(state):
    progress = state.get('progress', {}) or {}
    worker = pick_primary_worker(state)
    if worker and worker.get('summary'):
        return worker['summary'].rstrip('.')
    in_progress = progress.get('in_progress_items') or []
    if in_progress:
        return str(in_progress[0]).strip().rstrip('.')
    return None


def render_progress(state, now):
    progress = state.get('progress', {}) or {}
    lines = [header('🔄', state, now), '']
    milestone = render_pending_milestone(progress, {'milestone', 'progress'})
    if milestone:
        lines.append(milestone)
        lines.append('')
    worker = pick_primary_worker(state)
    if worker:
        lines.append(f"Worker {worker['icon']} {worker['status_text']}")
    in_progress = pick_in_progress_line(state)
    if in_progress:
        lines.append(f"• In progress: {in_progress}")
    lines.append('')
    lines.append(f"Next: {state.get('current') or 'continue current iteration flow'}")
    lines.extend(footer(state, now))
    return '\n'.join(lines)


def render_pause(state, now):
    resume = state.get('resume', {}) or {}
    progress = state.get('progress', {}) or {}
    lines = [header('⏸️', state, now), '']
    milestone = render_pending_milestone(progress, {'milestone', 'progress'})
    if milestone:
        lines.append(milestone)
        lines.append('')
    lines.append(f"Reason: {format_pause_reason(resume.get('blocked_by'))}")
    current = pick_current_line(state)
    if current:
        lines.append(f"Current: {current}")
    resume_at = parse_dt(resume.get('resume_at'))
    if resume_at:
        lines.append(f"Expected resume: {fmt_local(resume_at)}")
    lines.extend(footer(state, now))
    return '\n'.join(lines)


def render_resume(state, now):
    progress = state.get('progress', {}) or {}
    resume = state.get('resume', {}) or {}
    lines = [header('▶️', state, now), '']
    milestone = render_pending_milestone(progress, {'milestone', 'progress'})
    if milestone:
        lines.append(milestone)
        lines.append('')
    lines.append('Status: automatic iteration resumed')
    if resume.get('note'):
        lines.append(f"Reason: {resume['note']}")
    current = pick_current_line(state)
    if current:
        lines.append(f"Current: {current}")
    lines.append(f"Next: {state.get('current') or 'continue current iteration flow'}")
    lines.extend(footer(state, now))
    return '\n'.join(lines)


def render_repair(state, now):
    coord = state.get('coordination', {}) or {}
    lines = [header('⚠️', state, now), '']
    lines.append('Status: coordinator wake chain repaired')
    repair_count = coord.get('watchdog_tripped_count', 0)
    if repair_count > 1:
        lines.append(f"Handled: repair count = {repair_count}")
    lines.append(f"Next: {state.get('current') or 'resume coordinator polling'}")
    lines.extend(footer(state, now))
    return '\n'.join(lines)


def render_final(state, now):
    progress = state.get('progress', {}) or {}
    cleanup = state.get('cleanup', {}) or {}
    loops = state.get('loops', []) or []
    lines = [header('✅', state, now), '']
    milestone = render_pending_milestone(progress)
    if milestone:
        lines.append(milestone)
        lines.append('')
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
    ap = argparse.ArgumentParser(description='Render user-visible auto-iterate progress text from committed STATE.md.')
    ap.add_argument('state_path', help='Path to STATE.md (fenced YAML or raw YAML).')
    ap.add_argument('--mode', choices=['progress', 'pause', 'resume', 'repair', 'final'], help='Optional explicit render mode; default is inferred from state.')
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
