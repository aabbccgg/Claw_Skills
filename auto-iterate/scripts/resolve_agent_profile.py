#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path


def load_json(path: Path):
    with open(path, 'r') as f:
        return json.load(f)


def normalize(v: str | None) -> str:
    return (v or '').strip().lower()


def extract_allowed_agents(agents_payload: dict) -> list[str]:
    return [str(a.get('id') or '').strip() for a in (agents_payload.get('agents') or []) if str(a.get('id') or '').strip()]


def extract_profiles(openclaw_payload: dict) -> list[dict]:
    return list((openclaw_payload.get('agents') or {}).get('list') or [])


def match_profiles(requested: str, profiles: list[dict]) -> list[dict]:
    rq = normalize(requested)
    matches = []
    for item in profiles:
        candidates = {
            normalize(item.get('id')),
            normalize(item.get('name')),
        }
        if rq in candidates:
            matches.append(item)
    return matches


def main():
    ap = argparse.ArgumentParser(description='Resolve a requested agent/profile against runtime-available agents and OpenClaw agent config.')
    ap.add_argument('--requested', required=True, help='Requested agent identifier/name/profile reference')
    ap.add_argument('--agents-json', required=True, help='Path to JSON from agents_list output')
    ap.add_argument('--openclaw-json', default=os.path.expanduser('~/.openclaw/openclaw.json'), help='Path to openclaw.json')
    ap.add_argument('--json', action='store_true', help='Emit JSON result')
    args = ap.parse_args()

    requested = args.requested.strip()
    agents_payload = load_json(Path(args.agents_json).expanduser())
    openclaw_payload = load_json(Path(args.openclaw_json).expanduser())

    allowed = extract_allowed_agents(agents_payload)
    profiles = extract_profiles(openclaw_payload)
    matches = match_profiles(requested, profiles)

    result = {
        'ok': False,
        'requestedProfile': requested,
        'matchedProfile': None,
        'spawnable': False,
        'spawnAgentId': None,
        'expectedPrimaryModel': None,
        'fallbackNeeded': False,
        'reason': None,
        'allowedAgents': allowed,
        'matchedProfiles': [
            {
                'id': item.get('id'),
                'name': item.get('name'),
                'expectedPrimaryModel': ((item.get('model') or {}).get('primary')),
            }
            for item in matches
        ],
    }

    if not matches:
        result['reason'] = 'requested profile not found in openclaw.json'
    elif len(matches) > 1:
        result['reason'] = 'requested profile is ambiguous'
    else:
        match = matches[0]
        matched_id = str(match.get('id') or '').strip()
        result['matchedProfile'] = matched_id or (match.get('name') or None)
        result['expectedPrimaryModel'] = ((match.get('model') or {}).get('primary'))
        if matched_id in allowed:
            result['ok'] = True
            result['spawnable'] = True
            result['spawnAgentId'] = matched_id
        else:
            result['fallbackNeeded'] = True
            result['reason'] = 'matched profile exists but is not spawnable in the current runtime allowlist'

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result['ok']:
            print(result['spawnAgentId'])
        else:
            print(result['reason'] or 'resolution failed')
    sys.exit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
