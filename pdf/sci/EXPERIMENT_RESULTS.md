# JF/RFS-oriented experiment results

- Real returns: **2024-08-24 → 2026-08-03**, 10 assets, 7100 asset-days
- IS/OOS cut: **2025-08-14** (thresholds frozen on IS only)
- Frozen params: `{'ac_thr': 0.55, 'c_thr': 0.25, 'is_ce': -0.35889939395545356, 'is_abstain': 0.4546478873239437, 'is_sharpe': -0.13111572641996067, 'casc_only_thr': 0.7, 'wmi_thr': 0.2}`

## OOS economic value

| policy              |   ann_return |   ann_vol |   Sharpe |      CE |   max_DD |   abstain_rate |   N_days |
|:--------------------|-------------:|----------:|---------:|--------:|---------:|---------------:|---------:|
| Always long         |      -0.7963 |    0.6299 |   -1.264 | -1.1984 |  -0.6758 |          0     |      355 |
| Momentum always     |      -0.3918 |    0.5228 |   -0.749 | -0.6667 |  -0.5504 |          0     |      355 |
| Thick ungated       |       0.7963 |    0.6299 |    1.264 |  0.4014 |  -0.2792 |          0     |      355 |
| Simple outage rule  |       0.5436 |    0.6192 |    0.878 |  0.1623 |  -0.3427 |          0.085 |      355 |
| Simple cascade rule |       0.2527 |    0.119  |    2.123 |  0.2389 |  -0.0452 |          0.915 |      355 |
| WMI threshold (0.2) |       0.7963 |    0.6299 |    1.264 |  0.4014 |  -0.2792 |          0     |      355 |
| ACWMI (IS-frozen)   |       0.3256 |    0.5621 |    0.579 |  0.011  |  -0.3616 |          0.217 |      355 |

## Leave-one-band-out

| band_dropped   |   Sharpe |      CE |   abstain_rate |     dCE |
|:---------------|---------:|--------:|---------------:|--------:|
| (none)         |    0.579 |  0.011  |          0.217 |  0      |
| exchange       |    0.354 | -0.0739 |          0.347 | -0.0849 |
| news           |    0.401 | -0.0631 |          0.284 | -0.0741 |
| event_calendar |    0.493 | -0.0186 |          0.273 | -0.0297 |
| onchain        |    0.401 | -0.0631 |          0.284 | -0.0741 |
| tokenomics     |    0.493 | -0.0186 |          0.273 | -0.0297 |
| options        |    0.506 | -0.0118 |          0.269 | -0.0228 |
| alternative    |    0.603 |  0.028  |          0.234 |  0.017  |
| macro          |    0.52  | -0.0104 |          0.254 | -0.0214 |

## Thin vs thick

| world                |   mean_B |   mean_H |   mean_ACWMI |   Sharpe |      CE |   abstain_rate |
|:---------------------|---------:|---------:|-------------:|---------:|--------:|---------------:|
| Thin (exchange only) |    0.269 |    0.877 |        0.514 |   -0.24  | -0.1918 |          0.721 |
| Thick ungated        |    0.914 |    0.364 |        0.502 |    1.264 |  0.4014 |          0     |
| Thick gated (AC)     |    0.914 |    0.798 |        0.607 |    0.579 |  0.011  |          0.217 |

## Conditional signal value (OOS)

| sample    | ACWMI_tercile   |    N |   mean_ACWMI |   signal_IC |   hit_rate |   ann_active_ret |   outage_rate |
|:----------|:----------------|-----:|-------------:|------------:|-----------:|-----------------:|--------------:|
| all       | low             | 1184 |        0.518 |     0.00515 |      0.575 |           1.8812 |         0.247 |
| all       | mid             | 1183 |        0.597 |     0.00281 |      0.568 |           1.025  |         0.006 |
| all       | high            | 1183 |        0.706 |    -0.00142 |      0.495 |          -0.5182 |         0     |
| no_outage | low             | 1084 |        0.545 |     0.00367 |      0.534 |           1.3408 |         0     |
| no_outage | mid             | 1082 |        0.606 |     0.00227 |      0.571 |           0.8288 |         0     |
| no_outage | high            | 1084 |        0.712 |    -0.00106 |      0.504 |          -0.3878 |         0     |

## Notes

- Returns are real Yahoo daily crypto returns; signals use only pre-t history (PIT).
- Thresholds frozen on IS (Sharpe max, abstain rate in [5%, 55%]).
- Availability shocks O_t are Bernoulli and constructed return-orthogonal for identification.
- Multi-band historical archives are not in-repo; readiness layers use production band weights/WMI code.
- Stepping-stone toward full vintaged multi-source PIT via `logic_layer/time_slice`.