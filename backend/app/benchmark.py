"""Compare aggregate harvested-acre predictions with a NASS Quick Stats reference export.

Offline and standard library only: no model, satellite, network or API access.

Both files are CSV with the Quick Stats export headers (the lab file's column
names are accepted as aliases). A row is comparable only when it states all of:

  Year       four digits
  Geo Level  NATIONAL (State = US TOTAL) or STATE
  State      state name, matched exactly after trimming and upper-casing
  Data Item  exactly "CORN, GRAIN - ACRES HARVESTED" or "CORN, SILAGE - ACRES HARVESTED"
  Domain     TOTAL
  Value      acres; (D), (S), (H), (NA), NA or blank mean unknown, never zero

Rows that state another unit, scope or geography are rejected with a reason;
nothing is inferred. NATIONAL, STATE and the "OTHER STATES" aggregate are three
separate kinds of geography: they are matched only to their own kind and are
never added together.

The output is per-row errors plus descriptive summaries. It is not a contest
score: the judges' scored geographies and formula are unconfirmed.
"""
import csv
import hashlib
import json
import math
import re
from pathlib import Path

NOT_A_CONTEST_METRIC = (
    'Per-row errors and descriptive summaries only. This is not a contest score: '
    "the judges' scored geographies and formula are unconfirmed.")
ERROR_DEFINITIONS = {
    'signed_error': 'prediction - reference, in acres',
    'absolute_error': '|prediction - reference|, in acres',
    'relative_error': '(prediction - reference) / reference; null when the reference is 0',
}

NATIONAL, STATE, OTHER_STATES = 'NATIONAL', 'STATE', 'OTHER STATES'
NATIONAL_NAME = 'US TOTAL'

# Normalised field -> accepted headers (lower case). First group is the Quick
# Stats export; the rest are the lab file / rollup export column names.
_ALIASES = {
    'year': ('year',),
    'geo_level': ('geo level', 'aggregation_level', 'agg_level_desc'),
    'state': ('state', 'state_name'),
    'item': ('data item', 'short_description', 'short_desc'),
    'domain': ('domain', 'domain_desc'),
    'value': ('value',),
    'cv': ('cv (%)', 'cv_percent'),
    'program': ('program', 'source', 'source_desc'),
    'period': ('period', 'reference_period'),
    'county': ('county', 'county_name'),
    'ag_district': ('ag district', 'asd_desc'),
    'zip_code': ('zip code', 'zip_5'),
    'region': ('region', 'region_desc'),
    'watershed': ('watershed', 'watershed_desc'),
}
_REQUIRED = ('year', 'geo_level', 'state', 'item', 'domain', 'value')
# A STATE or NATIONAL row must leave these blank. The watershed *code* is not
# checked: the export writes 00000000 on every row.
_SUB_STATE = ('county', 'ag_district', 'zip_code', 'region', 'watershed')
_ITEM = re.compile(r'CORN, (GRAIN|SILAGE) - ACRES HARVESTED')
_UNKNOWN_WORDS = {'NA', 'N/A', 'NAN', 'NULL', 'NONE'}


class BenchmarkError(Exception):
    """The file cannot be read as a comparable table at all."""


def _columns(fieldnames, label: str) -> dict:
    found = {}
    for header in fieldnames or []:
        key = (header or '').strip().lower()
        for field, names in _ALIASES.items():
            if key in names:
                if field in found:
                    raise BenchmarkError(
                        f'{label}: columns "{found[field]}" and "{header}" both give {field}.')
                found[field] = header
    missing = [_ALIASES[f][0] for f in _REQUIRED if f not in found]
    if missing:
        raise BenchmarkError(f'{label}: missing required column(s): {", ".join(missing)}.')
    return found


def _value(raw: str):
    """(value, unknown_code, problem). Exactly one of the three describes the cell."""
    text = raw.strip()
    if not text:
        return None, 'blank', None
    if (text.startswith('(') and text.endswith(')')) or text.upper() in _UNKNOWN_WORDS:
        return None, text, None
    try:
        number = float(text.replace(',', ''))
    except ValueError:
        return None, None, f'Value "{text}" is not a number or a suppression code'
    if not math.isfinite(number) or number < 0:
        return None, None, f'Value "{text}" is not a finite, non-negative acreage'
    return number, None, None


def _geography(level: str, state: str):
    """(kind, name, problem) from Geo Level and State together."""
    if level == NATIONAL:
        if state != NATIONAL_NAME:
            return None, None, f'Geo Level NATIONAL with State "{state}" (expected {NATIONAL_NAME})'
        return NATIONAL, NATIONAL_NAME, None
    if level == STATE:
        if not state or state == NATIONAL_NAME:
            return None, None, f'Geo Level STATE with State "{state}"'
        return (OTHER_STATES if state == OTHER_STATES else STATE), state, None
    return None, None, f'Geo Level "{level}" is not NATIONAL or STATE'


def read_rows(path, label: str) -> dict:
    """Normalise one CSV. Returns rows, rejected rows (with reasons) and a row count."""
    try:
        with open(path, encoding='utf-8-sig', newline='') as file:
            reader = csv.DictReader(file)
            cols = _columns(reader.fieldnames, label)
            get = lambda record, field: (record.get(cols[field]) or '').strip() if field in cols else ''
            rows, rejected, read = [], [], 0
            for record in reader:
                read += 1
                line = reader.line_num
                level, state = get(record, 'geo_level').upper(), get(record, 'state').upper()
                item, year = get(record, 'item').upper(), get(record, 'year')
                kind, name, geo_problem = _geography(level, state)
                number, unknown, value_problem = _value(get(record, 'value'))
                match = _ITEM.fullmatch(item)
                reasons = []
                if not re.fullmatch(r'\d{4}', year):
                    reasons.append(f'Year "{year}" is not four digits')
                if geo_problem:
                    reasons.append(geo_problem)
                if not match:
                    reasons.append(f'Data Item "{item}" is not CORN, GRAIN|SILAGE - ACRES HARVESTED')
                if get(record, 'domain').upper() != 'TOTAL':
                    reasons.append(f'Domain "{get(record, "domain")}" is not TOTAL')
                if 'period' in cols and get(record, 'period').upper() != 'YEAR':
                    reasons.append(f'Period "{get(record, "period")}" is not YEAR')
                for field in _SUB_STATE:
                    if get(record, field):
                        reasons.append(f'{cols[field]} "{get(record, field)}" is set on a {level} row')
                if value_problem:
                    reasons.append(value_problem)
                if reasons:
                    rejected.append({'line': line, 'reasons': reasons, 'year': year, 'geo_level': level,
                                     'state': state, 'data_item': item, 'value': get(record, 'value')})
                    continue
                cv, _, _ = _value(get(record, 'cv'))
                rows.append({'line': line, 'year': int(year), 'geo_kind': kind, 'geography': name,
                             'crop_use': match.group(1).capitalize(), 'value': number,
                             'unknown_code': unknown, 'cv_percent': cv,
                             'program': get(record, 'program') or None})
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise BenchmarkError(f'{label}: cannot read {path}: {exc}') from exc
    return {'rows_read': read, 'rows': rows, 'rejected': rejected}


def _key(row: dict) -> tuple:
    return row['year'], row['geo_kind'], row['geography'], row['crop_use']


def _group(rows: list) -> dict:
    grouped = {}
    for row in rows:
        grouped.setdefault(_key(row), []).append(row)
    return grouped


def _mean(values: list):
    return sum(values) / len(values) if values else None


def compare(reference: dict, predictions: dict) -> dict:
    """Match normalised tables key by key: (year, geography kind, geography, crop use)."""
    ref, pred = _group(reference['rows']), _group(predictions['rows'])
    kinds = {NATIONAL: 0, STATE: 1, OTHER_STATES: 2}
    comparisons = []
    for key in sorted(set(ref) | set(pred), key=lambda k: (k[0], kinds[k[1]], k[2], k[3])):
        r_rows, p_rows = ref.get(key, []), pred.get(key, [])
        row = {'year': key[0], 'geo_kind': key[1], 'geography': key[2], 'crop_use': key[3],
               'status': None, 'reference_value': None, 'prediction_value': None,
               'signed_error': None, 'absolute_error': None, 'relative_error': None,
               'reference_unknown_code': None, 'prediction_unknown_code': None,
               'reference_cv_percent': None,
               'reference_lines': [r['line'] for r in r_rows],
               'prediction_lines': [p['line'] for p in p_rows]}
        if len(r_rows) > 1 or len(p_rows) > 1:
            # Ambiguous: never pick the first row, average, or add duplicates up.
            row['status'] = 'duplicate'
            row['duplicate_in'] = ([] if len(r_rows) < 2 else ['reference']) + \
                                  ([] if len(p_rows) < 2 else ['predictions'])
            row['reference_values'] = [r['value'] for r in r_rows]
            row['prediction_values'] = [p['value'] for p in p_rows]
        else:
            if r_rows:
                row.update(reference_value=r_rows[0]['value'],
                           reference_unknown_code=r_rows[0]['unknown_code'],
                           reference_cv_percent=r_rows[0]['cv_percent'])
            if p_rows:
                row.update(prediction_value=p_rows[0]['value'],
                           prediction_unknown_code=p_rows[0]['unknown_code'])
            if not p_rows:
                row['status'] = 'missing_prediction'
            elif not r_rows:
                row['status'] = 'unmatched_prediction'
            elif row['reference_value'] is None:
                row['status'] = 'reference_unknown'
            elif row['prediction_value'] is None:
                row['status'] = 'prediction_unknown'
            else:
                error = row['prediction_value'] - row['reference_value']
                row.update(status='scored', signed_error=error, absolute_error=abs(error),
                           relative_error=error / row['reference_value'] if row['reference_value'] else None)
        comparisons.append(row)

    statuses = ('scored', 'missing_prediction', 'unmatched_prediction', 'reference_unknown',
                'prediction_unknown', 'duplicate')
    summaries = []
    for kind in (NATIONAL, STATE, OTHER_STATES):
        for use in ('Grain', 'Silage'):
            group = [c for c in comparisons if c['geo_kind'] == kind and c['crop_use'] == use]
            if not group:
                continue
            scored = [c for c in group if c['status'] == 'scored']
            relative = [abs(c['relative_error']) for c in scored if c['relative_error'] is not None]
            summaries.append({'geo_kind': kind, 'crop_use': use,
                'reference_keys': sum(1 for c in group if c['reference_lines']),
                'scored_rows': len(scored),
                'mean_signed_error': _mean([c['signed_error'] for c in scored]),
                'mean_absolute_error': _mean([c['absolute_error'] for c in scored]),
                'mean_absolute_relative_error': _mean(relative),
                'relative_error_rows': len(relative)})
    side = lambda table: {'rows_read': table['rows_read'], 'rows_accepted': len(table['rows']),
                          'rows_rejected': len(table['rejected']), 'rejected': table['rejected']}
    return {
        'label': NOT_A_CONTEST_METRIC,
        'unit': 'ACRES HARVESTED',
        'error_definitions': ERROR_DEFINITIONS,
        'matching': ('year, geography kind (NATIONAL, STATE, OTHER STATES), geography name and crop use; '
                     'kinds are never combined and states are never summed into a national figure'),
        'reference': side(reference),
        'predictions': side(predictions),
        'status_counts': {s: sum(1 for c in comparisons if c['status'] == s) for s in statuses},
        'summaries_note': ('Unweighted means over scored rows within one geography kind and crop use. '
                           'Descriptive only; ' + NOT_A_CONTEST_METRIC),
        'summaries': summaries,
        'comparisons': comparisons,
    }


def fingerprint(path) -> dict:
    """SHA-256 of a file and whether it matches a neighbouring <name>.source.json, if any."""
    path = Path(path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise BenchmarkError(f'Cannot read {path}: {exc}') from exc
    recorded = None
    try:
        recorded = json.loads(path.with_suffix('.source.json').read_text(encoding='utf-8')).get('sha256')
    except (OSError, ValueError, AttributeError):
        pass
    return {'sha256': digest, 'recorded_sha256': recorded,
            'matches_recorded': None if recorded is None else recorded == digest}


REPO_ROOT = Path(__file__).resolve().parents[2]


def display_path(path) -> str:
    """Repository-relative POSIX path for reports (no local user or drive); the file name if outside the repo."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.name


def score_files(reference_path, predictions_path) -> dict:
    """Read both CSV files and return the comparison report."""
    report = compare(read_rows(reference_path, 'reference'), read_rows(predictions_path, 'predictions'))
    report['reference'] = {'path': display_path(reference_path), **fingerprint(reference_path), **report['reference']}
    report['predictions'] = {'path': display_path(predictions_path), **report['predictions']}
    return report
