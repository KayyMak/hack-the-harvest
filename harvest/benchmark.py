"""Score an aggregate prediction CSV against the judges' 2025 Quick Stats reference:

    python -m harvest.benchmark --predictions my_state_estimates.csv --out report.json

Offline and standard library only. The prediction file uses the Quick Stats export
headers; these columns are required (others are ignored):

    Year,Geo Level,State,Data Item,Domain,Value
    2025,STATE,MARYLAND,"CORN, SILAGE - ACRES HARVESTED",TOTAL,"41,500"
    2025,NATIONAL,US TOTAL,"CORN, GRAIN - ACRES HARVESTED",TOTAL,

Geo Level is NATIONAL (State = US TOTAL) or STATE; Data Item is exactly
"CORN, GRAIN - ACRES HARVESTED" or "CORN, SILAGE - ACRES HARVESTED"; Domain is TOTAL;
Value is acres, and blank, NA or a code such as (D) means unknown, never zero.
Rows for any other unit or scope, such as the BARC labeled-field roll-up, are
rejected and listed, not scored.

The report holds per-row signed, absolute and relative errors and descriptive
summaries. It is not a contest score: the judges' scored geographies and formula
are unconfirmed. See backend/app/benchmark.py for the matching rules.
"""
import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(_ROOT / 'backend'))

from app.benchmark import BenchmarkError, score_files  # noqa: E402

DEFAULT_REFERENCE = _ROOT / 'data' / 'reference' / 'quickstats_2025_judges.csv'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Per-row errors against a Quick Stats reference (not a contest score)')
    ap.add_argument('--predictions', required=True, help='CSV of aggregate predictions (Quick Stats headers)')
    ap.add_argument('--reference', default=str(DEFAULT_REFERENCE), help='Quick Stats export CSV')
    ap.add_argument('--out', help='write the JSON report here instead of standard output')
    a = ap.parse_args(argv)
    try:
        report = score_files(a.reference, a.predictions)
    except BenchmarkError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2)
    if a.out:
        Path(a.out).write_text(text + '\n', encoding='utf-8')
        brief = {'label': report['label'], 'status_counts': report['status_counts'],
                 'reference_rows_rejected': report['reference']['rows_rejected'],
                 'prediction_rows_rejected': report['predictions']['rows_rejected'],
                 'reference_matches_recorded_sha256': report['reference']['matches_recorded'],
                 'out': a.out}
        print(json.dumps(brief, indent=2))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
