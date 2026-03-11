#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
import yaml


def load_state(path: Path):
    text = path.read_text()
    m = re.search(r"```yaml\n(.*?)\n```", text, re.S)
    body = m.group(1) if m else text
    return yaml.safe_load(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state_path')
    ap.add_argument('--threshold', type=int, default=3)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    state = load_state(Path(args.state_path).expanduser())
    progress = state.get('progress', {}) or {}
    loops = state.get('loops', []) or []
    findings = []
    reset_suggested = False

    meaningful_progress = bool(
        progress.get('completed_items')
        or progress.get('commit_refs')
        or progress.get('test_summary')
        or any((sub.get('status') == 'success' and sub.get('summary')) for sub in (state.get('subagents') or []))
    )

    last_result = (progress.get('last_subagent_result') or '').lower()
    if ('no-change' in last_result or 'no change' in last_result or 'unchanged' in last_result) and not meaningful_progress:
        findings.append({'scope': 'workflow', 'reason': 'last result indicates no meaningful change', 'value': progress.get('last_subagent_result')})

    if meaningful_progress and progress.get('no_fix_rounds_total', 0) > 0:
        reset_suggested = True
    elif progress.get('no_fix_rounds_total', 0) >= args.threshold:
        findings.append({'scope': 'workflow', 'reason': 'no_fix_rounds_total threshold reached', 'value': progress.get('no_fix_rounds_total', 0)})

    for loop in loops:
        if loop.get('status') in {'running', 'paused'} and loop.get('current_func') is None and not any(child.get('parent') == loop.get('id') and child.get('status') in {'running', 'paused'} for child in loops):
            findings.append({'scope': loop.get('id'), 'reason': 'loop has no current_func while active', 'value': loop.get('round')})
        for branch in loop.get('branches') or []:
            nf = branch.get('no_fix_rounds') or 0
            if meaningful_progress and nf > 0:
                reset_suggested = True
            elif nf >= args.threshold:
                findings.append({'scope': f"{loop.get('id')}:{branch.get('branch_id')}", 'reason': 'branch no_fix_rounds threshold reached', 'value': nf})

    result = {
        'ok': len(findings) == 0,
        'shouldPause': len(findings) > 0,
        'threshold': args.threshold,
        'findings': findings,
        'resetSuggested': reset_suggested,
        'recommendedEvent': 'dead-loop' if findings else None,
        'recommendedTo': 'paused' if findings else None,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result['ok']:
            print('OK')
            if reset_suggested:
                print('! reset no_fix_rounds counters suggested')
        else:
            print('STALL')
            for f in findings:
                print(f"- {f['scope']}: {f['reason']} ({f['value']})")


if __name__ == '__main__':
    main()
