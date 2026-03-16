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
    compact = re.sub(r'[^a-z0-9]+', '', rq)

    exact = []
    prefix = []
    token = []
    for item in profiles:
        pid = normalize(item.get('id'))
        pname = normalize(item.get('name'))
        candidates = {pid, pname}
        compact_candidates = {re.sub(r'[^a-z0-9]+', '', c) for c in candidates if c}

        if rq in candidates or (compact and compact in compact_candidates):
            exact.append(item)
            continue

        if any(c.startswith(rq) for c in candidates if rq) or any(cc.startswith(compact) for cc in compact_candidates if compact):
            prefix.append(item)
            continue

        rq_tokens = [t for t in re.split(r'[^a-z0-9]+', rq) if t]
        cand_tokens = set()
        for c in candidates:
            cand_tokens.update([t for t in re.split(r'[^a-z0-9]+', c) if t])
        if rq_tokens and all(t in cand_tokens for t in rq_tokens):
            token.append(item)

    if exact:
        return exact
    if len(prefix) == 1:
        return prefix
    if len(prefix) > 1:
        return prefix
    if len(token) == 1:
        return token
    if len(token) > 1:
        return token
    return []


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
