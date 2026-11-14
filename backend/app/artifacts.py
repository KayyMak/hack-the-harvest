"""Read saved analysis outputs without importing or running the analysis stack."""
import csv
from pathlib import Path

from pydantic import ValidationError

from .schemas import BaselineSummary, Prediction

OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'baseline' / 'outputs'


class ArtifactUnavailable(Exception):
    pass


def read_summary() -> BaselineSummary:
    try:
        return BaselineSummary.model_validate_json(
            (OUTPUT_DIR / 'metrics.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, ValidationError) as exc:
        raise ArtifactUnavailable('Saved baseline metrics are missing or invalid.') from exc


def read_predictions() -> list[Prediction]:
    try:
        with (OUTPUT_DIR / 'heldout_predictions.csv').open(encoding='utf-8', newline='') as file:
            rows = list(csv.DictReader(file))
        if not rows:
            raise ValueError('Empty predictions file')
        return [Prediction(field_id=row['OBJECTID'], year=row['year'],
            reference_label=row['label'], predicted_label=row['predicted_label'],
            silage_probability=row['silage_probability'], fold=row['fold'],
            valid_dates=row['valid_dates']) for row in rows]
    except (OSError, ValueError, KeyError, ValidationError) as exc:
        raise ArtifactUnavailable('Saved baseline predictions are missing or invalid.') from exc
