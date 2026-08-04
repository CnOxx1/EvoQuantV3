# Real PIT multi-band experiment results

- PIT archive: **2025-07-01 → 2026-08-03**, 3990 rows
- Band ready rates: `{'exchange': 0.8030075187969925, 'news': 0.0, 'event_calendar': 0.0, 'onchain': 0.0, 'tokenomics': 0.0, 'options': 0.0, 'alternative': 1.0, 'macro': 1.0}`
- IS/OOS cut: **2026-01-16**
- Frozen: `{'ac_thr': 0.25, 'c_thr': 0.25, 'is_ce': -0.4467303855536908, 'is_abstain': 0.05628140703517588, 'is_sharpe': -0.2603324435708088, 'casc_only_thr': 0.7, 'wmi_thr': 0.2}`
- Bootstrap: circular block, n_boot=999, block=5 trading days

## OOS economic value

| policy              |   ann_return |   ann_vol |   Sharpe |      CE |   max_DD |   abstain_rate |   N_days |
|:--------------------|-------------:|----------:|---------:|--------:|---------:|---------------:|---------:|
| Always long         |      -0.8164 |    0.5836 |   -1.399 | -1.1568 |  -0.4661 |          0     |      200 |
| Momentum always     |       0.0506 |    0.5009 |    0.101 | -0.2019 |  -0.4997 |          0     |      200 |
| Thick ungated       |       0.3846 |    0.5012 |    0.767 |  0.132  |  -0.4378 |          0.075 |      200 |
| Simple outage rule  |      -0.0712 |    0.4432 |   -0.161 | -0.2699 |  -0.4378 |          0.438 |      200 |
| Simple cascade rule |       0.3846 |    0.5012 |    0.767 |  0.132  |  -0.4378 |          0.075 |      200 |
| WMI threshold (0.2) |       0      |    0      |    0     |  0      |   0      |          1     |      200 |
| ACWMI (IS-frozen)   |       0.3246 |    0.4967 |    0.654 |  0.0764 |  -0.4378 |          0.127 |      200 |

## OOS block-bootstrap contrasts

| contrast                    |   n_days | method   |   dSharpe |    dCE |   p_Sharpe |   p_CE |   n_boot |   block |   ci_dSharpe_05 |   ci_dSharpe_95 |   ci_dCE_05 |   ci_dCE_95 | ci95_excludes_0_CE   | ci95_excludes_0_Sharpe   |
|:----------------------------|---------:|:---------|----------:|-------:|-----------:|-------:|---------:|--------:|----------------:|----------------:|------------:|------------:|:---------------------|:-------------------------|
| Mechanism − Momentum        |      200 | circular |    0.6664 | 0.3339 |      0.034 |  0.034 |      999 |       5 |          0.0552 |          1.4781 |      0.028  |      0.6768 | True                 | True                     |
| Mechanism − Always long     |      200 | circular |    2.1664 | 1.2887 |      0.296 |  0.246 |      999 |       5 |         -2.2354 |          6.3169 |     -0.9963 |      3.5152 | False                | False                    |
| ACWMI − Always long         |      200 | circular |    2.0525 | 1.2332 |      0.326 |  0.264 |      999 |       5 |         -2.3153 |          6.1876 |     -1.1011 |      3.4577 | False                | False                    |
| ACWMI − Momentum always     |      200 | circular |    0.5526 | 0.2783 |      0.106 |  0.104 |      999 |       5 |         -0.1202 |          1.3873 |     -0.057  |      0.6342 | False                | False                    |
| Thick ungated − ACWMI       |      200 | circular |    0.1139 | 0.0556 |      0.2   |  0.232 |      999 |       5 |         -0.0675 |          0.3814 |     -0.0336 |      0.1673 | False                | False                    |
| ACWMI − WMI threshold (0.2) |      200 | circular |    0.6535 | 0.0764 |      0.576 |  0.906 |      999 |       5 |         -2.0541 |          3.2063 |     -1.2364 |      1.2439 | False                | False                    |

## LOBO (durable bands, content+gating deletion)

| band_dropped      |   Sharpe |      CE |   abstain_rate |     dCE |   p_dCE | policy        |
|:------------------|---------:|--------:|---------------:|--------:|--------:|:--------------|
| (none)            |    0.767 |  0.132  |          0.075 |  0      | nan     | thick_ungated |
| exchange          |    0.767 |  0.132  |          0.075 |  0      |   1     | thick_ungated |
| macro             |    0.101 | -0.2019 |          0     | -0.3339 |   0.034 | thick_ungated |
| alternative       |    0.101 | -0.2019 |          0     | -0.3339 |   0.034 | thick_ungated |
| macro+alternative |    0.101 | -0.2019 |          0     | -0.3339 |   0.034 | thick_ungated |

## LOBO decomposition (content vs gating channel)

| band              |   dCE_total |   p_total |   dCE_content |   p_content |   dCE_gating_residual |   p_gating_residual |   dCE_gating_standalone |   p_gating_standalone | telescope_ok   |   content_share_of_total |
|:------------------|------------:|----------:|--------------:|------------:|----------------------:|--------------------:|------------------------:|----------------------:|:---------------|-------------------------:|
| exchange          |      0      |     1     |      nan      |     nan     |                     0 |                   1 |                       0 |                     1 | True           |                      nan |
| macro             |     -0.3339 |     0.034 |       -0.3339 |       0.034 |                     0 |                   1 |                       0 |                     1 | True           |                        1 |
| alternative       |     -0.3339 |     0.034 |       -0.3339 |       0.034 |                     0 |                   1 |                       0 |                     1 | True           |                        1 |
| macro+alternative |     -0.3339 |     0.034 |       -0.3339 |       0.034 |                     0 |                   1 |                     nan |                   nan | True           |                        1 |

## Thin vs thick (real PIT statuses; thin deletes content AND gating)

| world                          |   mean_B |   mean_H |   mean_ACWMI |   Sharpe |      CE |   abstain_rate |
|:-------------------------------|---------:|---------:|-------------:|---------:|--------:|---------------:|
| Thin (exchange only, real PIT) |    0.123 |    0.538 |        0.165 |   -1.011 | -0.4037 |          0.614 |
| Thick real PIT (ex+macro+alt…) |    0.277 |    0.662 |        0.339 |    0.767 |  0.132  |          0.075 |
| Thick gated AC (real PIT)      |    0.277 |    0.662 |        0.339 |    0.654 |  0.0764 |          0.127 |

- Thick − Thin bootstrap: `{'n_days': 200, 'method': 'circular', 'dSharpe': 1.7781, 'dCE': 0.5357, 'p_Sharpe': 0.036, 'p_CE': 0.242, 'n_boot': 999, 'block': 5, 'ci_dSharpe_05': 0.1579, 'ci_dSharpe_95': 3.9295, 'ci_dCE_05': -0.434, 'ci_dCE_95': 1.4212, 'ci95_excludes_0_CE': False, 'ci95_excludes_0_Sharpe': True}`

## Block-length sensitivity

|   block |   thick_minus_thin_p_CE | thick_minus_thin_ci   |   acwmi_minus_long_p_CE | acwmi_minus_long_ci   |
|--------:|------------------------:|:----------------------|------------------------:|:----------------------|
|       5 |                   0.242 | [-0.434,1.4212]       |                   0.264 | [-1.1011,3.4577]      |
|      10 |                   0.254 | [-0.4047,1.3682]      |                   0.35  | [-1.3374,4.1243]      |
|      21 |                   0.212 | [-0.2853,1.373]       |                   0.326 | [-1.1576,4.0107]      |

## White (2000) reality check vs Always long

`{'benchmark': 'Always long', 'best_strategy': 'Thick ungated', 'max_dCE': 1.2887, 'p_reality_check': 0.144, 'n_boot': 999, 'block': 5, 'n_days': 200, 'deltas': {'Momentum always': 0.9549, 'Thick ungated': 1.2887, 'WMI threshold (0.2)': 1.1568, 'ACWMI (IS-frozen)': 1.2332}}`

## Transaction costs and funding

| policy            |   cost_bps | funding              |   Sharpe |      CE |
|:------------------|-----------:|:---------------------|---------:|--------:|
| Thick ungated     |          0 | no                   |    0.767 |  0.132  |
| Thick ungated     |         10 | no                   |    0.467 | -0.0191 |
| Thick ungated     |         25 | no                   |    0.017 | -0.246  |
| Thick ungated     |         50 | no                   |   -0.725 | -0.6251 |
| Thick ungated     |         10 | yes (where archived) |    0.467 | -0.0191 |
| ACWMI (IS-frozen) |          0 | no                   |    0.654 |  0.0764 |
| ACWMI (IS-frozen) |         10 | no                   |    0.357 | -0.0714 |
| ACWMI (IS-frozen) |         25 | no                   |   -0.086 | -0.2935 |
| ACWMI (IS-frozen) |         50 | no                   |   -0.818 | -0.6644 |
| ACWMI (IS-frozen) |         10 | yes (where archived) |    0.357 | -0.0714 |
| Momentum always   |          0 | no                   |    0.101 | -0.2019 |
| Momentum always   |         10 | no                   |   -0.198 | -0.3522 |
| Momentum always   |         25 | no                   |   -0.646 | -0.578  |
| Momentum always   |         50 | no                   |   -1.386 | -0.9552 |
| Momentum always   |         10 | yes (where archived) |   -0.198 | -0.3522 |
| Always long       |          0 | no                   |   -1.399 | -1.1568 |
| Always long       |         10 | no                   |   -1.402 | -1.1586 |
| Always long       |         25 | no                   |   -1.407 | -1.1613 |
| Always long       |         50 | no                   |   -1.415 | -1.1659 |
| Always long       |         10 | yes (where archived) |   -1.402 | -1.1586 |

## Regime-stratified OOS performance

| policy            | regime   |   n_asset_days |   share |   ann_mean_pnl |   hit_rate |
|:------------------|:---------|---------------:|--------:|---------------:|-----------:|
| Thick ungated     | crisis   |           1761 |   0.88  |         0.3083 |      0.476 |
| Thick ungated     | range    |            153 |   0.076 |         0.0793 |      0.516 |
| Thick ungated     | trend    |             86 |   0.043 |         2.4903 |      0.5   |
| ACWMI (IS-frozen) | crisis   |           1761 |   0.88  |         0.3083 |      0.476 |
| ACWMI (IS-frozen) | range    |            153 |   0.076 |         0.4823 |      0.275 |
| ACWMI (IS-frozen) | trend    |             86 |   0.043 |         0.3774 |      0.291 |

## Explanation / calibration metrics

`{'EAR': 1.0, 'UCR': 0.0, 'ECP_rate_detect_conf': 0.6882, 'ECP_rate_cascade_conf': 0.0, 'n_active_asset_days': 3752}`

## B_hier weight sensitivity (AC policy, frozen thresholds)

| weights_dom_band_asset   |   Sharpe |     CE |   abstain_rate |
|:-------------------------|---------:|-------:|---------------:|
| (0.25, 0.35, 0.4)        |    0.654 | 0.0764 |          0.127 |
| (0.15, 0.35, 0.5)        |    0.649 | 0.0744 |          0.127 |
| (0.35, 0.35, 0.3)        |    0.637 | 0.0682 |          0.126 |
| (0.333, 0.333, 0.333)    |    0.637 | 0.0682 |          0.126 |

## Mechanism (opened; band content in signals)

| component            | formula                                                                                                                                               | inputs                                                                               | role                                                                         |
|:---------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------|
| cascade_p            | LiquidationCascadeCalculator.compute_cascade_probability(cluster, capacity, distance)                                                                 | left-tail cluster intensity from pre-t returns; capacity=6e7; distance by vol regime | crisis / short trigger in R1                                                 |
| systemic             | ContagionRiskCalculator.compute_systemic_risk_score([{covar_95, corr, tail_beta}])                                                                    | asset vs synthetic peer path from pre-t returns                                      | sign in consistency C                                                        |
| S (signal integrity) | clip( hl_factor*(1-0.7*crowding_n)*(0.35+0.65*surprise_n) )                                                                                           | AlphaDecay half-life on cumsum(returns), crowding, surprise of last return           | ACWMI factor                                                                 |
| C (consistency)      | pairwise sign-agreement among {mom5, flow_sign, -1_{casc>0.55}, -1_{sys>55}}                                                                          | mom5, VPIN/flow class, cascade_p, systemic                                           | ACWMI factor + AC abstention gate                                            |
| detected_regime      | RegimeClassifier.classify_price_regime(RegimeFeatures) with crisis override                                                                           | returns, rolling vol, RSI/ADX proxies, cascade_p, vol_regime                         | R1/R2 branching                                                              |
| mom5                 | sign(mean(r_{t-5:t}))                                                                                                                                 | last 5 pre-t daily returns                                                           | R2/R3 directional fallback                                                   |
| macro_tilt           | +1 if VIX_5d_chg<0 and DXY_5d_chg<0; -1 if both>0; else 0; forced 0 when macro band not ready                                                         | vintaged macro_timeseries (available_at <= t): VIX, DXY                              | macro-band content: veto in R2, band-long in R2b, tie-break in R3, sign in C |
| alt_tilt             | sign(stablecoin_net_supply_change_7d at latest obs < t); forced 0 when alternative band not ready                                                     | alternative_timeseries stablecoin 7d net supply (pre-t)                              | alternative-band content: band-long in R2b, tie-break in R3, sign in C       |
| signal               | R1 (crisis AND casc>=0.60)→-1; R2→+1 (macro veto); R2b→+1 (band-driven); R3 sign(mom5) with double-risk-off long veto; ties sign(macro_tilt+alt_tilt) | detected_regime, cascade_p, mom5, macro_tilt, alt_tilt                               | position when not abstaining; R1 requires evidence conjunction               |

| detected_regime   |    n |   mean_cascade_p |    mean_S |   mean_C |   mean_macro_tilt |   mean_alt_tilt |   mean_signal |   share_long |   share_short |
|:------------------|-----:|-----------------:|----------:|---------:|------------------:|----------------:|--------------:|-------------:|--------------:|
| crisis            | 3266 |         0.316441 | 0.0809495 | 0.55497  |       -0.00979792 |      -0.0508267 |    -0.192897  |     0.369259 |      0.562156 |
| range             |  508 |         0.205636 | 0.13174   | 0.579659 |        0.0452756  |       0.456693  |     0.248031  |     0.622047 |      0.374016 |
| trend             |  216 |         0.21717  | 0.0695967 | 0.647222 |        0.180556   |       0.203704  |     0.0555556 |     0.5      |      0.444444 |

## Notes
- Exchange/macro/alternative have durable DB history; news/onchain/options/tokenomics are mostly collection-day right-censored.
- Band content (macro_tilt from vintaged VIX/DXY; alt_tilt from stablecoin 7d net supply) enters R2/R2b/R3 and C directly;
  tilts are forced to 0 whenever the band is not PIT-ready, so LOBO deletes content, not only gating.
- Natural hard outages are rare in continuous OKX backfill; scarce-world states use expanding B_hier quantile (no full-sample look-ahead).
- Hard O_t availability event study exported to table_ot_availability_event_study.csv.
- Joint macro+alternative LOBO and date-scrambled content placebo are reported.
- Macro component LOBO (VIX vs DXY), cost-aware pre-specified contrast, compilation-wedge bridge, planted O_t shocks exported.
- Mechanism signal is the deterministic R1–R3 rule in `directional_signal` (no latent model).
- Timing protocol: decision_at_prev_close (features at t-1 23:59; payoff = day-t close-to-close).
- Experiment config: `{'name': 'jf_rfs_pit_identification', 'version': '2.1.0', 'content_hash': '0451376393e1481a', 'path': '/workspace/pdf/sci/experiment_config.json', 'pre_specified_contrast': {'name': 'Mechanism − Momentum', 'treatment': 'Thick ungated', 'control': 'Momentum always', 'metric': 'CE'}, 'timing': {'protocol': 'decision_at_prev_close', 'decision_asof_offset_days': -1, 'decision_asof_clock': '23:59:00', 'payoff': 'same_calendar_day_close_to_close', 'notes': 'Position for calendar day t uses band statuses and content known at (t-1) 23:59; payoff is Yahoo close-to-close return on day t.'}}`.
- Selective prediction / ACWMI gating is secondary on this sparse archive (often equals ungated).
- time_slice grid exported to table_timeslice_grid.csv (analytics snapshots still sparse historically).