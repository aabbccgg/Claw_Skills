#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
import yaml

ACTIVE = {"accepted", "running"}
TERMINAL = {"complete", "paused"}


def load_state(path: Path):
    text = path.read_text()
    m = re.search(r"```yaml\n(.*?)\n```", text, re.S)
    body = m.group(1) if m else text
    return yaml.safe_load(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state_path')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    state = load_state(Path(args.state_path).expanduser())
    errors, warnings = [], []

    status = state.get('status')
    progress = state.get('progress', {}) or {}
    coord = state.get('coordination', {}) or {}
    cleanup = state.get('cleanup', {}) or {}
    resume = state.get('resume', {}) or {}
    loops = state.get('loops', []) or []
    subs = state.get('subagents', []) or []
    active_workers = [s for s in subs if s.get('status') in ACTIVE]

    if status == 'awaiting-review' and not active_workers:
        errors.append('awaiting-review requires at least one active worker')
    if status == 'complete' and active_workers:
        errors.append('complete must not have active workers')
    if status == 'complete' and not cleanup.get('wake_cleanup_complete'):
        errors.append('complete requires wake_cleanup_complete=true')
    if cleanup.get('terminal_report_sent') and status not in TERMINAL:
        errors.append('terminal_report_sent=true requires terminal status')
    if status in {'running', 'awaiting-review'}:
        if not coord.get('current_wake_job_id'):
            errors.append('non-terminal workflow requires current_wake_job_id')
        if not coord.get('next_expected_wake_at'):
            errors.append('non-terminal workflow requires next_expected_wake_at')
    if coord.get('alert_needed') and cleanup.get('terminal_report_sent'):
        warnings.append('alert_needed true after terminal report sent')
    if status == 'paused' and resume.get('mode') == 'none':
        warnings.append('paused state has no resume metadata')
    if cleanup.get('wake_cleanup_complete') and not cleanup.get('terminal_report_sent') and not coord.get('watchdog_job_id'):
        errors.append('final report retry path requires watchdog while terminal_report_sent=false')

    # Detect no-dispatch/no-reschedule style failed cycles.
    if status == 'running' and not active_workers and coord.get('pending_transition') == 'idle' and (progress.get('in_progress_items') or []):
        errors.append('running state with in-progress items requires active worker or non-idle transition')

    # Repair verification completeness.
    if coord.get('alert_needed'):
        if not coord.get('current_wake_job_id'):
            errors.append('repair verification incomplete: missing replacement current_wake_job_id')
        if not coord.get('next_expected_wake_at'):
            errors.append('repair verification incomplete: missing refreshed next_expected_wake_at')

    if state.get('loops_mode') == 'sequential':
        top = [loop for loop in loops if not loop.get('parent')]
        incomplete = [loop for loop in top if loop.get('status') != 'complete']
        if len(incomplete) > 1:
            current_ids = progress.get('active_loop_ids') or []
            if current_ids and current_ids[0] != incomplete[0].get('id'):
                errors.append('sequential mode active_loop_ids must point to first incomplete top-level loop')

    loop_map = {loop.get('id'): loop for loop in loops}
    for loop in loops:
        parent = loop.get('parent')
        if parent and loop.get('status') in {'pending', 'running'}:
            p = loop_map.get(parent)
            if p and p.get('status') == 'complete':
                warnings.append(f'nested loop {loop.get("id")} active under complete parent {parent}')
            if p and p.get('current_func') not in {loop.get('id'), None}:
                warnings.append(f'nested loop {loop.get("id")} active while parent {parent} current_func moved beyond child boundary')

        branches = loop.get('branches') or []
        merge_policy = loop.get('merge_policy')
        completed = [b for b in branches if b.get('status') == 'complete']
        active_branch_ids = [b.get('branch_id') for b in branches if b.get('status') in {'pending', 'running'}]
        if merge_policy == 'all-success' and loop.get('status') == 'complete' and branches and len(completed) != len(branches):
            errors.append(f'loop {loop.get("id")} complete without all-success branch completion')
        if merge_policy == 'quorum' and loop.get('status') == 'complete' and branches and len(completed) < max(1, (len(branches)//2) + (len(branches)%2)):
            errors.append(f'loop {loop.get("id")} complete without quorum branch completion')
        if merge_policy == 'custom-user-criterion' and loop.get('status') == 'complete':
            warnings.append(f'loop {loop.get("id")} complete under custom-user-criterion; ensure explicit user criterion was satisfied')

        for bid in active_branch_ids:
            count = sum(1 for s in subs if s.get('loop_id') == loop.get('id') and s.get('branch_id') == bid and s.get('status') in ACTIVE)
            if count > 1:
                errors.append(f'loop {loop.get("id")} branch {bid} has multiple active workers')

    if state.get('execution_mode') == 'existing-agent':
        bad = [s for s in subs if s.get('run_id') not in {None} and not isinstance(s.get('run_id'), str)]
        if bad:
            errors.append('existing-agent mode allows run_id null or string only')

    result = {'ok': not errors, 'errors': errors, 'warnings': warnings}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result['ok']:
            print('OK')
            for w in warnings:
                print(f'! {w}')
        else:
            print('INVALID')
            for e in errors:
                print(f'- {e}')
            for w in warnings:
                print(f'! {w}')
    sys.exit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
