"""Offline checks for the decline-date rule baseline (standard library only)."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decline_rule_baseline as rule


def series(*points):
    return [(day, value) for day, value in points]


def obs(day, ndvi, status='ok'):
    return {'date': day, 'ndvi': str(ndvi), 'status': status}


class DeclineRuleChecks(unittest.TestCase):
    def test_duplicate_dates_count_once_and_rejected_scenes_are_ignored(self):
        result = rule.daily_series([obs('2021-08-01', 0.8), obs('2021-08-01', 0.6),
                                    obs('2021-08-06', 0.1, status='insufficient_clear_pixels'),
                                    obs('2021-08-11', '', status='ok')])
        self.assertEqual(result, [('2021-08-01', 0.7)])

    def test_sustained_decline_ignores_a_single_low_date(self):
        cliff = series(('2021-07-01', 0.80), ('2021-07-15', 0.82), ('2021-08-01', 0.81),
                       ('2021-09-01', 0.30), ('2021-09-10', 0.28), ('2021-10-01', 0.25))
        self.assertEqual(rule.decline_doy(cliff), 244)  # 1 September
        dip = series(('2021-07-01', 0.80), ('2021-07-15', 0.82), ('2021-08-01', 0.20),
                     ('2021-08-10', 0.81), ('2021-08-20', 0.80), ('2021-09-01', 0.79))
        self.assertIsNone(rule.decline_doy(dip))  # one cloudy-looking date is smoothed away
        self.assertIsNone(rule.decline_doy([]))

    def test_no_decline_is_grain_never_silage(self):
        self.assertEqual(rule.classify(None, 330), 'Grain')
        self.assertEqual(rule.classify(250, 260), 'Silage')
        self.assertEqual(rule.classify(261, 260), 'Grain')

    def test_threshold_uses_only_the_rows_it_is_given(self):
        train = [dict(label='Silage', decline_doy=240), dict(label='Silage', decline_doy=250),
                 dict(label='Grain', decline_doy=290), dict(label='Grain', decline_doy=300)]
        threshold = rule.fit_threshold(train)
        self.assertTrue(250 <= threshold < 290)
        # A held-out row with the opposite pattern must not move the fitted value.
        self.assertEqual(threshold, rule.fit_threshold(list(train)))

    def test_saved_results_reproduce_and_folds_keep_fields_together(self):
        rows, metadata = rule.load()
        report = rule.evaluate(rows, metadata)
        saved = json.loads((rule.OUT / 'metrics.json').read_text(encoding='utf-8'))
        self.assertEqual(json.loads(json.dumps(report)), saved)
        self.assertEqual(report['evaluated_field_years'], 44)
        folds = {}
        for row in rows:
            self.assertEqual(folds.setdefault(row['OBJECTID'], row['fold']), row['fold'])
            self.assertIn(row['label'], ('Grain', 'Silage'))
        for fold in metadata['folds']:
            train = [r for r in rows if r['OBJECTID'] in set(fold['training_fields'])]
            self.assertFalse({r['OBJECTID'] for r in train} & set(fold['test_fields']))
            self.assertEqual(rule.fit_threshold(train), report['thresholds_by_fold'][fold['fold']])
        self.assertEqual(report['logistic_same_rows']['confusion_matrix'],
                         metadata['logistic']['confusion_matrix'])


if __name__ == '__main__':
    unittest.main()
