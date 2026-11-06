"""Human-readable report derived exclusively from a persisted analysis snapshot."""
import json
from datetime import datetime, timezone


def markdown_report(data):
    def text(value):
        # Escape source text so document instructions/markup remain quoted data.
        return str(value or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('`', '\\`')

    case, run = data['case'], data['run']
    lines = ['# ATOPSY investigation report', '', f"Case: {text(case['title'])}",
        f"Case ID: {case['id']}", f"Analysis: v{run['version']} / {run['id']} / {run['status']}",
        f"Generated: {datetime.now(timezone.utc).isoformat()}", '',
        '## Scope and qualifications', '', *['- ' + text(x) for x in data['limitations']], '',
        'Review and hypothesis revisions reflect the export time and retain their original run references.', '',
        '## Evidence inventory', '']
    for evidence in data['evidence']:
        lines += [f"- {text(evidence['original_filename'])} ({evidence['id']})", f"  SHA-256: {evidence['sha256_hash']}"]
    lines += ['', '## Processing and exclusions', '']
    for stage in data['stages']:
        lines += [f"- {stage['scope']} / {stage['name']}: {stage['status']}" + (f" — {text(stage['error'])}" if stage['error'] else '')]
    lines += ['', *[text(w) for w in run.get('warnings', [])], '', '## Source observations', '']
    reviews = {r['target_id']: r for r in data['reviews']}
    for entity in data['entities']:
        review = reviews.get(entity['entity_id'], {})
        lines += [f"### {text(entity['entity_type'])}: {text(entity['canonical_value'])}", '',
            f"Entity ID: {entity['entity_id']}; source: {text(entity['document_name'])} ({entity['evidence_id']})",
            f"Assertion: {text(entity.get('metadata', {}).get('assertion_status', 'EXTRACTED_ASSERTION'))}; extraction confidence: {entity['confidence']}; review: {review.get('state', 'DETECTED')}", '']
        for span in entity['provenance'].get('source_spans', []):
            lines += [f"Page {span['page'] + 1}, characters {span['start_char']}–{span['end_char']}:", '',
                *['> ' + text(line) for line in span['raw_text'].splitlines()], '']
        if review.get('correction'):
            lines += ['Reviewed correction: ' + text(review['correction']), '']
    # JSON appendices preserve every engine's alternatives, caveats, citations and
    # reasoning without inventing a narrative interpretation of forensic findings.
    for key, title in [('correlation', 'Cross-evidence relationships'), ('temporal', 'Timeline and unresolved times'),
        ('tod', 'Experimental TOD candidates and assumptions'), ('anomalies', 'Automated review leads'),
        ('hypotheses', 'Investigator hypotheses'), ('reviews', 'Review revisions'), ('audit', 'Audit history')]:
        lines += ['', '## ' + title, '', '```json', json.dumps(data.get(key), indent=2, default=str).replace('```', '\\u0060\\u0060\\u0060'), '```']
    return '\n'.join(lines) + '\n'
