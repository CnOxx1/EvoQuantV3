# Real PIT multi-band experiment results

- PIT archive: **2025-06-30 → 2026-08-03**, 4000 rows
- Band ready rates: `{'exchange': 0.9975, 'news': 0.0075, 'event_calendar': 0.0, 'onchain': 0.0, 'tokenomics': 0.0, 'options': 0.0, 'alternative': 1.0, 'macro': 1.0}`
- IS/OOS cut: **2026-01-16**
- Frozen: `{'ac_thr': 0.35000000000000003, 'c_thr': 0.35, 'is_ce': 0.15078787765302026, 'is_abstain': 0.3005, 'is_sharpe': 0.8155384049246936, 'casc_only_thr': 0.7, 'wmi_thr': 0.2}`

## OOS economic value

| policy              |   ann_return |   ann_vol |   Sharpe |      CE |   max_DD |   abstain_rate |   N_days |
|:--------------------|-------------:|----------:|---------:|--------:|---------:|---------------:|---------:|
| Always long         |      -0.8164 |    0.5836 |   -1.399 | -1.1568 |  -0.4661 |          0     |      200 |
| Momentum always     |       0.0506 |    0.5009 |    0.101 | -0.2019 |  -0.4997 |          0     |      200 |
| Thick ungated       |       0.8164 |    0.5836 |    1.399 |  0.4743 |  -0.2792 |          0     |      200 |
| Simple outage rule  |       0.8164 |    0.5836 |    1.399 |  0.4743 |  -0.2792 |          0     |      200 |
| Simple cascade rule |       0      |    0      |    0     |  0      |   0      |          1     |      200 |
| WMI threshold (0.2) |       0      |    0      |    0     |  0      |   0      |          1     |      200 |
| ACWMI (IS-frozen)   |       0.454  |    0.5039 |    0.901 |  0.1986 |  -0.3398 |          0.297 |      200 |

## LOBO (durable bands)

| band_dropped   |   Sharpe |      CE |   abstain_rate |     dCE |
|:---------------|---------:|--------:|---------------:|--------:|
| (none)         |    0.901 |  0.1986 |          0.297 |  0      |
| exchange       |   -0.232 | -0.1406 |          0.737 | -0.3391 |
| macro          |   -0.485 | -0.3358 |          0.572 | -0.5344 |
| alternative    |   -0.422 | -0.3272 |          0.522 | -0.5257 |

## Thin vs thick (real PIT statuses)

| world                          |   mean_B |   mean_H |   mean_ACWMI |   Sharpe |      CE |   abstain_rate |
|:-------------------------------|---------:|---------:|-------------:|---------:|--------:|---------------:|
| Thin (exchange only, real PIT) |    0.201 |    0.562 |        0.288 |   -0.004 | -0.0114 |          0.933 |
| Thick real PIT (ex+macro+alt…) |    0.356 |    0.688 |        0.415 |    1.399 |  0.4743 |          0     |
| Thick gated AC (real PIT)      |    0.356 |    0.688 |        0.415 |    0.901 |  0.1986 |          0.297 |

## Notes
- Exchange/macro/alternative have durable DB history; news/onchain/options/tokenomics are mostly collection-day right-censored.
- Natural hard outages are rare in continuous OKX backfill; scarce-world states use bottom B_hier quintile for event study.
- time_slice grid exported to table_timeslice_grid.csv (analytics snapshots still sparse historically).