"""Replay saved OpenAI proposals locally; never create a provider client or job.

Run from backend with --database data/documents.sqlite3 --document-id ID
--output ../tmp/offline-replay.json. The SQLite connection is read-only.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.facts import VALIDATOR_VERSION, project_saved_indexed


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def counts(result):
    return {key: len(result.get(key, [])) for key in ('facts', 'review_candidates', 'rejected_candidates')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--document-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        job = db.execute('SELECT * FROM fact_jobs WHERE document_id=?', (args.document_id,)).fetchone()
        if not job or job['provider'] != 'openai':
            parser.error('An existing OpenAI extraction is required; no job was created.')
        segments = db.execute('SELECT * FROM fact_segments WHERE document_id=? AND request_hash=? ORDER BY ordinal',
                              (args.document_id, job['request_hash'])).fetchall()
    source = json.loads(job['source_snapshot'])
    rows = []
    for segment in segments:
        if not segment['output_json']:
            continue
        saved = json.loads(segment['output_json'])
        proposal = saved.get('proposed_result')
        if not proposal:
            continue
        before_hash = digest(proposal)
        after = project_saved_indexed(saved, source, json.loads(segment['payload_json']))
        assert before_hash == digest(proposal), 'Replay mutated a saved proposal'
        baseline = saved['result']
        rejected_before = {item['fact_index'] for item in baseline.get('rejected_candidates', [])}
        recoveries = [{'proposal_index': item['fact_index'],
                       'before': 'rejected' if item['fact_index'] in rejected_before else 'previously_supported',
                       'after': 'needs_review', 'reference_changes': item['recovery_audit']}
                      for item in after.get('review_candidates', []) if item.get('recovery_audit')]
        rows.append({'segment_id': segment['segment_id'], 'proposal_sha256': before_hash,
                     'raw_proposal_unchanged': True, 'before': counts(baseline), 'after': counts(after),
                     'before_rejection_reasons': dict(Counter(item['reason'] for item in baseline.get('rejected_candidates', []))),
                     'after_rejection_reasons': dict(Counter(item['reason'] for item in after.get('rejected_candidates', []))),
                     'after_review_methods': dict(Counter(item.get('method', 'model_association') for item in after.get('review_candidates', []))),
                     'recovery_transitions': recoveries})
    if not rows:
        parser.error('No replayable saved responses; no provider request was made.')
    result = {'scope': 'Local evidence replay, not semantic accuracy or final QA evaluation',
              'provider_calls': 0, 'validator_version': VALIDATOR_VERSION,
              'before': {key: sum(row['before'][key] for row in rows) for key in rows[0]['before']},
              'after': {key: sum(row['after'][key] for row in rows) for key in rows[0]['after']}, 'segments': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('provider_calls', 'validator_version', 'before', 'after')}))


if __name__ == '__main__':
    main()
