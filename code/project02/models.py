"""v1: multiple linear regression predicting next-season fantasy points.

Time-based split: train on 2011-2023 feature seasons, test on 2024 features
predicting 2025 points. Baseline: player repeats last season's total.
"""
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

from features import POSITIONS, build_feature_table

TEST_SEASON = 2024

table = build_feature_table()
feature_cols = ["age", "games", "points", "ppg"] + [
    c for c in table.columns if c.endswith("_pg")
]
X = pd.get_dummies(table[feature_cols + ["position"]], columns=["position"])

train = table["season"] < TEST_SEASON
test = table["season"] == TEST_SEASON

model = LinearRegression()
model.fit(X[train], table.loc[train, "target_points"])
pred = model.predict(X[test])

y_test = table.loc[test, "target_points"]
naive = table.loc[test, "points"]  # repeat last season

print(f"train rows: {train.sum():,}   test rows: {test.sum():,}")
print(f"MLR:   MAE {mean_absolute_error(y_test, pred):6.1f}   R^2 {r2_score(y_test, pred):6.3f}")
print(f"naive: MAE {mean_absolute_error(y_test, naive):6.1f}   R^2 {r2_score(y_test, naive):6.3f}")

print("\nper position (test season):")
results = table.loc[test, ["player_display_name", "position", "points", "target_points"]].copy()
results["pred"] = pred
for pos in POSITIONS:
    p = results[results["position"] == pos]
    print(
        f"  {pos}: MLR MAE {mean_absolute_error(p['target_points'], p['pred']):6.1f}   "
        f"naive MAE {mean_absolute_error(p['target_points'], p['points']):6.1f}   n={len(p)}"
    )

print("\nlargest coefficients:")
coefs = pd.Series(model.coef_, index=X.columns).sort_values(key=abs, ascending=False)
print(coefs.head(10).round(2).to_string())
