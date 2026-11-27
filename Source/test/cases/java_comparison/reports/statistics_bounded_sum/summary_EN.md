# PyFCS / Java — Bounded-sum membership equivalence

## Experimental setup

- PyFCS model: `basic_granular_complete_PyFCS.json`
- Model SHA-256: `98b3634cf78fb207976bd9af230d09dd28e621b38544e98cb1d8dcf3a5f07733`
- Java evaluation file: `evaluation_basic_granular_complete.json`
- Aggregation: BOUNDED_SUM in PyFCS; Java reference numerically consistent with bounded sum.
- RGB samples: 10,000,000 of 10,000,000 declared; unique RGB count unavailable.
- Categories: 13; membership comparisons: 130,000,000.
- Seed: 12345; absolute tolerance: 1e-06.
- Complete input validated: True.
- Engine: fast; fast/API checked maximum error: 1.3877788e-16.
- Recorded processing time (original evaluation run): 562.566 s.

## Global statistics

| Metric | Result |
|---|---:|
| MAE | 2.0947889e-16 |
| RMSE | 6.7258529e-16 |
| Maximum absolute error | 5.2291504e-14 |
| Mean signed error (PyFCS - Java) | 2.7365638e-17 |
| Active-membership MAE | 5.6051401e-16 |
| Active membership comparisons | 48,584,434 |
| Memberships within tolerance | 130,000,000 |
| Memberships outside tolerance | 0 |
| RGB samples entirely within tolerance | 10,000,000 |
| RGB samples outside tolerance | 0 |
| Identical winning sets (count) | 10,000,000 |
| Winning-set overlap (count) | 10,000,000 |
| Membership agreement | 100.000000% |
| Complete RGB agreement | 100.000000% |
| Winning-set agreement | 100.000000% |
| Winning-set overlap agreement | 100.000000% |

## Per-category statistics

| Category | MAE | RMSE | Maximum error | Active MAE | Agreement | Outside tolerance |
|---|---:|---:|---:|---:|---:|---:|
| Olive | 1.8011395e-16 | 5.6065149e-16 | 4.8849813e-15 | 7.2053536e-16 | 100.000000% | 0 |
| Brown | 1.5313823e-16 | 3.7640536e-16 | 4.4408921e-15 | 4.421655e-16 | 100.000000% | 0 |
| Red | 1.5007519e-16 | 4.818807e-16 | 7.4384943e-15 | 5.205092e-16 | 100.000000% | 0 |
| Pink | 2.2424038e-16 | 6.5229469e-16 | 1.2878587e-14 | 6.4772387e-16 | 100.000000% | 0 |
| Yellow-Green | 2.6220174e-16 | 6.7119266e-16 | 6.5503158e-15 | 5.3118814e-16 | 100.000000% | 0 |
| Orange | 1.6391806e-16 | 5.3998535e-16 | 9.3258734e-15 | 6.739517e-16 | 100.000000% | 0 |
| Green | 3.2318922e-16 | 8.890786e-16 | 9.8254738e-15 | 5.8305252e-16 | 100.000000% | 0 |
| Yellow | 1.6286311e-16 | 4.7764392e-16 | 7.7715612e-15 | 5.5226892e-16 | 100.000000% | 0 |
| Blue | 2.7260786e-16 | 7.8246003e-16 | 1.0880186e-14 | 5.3801227e-16 | 100.000000% | 0 |
| Gray | 3.7903196e-16 | 1.1676148e-15 | 4.4741988e-14 | 6.1614352e-16 | 100.000000% | 0 |
| White | 8.1672556e-17 | 4.2952145e-16 | 5.2291504e-14 | 5.5299803e-16 | 100.000000% | 0 |
| Black | 2.540011e-17 | 1.5948699e-16 | 1.4876989e-14 | 2.0379777e-16 | 100.000000% | 0 |
| Purple | 3.4477322e-16 | 9.060536e-16 | 2.5979219e-14 | 5.3255967e-16 | 100.000000% | 0 |

## Worst observed case

| Sample index (zero-based) | RGB | Category | Java | PyFCS | Absolute error |
|---:|---|---|---:|---:|---:|
| 6,888,611 | (241, 234, 232) | White | 0.92976861222037388 | 0.92976861222032159 | 5.2291504459844873e-14 |

## Interpretation and limitations

All evaluated bounded-sum memberships agree with the Java reference within the specified tolerance.

The observed discrepancies are consistent with double-precision rounding. The exact operation responsible cannot be determined from aggregated reports alone.

These results concern aggregated memberships for the evaluated model and samples, not all possible RGB values, individual granule memberships, or exact equality of all geometric volumes.

The Java aggregation is not explicitly identified in the available evaluation metadata. Only bounded-sum equivalence is reported here.

## Metric definitions

- MAE = mean absolute membership difference; RMSE = root mean squared difference.
- Bias = mean(PyFCS - Java). Active comparisons have Java > 0 or PyFCS > 0; active MAE is weighted by active counts.
- Membership agreement means absolute error <= tolerance. Complete RGB agreement requires every category to agree.
- Winning sets include positive memberships within tolerance of the largest membership; all-zero vectors have empty sets. Overlap counts at least one shared winner or two empty sets.
- All global category averages use equal sample counts. Counts are recovered from fractions and verified against per-category totals.
- No raw error distribution, percentiles, unique RGB count or per-granule data can be recovered from these aggregate files.

## Provenance

- JSON input SHA-256: `f699658d5aa216d43c82409f79bccd6dd7a860a4072fa92372eaae19ecb693ea`
- CSV input SHA-256: `af59b1fece9542aedc516ac2b2ceb42e5ddb7424e89ec310ad9b2c0ce772bf7a`
- Bounded-sum JSON and CSV per-category statistics checked for exact numeric agreement.
- Processing time is the recorded evaluation-loop time, not a controlled benchmark or a standalone bounded-sum timing.

