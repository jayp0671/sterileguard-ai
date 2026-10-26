# 0006. SHAP explainer and the staffing direction check

- Status: proposed (needs Leo's review; the SG-17 gate definition needs Carlos's review)
- Date: 2026-10-25
- Deciders: Jay, Leo, Carlos
- Ticket: SG-14 (and the shap_direction gate in SG-17)

## Context and problem statement

SG-14 asks for `shap.TreeExplainer` on the p50 model with a background sample of at most 200
synthetic rows, drivers that add up to p50 within 0.01 hours, and `shap_direction_check`
returning the mean SHAP value of each staffing feature, which the SG-17 gate requires to be
<= 0. With shap 0.54.1 and scikit-learn 1.9.1 three problems showed up:

1. **Native categorical splits.** HistGradientBoosting with `categorical_features` (day of week,
   academic event) gave SHAP values that were off by about 22 hours from the model output.
2. **Interventional SHAP.** With numeric-only trees and a 100 to 200 row background, the
   interventional algorithm was still off by about 0.6 hours. The tree-path-dependent algorithm
   was exact (error 0.0).
3. **Mean SHAP as a direction test.** SHAP values average to about zero over the data by
   construction, so a feature's mean SHAP is noise around 0 and says nothing about direction.
   On the tuned model, `sterilizers_up` had a mean SHAP of +0.062 even though the model is
   monotone-constrained in it and more sterilizers lower its contribution (slope -1.02 hours per
   sterilizer).

## Decision outcome

- The tree pipelines ordinal-encode categoricals and treat the codes as numbers (no native
  categorical splits). The accuracy cost on the holdout was negligible.
- Drivers use `TreeExplainer(model, feature_perturbation="tree_path_dependent")`, which is exactly
  additive. The background sample (200 training rows, simulated) is still saved in the artifact
  as `explainer_background`.
- `direction_check` reports both numbers per staffing feature: `mean_shap` (the ticket's measure)
  and `slope`, the least-squares slope of SHAP against the feature's value. **The SG-17
  `shap_direction` gate uses `slope <= 0`**, which is what plan §12.4 asks for ("SHAP shows
  staffing pushing overtime in the right direction"). This is a conflict with the ticket text
  and is flagged on the PR rather than resolved silently.

### Consequences

- Good: drivers plus the expected value equal the prediction to floating-point precision; the
  direction gate tests direction rather than noise.
- Bad: tree-path-dependent SHAP attributes credit along the tree's own paths, so correlated
  features (for example `capacity_ratio` and `demand_units_est`) can share credit differently
  than an interventional explanation would.

## Links

- Plan section: §12.4, §12.5
- Code: `packages/ml/src/sg_ml/explain.py`, `packages/ml/src/sg_ml/models.py`
