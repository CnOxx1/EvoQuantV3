# Real PIT multi-band experiment results

- PIT archive: **2025-06-30 → 2026-08-03**, 4000 rows
- Band ready rates: `{'exchange': 0.9975, 'news': 0.0075, 'event_calendar': 0.0, 'onchain': 0.0, 'tokenomics': 0.0, 'options': 0.0, 'alternative': 1.0, 'macro': 1.0}`
- IS/OOS cut: **2026-01-16**
- Frozen: `{'ac_thr': 0.35000000000000003, 'c_thr': 0.35, 'is_ce': 0.15078787765302026, 'is_abstain': 0.3005, 'is_sharpe': 0.8155384049246936, 'casc_only_thr': 0.7, 'wmi_thr': 0.2}`
- Bootstrap: circular block, n_boot=999, block=5 trading days

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

## OOS block-bootstrap contrasts

| contrast                    |   n_days |   dSharpe |    dCE |   p_Sharpe |   p_CE |   n_boot |   block |   ci_dSharpe_05 |   ci_dSharpe_95 |   ci_dCE_05 |   ci_dCE_95 | ci95_excludes_0_CE   | ci95_excludes_0_Sharpe   |
|:----------------------------|---------:|----------:|-------:|-----------:|-------:|---------:|--------:|----------------:|----------------:|------------:|------------:|:---------------------|:-------------------------|
| Thick ungated − Always long |      200 |    2.798  | 1.6311 |      0.272 |  0.272 |      999 |       5 |         -1.8665 |          7.7607 |     -0.9632 |      4.4358 | False                | False                    |
| ACWMI − Always long         |      200 |    2.2999 | 1.3553 |      0.326 |  0.298 |      999 |       5 |         -2.4011 |          7.2067 |     -1.0905 |      3.8543 | False                | False                    |
| ACWMI − Momentum always     |      200 |    0.8    | 0.4005 |      0.434 |  0.426 |      999 |       5 |         -1.2259 |          3.1373 |     -0.5859 |      1.4367 | False                | False                    |
| Thick ungated − ACWMI       |      200 |    0.4981 | 0.2758 |      0.286 |  0.3   |      999 |       5 |         -0.4405 |          1.4644 |     -0.2243 |      0.8187 | False                | False                    |
| ACWMI − WMI threshold (0.2) |      200 |    0.9009 | 0.1986 |      0.454 |  0.704 |      999 |       5 |         -1.5913 |          3.3203 |     -0.9472 |      1.3735 | False                | False                    |

## LOBO (durable bands)

| band_dropped   |   Sharpe |      CE |   abstain_rate |     dCE |   p_dCE |
|:---------------|---------:|--------:|---------------:|--------:|--------:|
| (none)         |    0.901 |  0.1986 |          0.297 |  0      | nan     |
| exchange       |   -0.232 | -0.1406 |          0.737 | -0.3391 |   0.4   |
| macro          |   -0.485 | -0.3358 |          0.572 | -0.5344 |   0.084 |
| alternative    |   -0.422 | -0.3272 |          0.522 | -0.5257 |   0.04  |

## Thin vs thick (real PIT statuses)

| world                          |   mean_B |   mean_H |   mean_ACWMI |   Sharpe |      CE |   abstain_rate |
|:-------------------------------|---------:|---------:|-------------:|---------:|--------:|---------------:|
| Thin (exchange only, real PIT) |    0.201 |    0.562 |        0.288 |   -0.004 | -0.0114 |          0.933 |
| Thick real PIT (ex+macro+alt…) |    0.356 |    0.688 |        0.415 |    1.399 |  0.4743 |          0     |
| Thick gated AC (real PIT)      |    0.356 |    0.688 |        0.415 |    0.901 |  0.1986 |          0.297 |

- Thick − Thin bootstrap: `{'n_days': 200, 'dSharpe': 1.4028, 'dCE': 0.4857, 'p_Sharpe': 0.48, 'p_CE': 0.442, 'n_boot': 999, 'block': 5, 'ci_dSharpe_05': -2.1223, 'ci_dSharpe_95': 3.9181, 'ci_dCE_05': -0.7917, 'ci_dCE_95': 1.7944, 'ci95_excludes_0_CE': False, 'ci95_excludes_0_Sharpe': False}`

## Mechanism (opened)

| component            | formula                                                                               | inputs                                                                               | role                              |
|:---------------------|:--------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------|:----------------------------------|
| cascade_p            | LiquidationCascadeCalculator.compute_cascade_probability(cluster, capacity, distance) | left-tail cluster intensity from pre-t returns; capacity=6e7; distance by vol regime | crisis / short trigger in R1      |
| systemic             | ContagionRiskCalculator.compute_systemic_risk_score([{covar_95, corr, tail_beta}])    | asset vs synthetic peer path from pre-t returns                                      | sign in consistency C             |
| S (signal integrity) | clip( hl_factor*(1-0.7*crowding_n)*(0.35+0.65*surprise_n) )                           | AlphaDecay half-life on cumsum(returns), crowding, surprise of last return           | ACWMI factor                      |
| C (consistency)      | pairwise sign-agreement among {mom5, flow_sign, -1_{casc>0.55}, -1_{sys>55}}          | mom5, VPIN/flow class, cascade_p, systemic                                           | ACWMI factor + AC abstention gate |
| detected_regime      | RegimeClassifier.classify_price_regime(RegimeFeatures) with crisis override           | returns, rolling vol, RSI/ADX proxies, cascade_p, vol_regime                         | R1/R2 branching                   |
| mom5                 | sign(mean(r_{t-5:t}))                                                                 | last 5 pre-t daily returns                                                           | R2/R3 directional fallback        |
| signal               | R1→-1; R2→+1; else sign(mom5) or 0                                                    | detected_regime, cascade_p, mom5                                                     | position when not abstaining      |

| detected_regime   |    n |   mean_cascade_p |   mean_S |   mean_C |   mean_signal |   share_long |   share_short |
|:------------------|-----:|-----------------:|---------:|---------:|--------------:|-------------:|--------------:|
| crisis            | 3546 |         0.869114 | 0.12504  | 0.582158 |     -1        |     0        |      1        |
| range             |  454 |         0.466054 | 0.137315 | 0.470999 |     -0.167401 |     0.361233 |      0.528634 |

## Notes
- Exchange/macro/alternative have durable DB history; news/onchain/options/tokenomics are mostly collection-day right-censored.
- Natural hard outages are rare in continuous OKX backfill; scarce-world states use bottom B_hier quintile for event study.
- Mechanism signal is the deterministic R1–R3 rule in `directional_signal` (no latent model).
- time_slice grid exported to table_timeslice_grid.csv (analytics snapshots still sparse historically).