# Decline-date rule baseline

One transparent rule on the date of sustained NDVI decline, scored on the same 44 held-out
BARC field-years and the same field folds as the logistic regression. The day-of-year
threshold is fitted on training fields only; the 0.25 NDVI drop was fixed beforehand.

| Metric | Decline rule | Logistic regression | Always Grain |
| --- | ---: | ---: | ---: |
| Silage precision | 0.3929 | 0.8750 | 0.0000 |
| Silage recall | 0.9167 | 0.5833 | 0.0000 |
| Silage F1 | 0.5500 | 0.7000 | 0.0000 |
| False positive rate | 0.5312 | 0.0312 | 0.0000 |
| Balanced accuracy | 0.6927 | 0.7760 | 0.5000 |

Decline rule confusion (rows true, columns predicted): Grain 15 / 17, Silage 1 / 11.
Thresholds by fold (day of year): {1: 260, 2: 261, 3: 261, 4: 261, 5: 261}.
0 field-years had no sustained decline in the season and are called Grain.

## Limits

- Exploratory comparison on already-inspected BARC data; not an independent test.
- Twelve Silage field-years: differences of one or two rows are not distinguishable.
- An early NDVI decline is a hypothesis about harvest timing, not proof of silage.
- Cloud gaps can delay or hide the decline date; no residue (SWIR) evidence is used.
