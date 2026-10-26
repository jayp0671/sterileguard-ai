# 0005. Forecast range and central estimate

- Status: proposed (needs Leo's review)
- Date: 2026-10-25
- Deciders: Jay, Leo
- Ticket: SG-13

## Context and problem statement

SG-13 asks for HistGradientBoosting quantile regressors at 0.1, 0.5 and 0.9 with the same
monotonic constraints as the main model, served as p10, p50 and p90. Two problems turned up on
the 5,000-day calibrated dataset with scikit-learn 1.9.1:

1. **The p10 model never trains.** A quarter of simulated days have exactly 0 overtime hours, so
   the starting value of the 0.1-quantile model (the 10th percentile of the target, 0) ties with
   those rows, and boosting never moves off it. The p10 model predicted 0 for every day, and the
   80% band covered 87% of the holdout. A minimal repro (`y = max(0, x + noise)`) shows the same
   behavior; adding sub-second noise to the target fixes it.
2. **Quantile models break the monotonic constraints.** For quantile loss, scikit-learn re-fits
   leaf values to residual quantiles after each tree is grown, and that step ignores the
   constraints. On 200 holdout rows, adding one staff member raised the quantile median by up to
   2.5 hours (93 of 1,400 bumps). The squared-error model had none. The plan promises that
   adding staff can never raise predicted overtime (§12.3), and SG-17 gates on it.

## Considered options

1. Quantile models as written; accept the stuck p10 and the violations.
2. Seeded target jitter for the bound models, and a squared-error model as the central estimate.
3. Conformalized quantile regression to fix coverage, keeping the quantile median.
4. Another library (LightGBM) with constrained quantile objectives.

## Decision outcome

Chosen option 2:

- p10 and p90 stay quantile-loss models with the same monotonic constraints. Their training
  target gets a seeded uniform jitter of at most 0.01 hours (`TIE_JITTER`), which breaks the ties.
  `combine_quantiles` subtracts it again and clips at 0.
- The central estimate (stored as `pipeline_p50`, shown as "most likely") is the squared-error
  HistGradientBoosting model, which keeps the constraints exactly. The quantile median is still
  trained and reported (`hgb_q50`) for comparison.
- The bounds are widened to contain the central estimate (`p10 = min(p10, p50)`,
  `p90 = max(p90, p50)`) instead of sorting, so the central estimate is never replaced by a bound
  and stays monotone.
- Optuna tunes the served central estimate (mean CV MAE), not the quantile median.

Option 3 did not help: conformity scores are mostly exactly 0 on zero-overtime days, so the
adjustment came out as 0. Option 4 adds a dependency, and constrained quantile objectives there
have their own caveats.

Results (tuned run `20261026-000220-full-s42`, time-ordered holdout of 1,000 days): central MAE
0.819 h against 1.909 h for the best baseline (Ridge), a 57% improvement. 80% coverage is 0.804,
with a mean width of 2.5 h. The quantile median had a slightly lower MAE (0.721) but is not
monotone.

### Consequences

- Good: the served estimate respects "more staff never means more predicted overtime"; the band
  has the intended coverage; training stays deterministic (the jitter is seeded).
- Bad: "p50" is a conditional mean, not a median. The UI says "most likely", which fits either.
  The bounds themselves are not guaranteed monotone, so the gates check the central estimate
  only, as SG-17 specifies.
- Revisit if a scikit-learn release fixes either behavior.

## Links

- Plan section: §12.3, §12.4
- Code: `packages/ml/src/sg_ml/models.py` (`QuantileModel`, `combine_quantiles`)
