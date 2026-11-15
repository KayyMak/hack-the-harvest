"""Checks for the offline Quick Stats benchmark adapter.

Every prediction and every reference value used for error arithmetic here is
SYNTHETIC: invented round numbers for invented geographies ("SYNTHETIC STATE A").
They are not estimates and say nothing about any real state. The judges' file is
only checked for structure (headers, row kinds, fingerprint), never for values.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import artifacts, benchmark
from harvest import benchmark as cli

JUDGES = Path(__file__).resolve().parents[2] / 'data' / 'reference' / 'quickstats_2025_judges.csv'

# The judges' export header, verbatim.
HEADER = ('"Program","Year","Period","Week Ending","Geo Level","State","State ANSI","Ag District",'
          '"Ag District Code","County","County ANSI","Zip Code","Region","watershed_code","Watershed",'
          '"Commodity","Data Item","Domain","Domain Category","Value","CV (%)"')
GRAIN, SILAGE = 'CORN, GRAIN - ACRES HARVESTED', 'CORN, SILAGE - ACRES HARVESTED'
A, B = 'SYNTHETIC STATE A', 'SYNTHETIC STATE B'


def line(level, state, item, value, *, year='2025', domain='TOTAL', period='YEAR', county='', cv=''):
    """One synthetic row in the judges' export layout."""
    cells = ['SURVEY', year, period, '', level, state, '', '', '', county, '', '', '', '00000000', '',
             'CORN', item, domain, 'NOT SPECIFIED', value, cv]
    return ','.join('"%s"' % c for c in cells)


def table(*rows):
    return '\n'.join((HEADER,) + rows) + '\n'


class BenchmarkAdapter(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding='utf-8')
        return path

    def score(self, reference, predictions):
        return benchmark.score_files(self.write('synthetic_reference.csv', reference),
                                     self.write('synthetic_predictions.csv', predictions))

    def by_key(self, report):
        return {(c['geo_kind'], c['geography'], c['crop_use']): c for c in report['comparisons']}

    def test_judges_file_headers_and_row_kinds(self):
        self.assertEqual(JUDGES.read_text(encoding='utf-8').splitlines()[0], HEADER)
        table_ = benchmark.read_rows(JUDGES, 'reference')
        self.assertEqual((table_['rows_read'], len(table_['rows']), table_['rejected']), (92, 92, []))
        kinds = {}
        for row in table_['rows']:
            kinds[row['geo_kind'], row['crop_use']] = kinds.get((row['geo_kind'], row['crop_use']), 0) + 1
        self.assertEqual(kinds, {('NATIONAL', 'Grain'): 1, ('NATIONAL', 'Silage'): 1, ('STATE', 'Grain'): 41,
                                 ('OTHER STATES', 'Grain'): 1, ('STATE', 'Silage'): 48})
        self.assertEqual({row['year'] for row in table_['rows']}, {2025})
        self.assertTrue(all(row['program'] == 'SURVEY' and row['cv_percent'] is None for row in table_['rows']))
        self.assertTrue(benchmark.fingerprint(JUDGES)['matches_recorded'])

    def test_no_predictions_means_every_reference_row_is_missing_not_zero(self):
        report = benchmark.score_files(JUDGES, self.write('synthetic_empty.csv', HEADER + '\n'))
        self.assertEqual(report['status_counts'], {'scored': 0, 'missing_prediction': 92,
            'unmatched_prediction': 0, 'reference_unknown': 0, 'prediction_unknown': 0, 'duplicate': 0})
        self.assertTrue(all(c['prediction_value'] is None and c['signed_error'] is None
                            for c in report['comparisons']))
        self.assertTrue(all(s['scored_rows'] == 0 and s['mean_absolute_error'] is None
                            for s in report['summaries']))
        self.assertIn('not a contest score', report['label'])
        self.assertTrue(report['reference']['matches_recorded'])

    def test_both_crop_uses_report_signed_absolute_and_relative_error(self):
        report = self.score(
            table(line('STATE', A, GRAIN, '1,000', cv='2.5'), line('STATE', A, SILAGE, '200')),
            table(line('STATE', A, GRAIN, '1,100'), line('STATE', A, SILAGE, '150')))
        rows = self.by_key(report)
        grain, silage = rows['STATE', A, 'Grain'], rows['STATE', A, 'Silage']
        self.assertEqual((grain['status'], grain['signed_error'], grain['absolute_error']), ('scored', 100, 100))
        self.assertAlmostEqual(grain['relative_error'], 0.1)
        self.assertEqual(grain['reference_cv_percent'], 2.5)
        self.assertEqual((silage['signed_error'], silage['absolute_error'], silage['relative_error']),
                         (-50, 50, -0.25))
        self.assertEqual([(s['geo_kind'], s['crop_use'], s['scored_rows'], s['mean_signed_error'])
                          for s in report['summaries']],
                         [('STATE', 'Grain', 1, 100), ('STATE', 'Silage', 1, -50)])
        self.assertEqual(report['unit'], 'ACRES HARVESTED')

    def test_lab_column_names_are_accepted_for_predictions(self):
        report = self.score(
            table(line('STATE', A, SILAGE, '200')),
            'year,aggregation_level,state_name,short_description,domain,value\n'
            f'2025,STATE,{A.lower()},"{SILAGE}",TOTAL,260\n')
        self.assertEqual(self.by_key(report)['STATE', A, 'Silage']['signed_error'], 60)

    def test_states_are_never_summed_into_the_national_row(self):
        reference = table(line('NATIONAL', 'US TOTAL', GRAIN, '3,000'), line('STATE', A, GRAIN, '1,000'),
                          line('STATE', B, GRAIN, '2,000'))
        rows = self.by_key(self.score(reference, table(line('STATE', A, GRAIN, '900'),
                                                       line('STATE', B, GRAIN, '2,400'))))
        national = rows['NATIONAL', 'US TOTAL', 'Grain']
        self.assertEqual((national['status'], national['prediction_value']), ('missing_prediction', None))
        self.assertEqual(rows['STATE', B, 'Grain']['signed_error'], 400)

        report = self.score(reference, table(line('NATIONAL', 'US TOTAL', GRAIN, '3,300')))
        rows = self.by_key(report)
        self.assertEqual(rows['NATIONAL', 'US TOTAL', 'Grain']['signed_error'], 300)
        self.assertEqual(rows['STATE', A, 'Grain']['status'], 'missing_prediction')
        self.assertEqual([(s['geo_kind'], s['reference_keys'], s['scored_rows']) for s in report['summaries']],
                         [('NATIONAL', 1, 1), ('STATE', 2, 0)])

    def test_other_states_is_its_own_kind_and_zero_reference_has_no_relative_error(self):
        report = self.score(
            table(line('STATE', 'OTHER STATES', GRAIN, '0'), line('STATE', A, GRAIN, '1,000')),
            table(line('STATE', 'OTHER STATES', GRAIN, '50'), line('STATE', A, GRAIN, '1,000')))
        other = self.by_key(report)['OTHER STATES', 'OTHER STATES', 'Grain']
        self.assertEqual((other['status'], other['reference_value'], other['signed_error'],
                          other['relative_error']), ('scored', 0, 50, None))
        summaries = {s['geo_kind']: s for s in report['summaries']}
        self.assertEqual((summaries['OTHER STATES']['scored_rows'], summaries['OTHER STATES']['relative_error_rows'],
                          summaries['OTHER STATES']['mean_absolute_relative_error']), (1, 0, None))
        self.assertEqual((summaries['STATE']['scored_rows'], summaries['STATE']['mean_absolute_error']), (1, 0))

    def test_suppressed_and_missing_values_are_unknown_never_zero(self):
        codes = ['(D)', '(S)', '(H)', '(NA)', '', 'NA', '  (D) ']
        states = [f'SYNTHETIC STATE {i}' for i in range(len(codes))]
        known = table(*[line('STATE', s, SILAGE, '100') for s in states])
        unknown = table(*[line('STATE', s, SILAGE, code) for s, code in zip(states, codes)])
        for reference, predictions, status, side in [(unknown, known, 'reference_unknown', 'reference'),
                                                     (known, unknown, 'prediction_unknown', 'prediction')]:
            report = self.score(reference, predictions)
            self.assertEqual(report['status_counts'][status], len(codes))
            self.assertEqual(report['status_counts']['scored'], 0)
            for row in report['comparisons']:
                self.assertIsNone(row[f'{side}_value'])
                self.assertIsNotNone(row[f'{side}_unknown_code'])
                self.assertIsNone(row['signed_error'])
            self.assertIsNone(report['summaries'][0]['mean_signed_error'])

    def test_duplicates_on_either_side_are_reported_and_not_scored(self):
        report = self.score(
            table(line('STATE', A, GRAIN, '1,000'), line('STATE', A, GRAIN, '1,000'),
                  line('STATE', B, GRAIN, '2,000')),
            table(line('STATE', A, GRAIN, '900'), line('STATE', B, GRAIN, '1,900'),
                  line('STATE', B, GRAIN, '2,100')))
        rows = self.by_key(report)
        a, b = rows['STATE', A, 'Grain'], rows['STATE', B, 'Grain']
        self.assertEqual((a['status'], a['duplicate_in'], a['reference_lines']), ('duplicate', ['reference'], [2, 3]))
        self.assertEqual((b['status'], b['duplicate_in'], b['prediction_lines'], b['prediction_values']),
                         ('duplicate', ['predictions'], [3, 4], [1900, 2100]))
        self.assertIsNone(a['signed_error'])
        self.assertIsNone(b['signed_error'])
        self.assertEqual((report['status_counts']['duplicate'], report['status_counts']['scored']), (2, 0))

    def test_unit_and_scope_mismatches_are_rejected_with_reasons(self):
        bad = [
            (line('STATE', A, 'CORN, GRAIN - ACRES PLANTED', '10'), 'Data Item'),
            (line('STATE', A, 'CORN, GRAIN - PRODUCTION, MEASURED IN BU', '10'), 'Data Item'),
            (line('STATE', A, 'CORN, GRAIN, IRRIGATED - ACRES HARVESTED', '10'), 'Data Item'),
            (line('STATE', A, 'CORN - ACRES HARVESTED', '10'), 'Data Item'),
            (line('STATE', A, GRAIN, '10', domain='IRRIGATION STATUS'), 'Domain'),
            (line('STATE', A, GRAIN, '10', period='YEAR - AUG FORECAST'), 'Period'),
            (line('COUNTY', A, GRAIN, '10', county='SYNTHETIC COUNTY'), 'Geo Level'),
            (line('STATE', A, GRAIN, '10', county='SYNTHETIC COUNTY'), 'County'),
            (line('NATIONAL', A, GRAIN, '10'), 'Geo Level NATIONAL'),
            (line('STATE', 'US TOTAL', GRAIN, '10'), 'Geo Level STATE'),
            (line('BARC LABELED FIELDS', 'MARYLAND', SILAGE, '10'), 'Geo Level'),
            (line('STATE', A, GRAIN, '10', year='25'), 'Year'),
            (line('STATE', A, GRAIN, 'about ten'), 'Value'),
            (line('STATE', A, GRAIN, '-10'), 'Value'),
            (line('STATE', A, GRAIN, 'inf'), 'Value'),
        ]
        report = self.score(table(line('STATE', A, GRAIN, '1,000')), table(*[row for row, _ in bad]))
        rejected = report['predictions']['rejected']
        self.assertEqual([r['line'] for r in rejected], list(range(2, len(bad) + 2)))
        for entry, (_, expected) in zip(rejected, bad):
            self.assertTrue(any(reason.startswith(expected) for reason in entry['reasons']), entry)
        self.assertEqual(report['predictions']['rows_accepted'], 0)
        self.assertEqual((report['status_counts']['scored'], report['status_counts']['missing_prediction'],
                          report['status_counts']['unmatched_prediction']), (0, 1, 0))
        # The same checks apply to the reference side.
        report = self.score(table(bad[0][0]), table(line('STATE', A, GRAIN, '10')))
        self.assertEqual((report['reference']['rows_rejected'], report['status_counts']['unmatched_prediction']),
                         (1, 1))

    def test_unmatched_predictions_are_listed(self):
        report = self.score(
            table(line('STATE', A, GRAIN, '1,000')),
            table(line('STATE', A, GRAIN, '10', year='2024'), line('STATE', B, GRAIN, '10'),
                  line('STATE', A, SILAGE, '10'), line('NATIONAL', 'US TOTAL', GRAIN, '10')))
        self.assertEqual((report['status_counts']['unmatched_prediction'],
                          report['status_counts']['missing_prediction'], report['status_counts']['scored']),
                         (4, 1, 0))

    def test_barc_rollup_export_is_rejected_not_scored_as_maryland(self):
        # The app's own roll-up covers labeled BARC fields only; it must never be
        # compared with a statewide MARYLAND row.
        export = artifacts.rollup_quickstats_csv()
        self.assertIn('BARC LABELED FIELDS', export)
        report = benchmark.score_files(JUDGES, self.write('barc_rollup_export.csv', export))
        predictions = report['predictions']
        self.assertGreater(predictions['rows_read'], 0)
        self.assertEqual((predictions['rows_accepted'], predictions['rows_rejected']),
                         (0, predictions['rows_read']))
        self.assertTrue(all(any('BARC LABELED FIELDS' in reason for reason in r['reasons'])
                            for r in predictions['rejected']))
        self.assertEqual((report['status_counts']['scored'], report['status_counts']['missing_prediction']),
                         (0, 92))

    def test_missing_or_ambiguous_columns_stop_the_run(self):
        for text, expected in [('Year,State,Data Item,Value\n', 'geo level, domain'),
                               ('Year,Geo Level,State,state_name,Data Item,Domain,Value\n', 'both give state'),
                               ('', 'missing required')]:
            with self.assertRaises(benchmark.BenchmarkError) as caught:
                benchmark.read_rows(self.write('synthetic_bad_header.csv', text), 'predictions')
            self.assertIn(expected, str(caught.exception))
        with self.assertRaises(benchmark.BenchmarkError):
            benchmark.read_rows(self.dir / 'absent.csv', 'predictions')

    def test_command_writes_report_and_fails_clearly(self):
        reference = self.write('synthetic_reference.csv', table(line('STATE', A, SILAGE, '200')))
        predictions = self.write('synthetic_predictions.csv', table(line('STATE', A, SILAGE, '150')))
        out = self.dir / 'report.json'
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = cli.main(['--reference', str(reference), '--predictions', str(predictions), '--out', str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())['status_counts']['scored'], 1)
        report = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(report['comparisons'][0]['signed_error'], -50)
        self.assertIsNone(report['reference']['matches_recorded'])  # no .source.json beside a synthetic file
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = cli.main(['--reference', str(reference), '--predictions', str(self.dir / 'absent.csv')])
        self.assertEqual(code, 2)
        self.assertIn('error:', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
