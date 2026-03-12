#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
import yaml

ALIAS_HINTS = {
    'spawn': 'worker-dispatched',
    'dispatch': 'worker-dispatched',
    'worker-spawned': 'worker-dispatched',
    'result-ingested': 'worker-result',
}

ALLOWED = {
    'running': {
        'worker-dispatched': ['awaiting-result'],
        'pause-requested': ['paused'],
        'quota-suspended': ['paused'],
        'dead-loop': ['paused'],
        'complete-requested': ['complete'],
        'repair-failed': ['paused'],
    },
    'awaiting-result': {
        'worker-result': ['running', 'paused', 'complete'],
        'worker-timeout': ['running', 'paused'],
        'worker-failed': ['running', 'paused'],
    },
    'paused': {
        'user-resume': ['running'],
        'quota-restored': ['running'],
    },
    'complete': {},
}


def load_state(path: Path):
    text = path.read_text()
    m = re.search(r"```yaml\n(.*?)\n```", text, re.S)
    body = m.group(1) if m else text
    return yaml.safe_load(body)


def invariant_errors(state, from_status, event, to_status):
    errors = []
    cleanup = state.get('cleanup', {}) or {}
    subs = state.get('subagents', []) or []
    progress = state.get('progress', {}) or {}
    resume = state.get('resume', {}) or {}

    if from_status == 'complete':
        errors.append('complete is terminal; no outbound transition allowed')
    if from_status == 'paused' and to_status == 'running' and event not in {'user-resume', 'quota-restored'}:
        errors.append('paused -> running requires explicit resume event')
    if from_status == 'awaiting-result' and event == 'worker-result' and to_status == 'awaiting-result':
        errors.append('awaiting-result must not remain awaiting-result after successful worker result ingestion')
    if to_status == 'complete':
        if not cleanup.get('wake_cleanup_complete'):
            errors.append('transition to complete requires cleanup.wake_cleanup_complete=true in terminal path')
        active = [s for s in subs if s.get('status') in {'accepted', 'running'}]
        if active:
            errors.append('cannot complete while active workers still running')
    if event == 'quota-suspended' and to_status != 'paused':
        errors.append('quota suspension must transition to paused')
    if event == 'quota-suspended' and (resume.get('mode') != 'quota-auto' or resume.get('blocked_by') != 'claude-quota'):
        errors.append('quota suspension requires resume.mode=quota-auto and resume.blocked_by=claude-quota')
    if event == 'dead-loop' and progress.get('no_fix_rounds_total', 0) < 3:
        errors.append('dead-loop event expects progress.no_fix_rounds_total >= 3 or equivalent branch stall evidence')
    return errors


def main():
    ap = argparse.ArgumentParser(description='Validate a candidate auto-iterate state transition using canonical event vocabulary.')
    ap.add_argument('state_path', help='Path to STATE.md (fenced YAML or raw YAML).')
    ap.add_argument('--event', required=True, help='Canonical transition event (for example: worker-dispatched, worker-result, dead-loop).')
    ap.add_argument('--to', dest='to_status', help='Candidate target status to validate.')
    ap.add_argument('--json', action='store_true', help='Emit machine-readable JSON result.')
    args = ap.parse_args()
    state = load_state(Path(args.state_path).expanduser())
    from_status = state.get('status')
    result = {'from': from_status, 'event': args.event, 'ok': True, 'errors': []}

    if args.event in ALIAS_HINTS:
        result['ok'] = False
        result['errors'].append(f"invalid event alias '{args.event}'; use '{ALIAS_HINTS[args.event]}'")
        result['allowedTargets'] = []
    else:
        allowed_targets = ALLOWED.get(from_status, {}).get(args.event, [])
        result['allowedTargets'] = allowed_targets
        if args.to_status:
            result['to'] = args.to_status
            if args.to_status not in allowed_targets:
                result['ok'] = False
                result['errors'].append(f'transition not allowed: {from_status} --{args.event}--> {args.to_status}')
            result['errors'].extend(invariant_errors(state, from_status, args.event, args.to_status))
            result['ok'] = result['ok'] and not result['errors']

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if args.to_status or result['errors']:
            print('OK' if result['ok'] else 'INVALID')
            for e in result['errors']:
                print(f'- {e}')
        else:
            print(' '.join(result.get('allowedTargets', [])))
    sys.exit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
