#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'check_transition.py'

CASES = [
    {
        'name': 'worker pre-dispatch -> awaiting-result',
        'fixture': ROOT / 'scripts' / 'fixtures' / 'worker-pre-dispatch.yaml',
        'event': 'worker-dispatched',
        'to': 'awaiting-result',
        'expect_ok': True,
    },
    {
        'name': 'worker result -> running',
        'fixture': ROOT / 'scripts' / 'fixtures' / 'worker-result-ready.yaml',
        'event': 'worker-result',
        'to': 'running',
        'expect_ok': True,
    },
    {
        'name': 'alias result-ingested rejected',
        'fixture': ROOT / 'scripts' / 'fixtures' / 'worker-result-ready.yaml',
        'event': 'result-ingested',
        'to': 'running',
        'expect_ok': False,
    },
    {
        'name': 'alias dispatch rejected',
        'fixture': ROOT / 'scripts' / 'fixtures' / 'worker-pre-dispatch.yaml',
        'event': 'dispatch',
        'to': 'awaiting-result',
        'expect_ok': False,
    },
]


def main():
    results = []
    for case in CASES:
        cmd = [
            'python3', str(SCRIPT), str(case['fixture']),
            '--event', case['event'], '--to', case['to'], '--json'
        ]
        p = subprocess.run(cmd, capture_output=True, text=True)
        parsed = json.loads(p.stdout)
        ok = (p.returncode == 0) == case['expect_ok']
        results.append({
            'name': case['name'],
            'expect_ok': case['expect_ok'],
            'ok': ok,
            'event': case['event'],
            'to': case['to'],
            'returncode': p.returncode,
            'parsed': parsed,
        })
    summary = {
        'cases': len(results),
        'unexpectedFailures': sum(1 for r in results if not r['ok']),
    }
    print(json.dumps({'summary': summary, 'results': results}, indent=2))
    raise SystemExit(1 if summary['unexpectedFailures'] else 0)


if __name__ == '__main__':
    main()
