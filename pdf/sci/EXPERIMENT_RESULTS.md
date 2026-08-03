# Experiment outputs (project-grounded)

- Python files: **784**, LOC ≈ **134039**
- Data domains: **43**, logic modules: **39**, audit bands: **13**
- Panel: **180** days × **10** assets

## Regime summary

| regime   |    N |   WMI_mean |   ACWMI_mean |   abstain_wmi |   abstain_ac |   unsafe_wmi |   unsafe_ac |   cascade_p |   C_mean |   S_mean |
|:---------|-----:|-----------:|-------------:|--------------:|-------------:|-------------:|------------:|------------:|---------:|---------:|
| crisis   | 1000 |     0.5041 |       0.5459 |        0.19   |       1      |         0.81 |           0 |      0.8591 |   0.8816 |   0.0745 |
| range    |  430 |     0.6851 |       0.4697 |        0.0465 |       0.0465 |         0    |           0 |      0.2705 |   0.4419 |   0.0547 |
| trend    |  370 |     0.681  |       0.4254 |        0.0541 |       0.2703 |         0    |           0 |      0.3662 |   0.4751 |   0.0604 |

## Detection metrics (planted events)

| task              |   accuracy |   precision |   recall |     f1 |   support_pos |
|:------------------|-----------:|------------:|---------:|-------:|--------------:|
| crisis_detection  |     0.7161 |      0.6664 |   0.979  | 0.793  |          1000 |
| cascade_detection |     0.8944 |      0.81   |   1      | 0.895  |           810 |
| regime_match      |     0.7156 |      0.7156 |   0.7156 | 0.7156 |          1800 |

## Outage contrasts

| regime   |   outage |   N |    WMI |   ACWMI |   cascade_p |   detect_cascade |   abstain_ac |   unsafe_ac |   unsafe_wmi |
|:---------|---------:|----:|-------:|--------:|------------:|-----------------:|-------------:|------------:|-------------:|
| crisis   |        0 | 810 | 0.5995 |  0.5789 |      0.9275 |                1 |       1      |           0 |            1 |
| crisis   |        1 | 190 | 0.0975 |  0.4055 |      0.5675 |                1 |       1      |           0 |            0 |
| range    |        0 | 410 | 0.7104 |  0.4764 |      0.2738 |                0 |       0      |           0 |            0 |
| range    |        1 |  20 | 0.166  |  0.3334 |      0.2038 |                0 |       1      |           0 |            0 |
| trend    |        0 | 350 | 0.7104 |  0.4294 |      0.3738 |                0 |       0.2286 |           0 |            0 |
| trend    |        1 |  20 | 0.166  |  0.3555 |      0.2338 |                0 |       1      |           0 |            0 |

## Explanation-quality suite (EAR/UCR/EV/ECP)

| policy            |    N |   EAR |   UCR |    EV |   ECP_rate |
|:------------------|-----:|------:|------:|------:|-----------:|
| baseline / all    | 1800 | 0.677 | 0.323 | 0.032 |      0.101 |
| baseline / crisis | 1000 | 0.962 | 0.038 | 0.027 |      0.181 |
| AC-gated / all    | 1800 | 0.742 | 0.258 | 0.032 |      0.001 |
| AC-gated / crisis | 1000 | 1     | 0     | 0.027 |      0.002 |