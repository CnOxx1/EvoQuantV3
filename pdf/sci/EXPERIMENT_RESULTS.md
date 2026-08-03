# Experiment outputs for SCI paper

- Data domains: **43**
- Logic modules: **39**
- Audit bands: **13**

## Regime summary

| regime   |    N |   WMI_mean |   ACWMI_mean |   H_cont_mean |   C_mean |   S_mean |   Q_mean |   EV_mean |   UCR_mean |   abstain_wmi_rate |   abstain_ac_rate |
|:---------|-----:|-----------:|-------------:|--------------:|---------:|---------:|---------:|----------:|-----------:|-------------------:|------------------:|
| crisis   |  486 |     0.4093 |       0.4655 |        0.7859 |   0.5317 |   0.0796 |   0.5432 |    0.4916 |     0.3044 |             0.0144 |            0.9465 |
| range    | 1008 |     0.6679 |       0.5915 |        0.7411 |   0.5601 |   0.2584 |   0.6067 |    0.444  |     0.3095 |             0      |            0.5635 |
| trend    |  666 |     0.6721 |       0.5527 |        0.7475 |   0.5613 |   0.2492 |   0.6026 |    0.4518 |     0.3093 |             0      |            0.8063 |

## Regression R²

| Model                         |     R2 |
|:------------------------------|-------:|
| Model A: WMI only             | 0.1154 |
| Model B: factor decomposition | 0.4838 |
| Model C: ACWMI                | 0.3448 |
| Model D: ACWMI + factors      | 0.4891 |

Figures saved under `pdf/figures/`, tables under `pdf/tables/`.