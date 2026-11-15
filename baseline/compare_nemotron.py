"""Frozen, numerical-feature comparison: run `pilot`, then `run` in the key's terminal.

Uses only the standard library. Never modifies the logistic regression artifacts.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
INPUTS = HERE / 'outputs'
OUT = INPUTS / 'nemotron'
MODEL = 'nvidia/nemotron-3.5-super-vl-120b-a12b'
URL = 'https://integrate.api.nvidia.com/v1/chat/completions'
PROMPT = '''Predict whether a corn field was harvested for Grain or Silage using
only its nine numerical satellite vegetation features and the labeled training
examples supplied below. NDVI measures greenness. ndvi_07 through ndvi_11 are
July through November monthly median NDVI. peak_ndvi is the maximum observed
July-November NDVI; peak_doy is its day of year. late_ndvi is median NDVI from
September onward. early_minus_late is the July-August median minus the
October-November median. Values are in original units. Missing values have been
imputed with training-fold medians (zero for an entirely missing training column).
Infer the relationship from the examples; no harvest-date rule is definitive.
Return exactly one JSON object: {"harvest_type":"Grain"} or
{"harvest_type":"Silage"}. Do not include an explanation or other keys.'''


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def load_inputs():
    with (INPUTS / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as file:
        rows = list(csv.DictReader(file))
    metadata = json.loads((INPUTS / 'metrics.json').read_text(encoding='utf-8'))
    features = metadata['features']
    if len(features) != 9 or not rows:
        raise ValueError('Expected the saved nine-feature baseline and nonempty predictions')
    keys, groups = set(), {}
    for row in rows:
        row['OBJECTID'], row['year'], row['fold'] = (int(row[k]) for k in ['OBJECTID', 'year', 'fold'])
        key = row['OBJECTID'], row['year']
        if key in keys or row['label'] not in ['Grain', 'Silage']:
            raise ValueError('Duplicate field-year or blank/unexpected reference label')
        keys.add(key)
        if groups.setdefault(row['OBJECTID'], row['fold']) != row['fold']:
            raise ValueError('Repeated field appears in different folds')
        for feature in features:
            value = float(row[feature]) if row[feature] else math.nan
            row[feature] = value if math.isfinite(value) else None
    for fold in metadata['folds']:
        test = {r['OBJECTID'] for r in rows if r['fold'] == fold['fold']}
        train = {r['OBJECTID'] for r in rows if r['fold'] != fold['fold']}
        if test != set(fold['test_fields']) or train != set(fold['training_fields']) or test & train:
            raise ValueError('Saved prediction folds do not match saved split metadata')
    if len(rows) != metadata['evaluated_field_years']:
        raise ValueError('Saved evaluation count does not match prediction rows')
    provenance = {name: hashlib.sha256((INPUTS / name).read_bytes()).hexdigest()
                  for name in ['heldout_predictions.csv', 'metrics.json']}
    return rows, features, provenance


def make_request(rows, target, features):
    training = [r for r in rows if r['fold'] != target['fold']]
    if not training or any(r['OBJECTID'] == target['OBJECTID'] for r in training):
        raise ValueError('Missing training examples or field leakage')
    medians = {f: statistics.median(values) if values else 0.0
               for f in features for values in [[r[f] for r in training if r[f] is not None]]}

    def measurements(row):
        return {f: row[f] if row[f] is not None else medians[f] for f in features}

    evidence = dict(training_examples=[dict(features=measurements(r), harvest_type=r['label'])
                                      for r in training],
                    field_to_classify=measurements(target))
    payload = dict(model=MODEL, messages=[{'role': 'system', 'content': PROMPT},
        {'role': 'user', 'content': encode(evidence)}], temperature=0, top_p=1,
        max_tokens=128, seed=42, stream=False,
        chat_template_kwargs={'enable_thinking': False})
    return payload, sorted({r['OBJECTID'] for r in training}), medians


def parse_label(text):
    text = text.strip()
    fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, flags=re.DOTALL | re.IGNORECASE)
    value = json.loads(fenced.group(1) if fenced else text)
    if not isinstance(value, dict) or set(value) != {'harvest_type'} or value['harvest_type'] not in ['Grain', 'Silage']:
        raise ValueError('Expected exactly one Grain/Silage harvest_type in JSON')
    return value['harvest_type']


def complete(payload, key):
    request = urllib.request.Request(URL, data=encode(payload).encode(),
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        return dict(status='request_error', error=f'NVIDIA HTTP {code}', http_status=code,
                    elapsed_seconds=round(time.monotonic() - started, 3))
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return dict(status='request_error', error=f'Network failure: {type(exc).__name__}',
                    elapsed_seconds=round(time.monotonic() - started, 3))
    except ValueError:
        return dict(status='invalid_response', error='NVIDIA returned invalid response JSON')
    record = dict(elapsed_seconds=round(time.monotonic() - started, 3),
                  usage=result.get('usage'), reported_model=result.get('model')) if isinstance(result, dict) else {}
    try:
        text = result['choices'][0]['message']['content']
        if not isinstance(text, str):
            raise ValueError('No answer text')
        record['raw_response'] = text
        record.update(status='ok', predicted_label=parse_label(text))
    except (ValueError, KeyError, IndexError, TypeError):
        record.update(status='invalid_response', error='Missing answer or invalid Grain/Silage JSON')
    return record


def score(truth, predicted):
    tn = sum(a == 'Grain' and b == 'Grain' for a, b in zip(truth, predicted))
    fp = sum(a == 'Grain' and b == 'Silage' for a, b in zip(truth, predicted))
    fn = sum(a == 'Silage' and b == 'Grain' for a, b in zip(truth, predicted))
    tp = sum(a == 'Silage' and b == 'Silage' for a, b in zip(truth, predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    return dict(n=len(truth), silage_precision=precision, silage_recall=recall,
        silage_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0,
        false_positive_rate=1-specificity if specificity is not None else None,
        balanced_accuracy=(recall+specificity)/2 if recall is not None and specificity is not None else None,
        confusion_matrix=[[tn, fp], [fn, tp]], matrix_order=['Grain', 'Silage'],
        matrix_rows='true', matrix_columns='predicted')


def report(rows, records):
    paired = [(r, records[(r['OBJECTID'], r['year'])]) for r in rows
              if records.get((r['OBJECTID'], r['year']), {}).get('status') == 'ok']
    truth = [r['label'] for r, _ in paired]
    quality = {status: sum(r.get('status') == status for r in records.values())
               for status in ['ok', 'request_error', 'invalid_response']}
    result = dict(total_field_years=len(rows), coverage=quality,
        pending=len(rows)-len(records), protocol='Saved field-grouped folds; training-fold in-context examples; frozen prompt; no fine-tuning',
        nemotron=score(truth, [p['predicted_label'] for _, p in paired]),
        logistic_same_rows=score(truth, [r['predicted_label'] for r, _ in paired]),
        always_grain_same_rows=score(truth, ['Grain']*len(paired)),
        logistic_all_rows=score([r['label'] for r in rows], [r['predicted_label'] for r in rows]),
        token_usage=[r['usage'] for r in records.values() if r.get('usage')],
        limitations=['Exploratory comparison on previously inspected BARC data.',
            'No image inputs. Pretrained Nemotron receives labeled training-fold examples.',
            'Invalid responses, failed requests, and pending rows are not silently assigned Grain.',
            'Seed and temperature do not guarantee identical hosted-model responses.',
            'No API pricing assumption; token usage is recorded when provided.'])
    save(OUT / 'metrics.json', result)
    with (OUT / 'predictions.csv').open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['OBJECTID', 'year', 'fold', 'reference_label',
            'logistic_prediction', 'nemotron_prediction', 'status', 'error'])
        writer.writeheader()
        for row in rows:
            record = records.get((row['OBJECTID'], row['year']), {})
            writer.writerow(dict(OBJECTID=row['OBJECTID'], year=row['year'], fold=row['fold'],
                reference_label=row['label'], logistic_prediction=row['predicted_label'],
                nemotron_prediction=record.get('predicted_label', ''),
                status=record.get('status', 'pending'), error=record.get('error', '')))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['pilot', 'run'])
    parser.add_argument('--retry-failures', action='store_true', help='Explicitly retry cached failed requests')
    args = parser.parse_args()
    key = os.environ.get('NVIDIA_API_KEY', '').strip()
    if not key:
        raise ValueError('Set NVIDIA_API_KEY in this same terminal first')
    rows, features, inputs = load_inputs()
    protocol = dict(model=MODEL, prompt=PROMPT, features=features, inputs=inputs,
                    temperature=0, top_p=1, max_tokens=128, seed=42, enable_thinking=False)
    signature = digest(protocol)
    manifest = OUT / 'protocol.json'
    if manifest.exists() and digest(json.loads(manifest.read_text())) != signature:
        raise ValueError('Protocol or data changed. Move the old nemotron output directory aside before rerunning.')
    save(manifest, protocol)
    records = {}
    requests = {}
    for row in rows:
        identifier = (row['OBJECTID'], row['year'])
        payload, training_fields, medians = make_request(rows, row, features)
        requests[identifier] = (payload, training_fields, medians)
        path = OUT / 'responses' / f'{identifier[0]}_{identifier[1]}.json'
        if path.exists():
            record = json.loads(path.read_text())
            if record['request_sha256'] != digest(payload):
                raise ValueError(f'Stale response cache: {path.name}')
            records[identifier] = record
    pilot_id = (rows[0]['OBJECTID'], rows[0]['year'])
    if args.stage == 'run' and records.get(pilot_id, {}).get('status') != 'ok':
        raise ValueError('Run a successful pilot first; its gate checks format/access, not prediction correctness')
    selected = rows[:1] if args.stage == 'pilot' else rows
    for index, row in enumerate(selected, 1):
        identifier = (row['OBJECTID'], row['year'])
        old = records.get(identifier)
        if old and (old['status'] == 'ok' or not args.retry_failures):
            print(f'{index}/{len(selected)} field {identifier}: cached {old["status"]}', flush=True)
            continue
        payload, training_fields, medians = requests[identifier]
        print(f'{index}/{len(selected)} field {identifier}: requesting prediction...', flush=True)
        record = complete(payload, key)
        record.update(request_sha256=digest(payload), field_id=identifier[0], year=identifier[1],
            fold=row['fold'], training_fields=training_fields, imputation_medians=medians,
            request=payload, recorded_utc=datetime.now(timezone.utc).isoformat())
        save(OUT / 'responses' / f'{identifier[0]}_{identifier[1]}.json', record)
        records[identifier] = record
        print(f'  {record["status"]}', flush=True)
        if record['status'] == 'request_error':
            print(f'Stopping: {record["error"]}. Saved completed results; remaining rows stay pending.', flush=True)
            break
    result = report(rows, records)
    print(f'Saved to {OUT}. Coverage: {result["coverage"]}; pending: {result["pending"]}', flush=True)
    failed = result['coverage']['request_error'] + result['coverage']['invalid_response']
    if args.stage == 'pilot':
        print('Pilot checks only access and response format. Keep the prompt fixed before the full run.', flush=True)
        return int(records.get(pilot_id, {}).get('status') != 'ok')
    print(json.dumps({k: result[k] for k in ['nemotron', 'logistic_same_rows', 'always_grain_same_rows']}, indent=2))
    return int(bool(failed or result['pending']))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(f'Cannot run comparison: {exc}', file=sys.stderr)
        sys.exit(1)
