"""v2: predict each stat category, then score the predictions under any rules.

The point: one set of stat models serves every league. Changing the scoring
rules changes the projections with no retraining. Evaluated under standard PPR
and an alternate rule set (no PPR, 6-pt passing TDs) on the same time split
as v1: train 2011-2023 feature seasons, test 2024 features -> 2025 outcomes.
"""
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

from features import build_feature_table
from scoring import DEFAULT_RULES

TEST_SEASON = 2024

ALT_RULES = dict(DEFAULT_RULES, receptions=0.0, passing_tds=6.0)

table = build_feature_table()
feature_cols = ["age", "games", "points", "ppg"] + [
    c for c in table.columns if c.endswith("_pg")
]
X = pd.get_dummies(table[feature_cols + ["position"]], columns=["position"])
train = table["season"] < TEST_SEASON
test = table["season"] == TEST_SEASON

# one linear model per stat category (counts can't go below zero)
stat_preds = pd.DataFrame(index=table.index[test])
for stat in DEFAULT_RULES:
    m = LinearRegression().fit(X[train], table.loc[train, "target_" + stat])
    stat_preds[stat] = m.predict(X[test]).clip(min=0)


def report(rules, label):
    # actual/naive/predicted points under these rules, from stat totals
    actual = sum(table.loc[test, "target_" + s] * v for s, v in rules.items())
    naive = sum(table.loc[test, s] * v for s, v in rules.items())
    v2 = sum(stat_preds[s] * v for s, v in rules.items())

    # direct model retrained on points under these rules (what v1 would need to do)
    direct_y = sum(table.loc[train, "target_" + s] * v for s, v in rules.items())
    direct = LinearRegression().fit(X[train], direct_y).predict(X[test])

    print(f"\n{label}:")
    print(f"  v2 per-stat: MAE {mean_absolute_error(actual, v2):6.1f}   R^2 {r2_score(actual, v2):6.3f}")
    print(f"  direct MLR:  MAE {mean_absolute_error(actual, direct):6.1f}   R^2 {r2_score(actual, direct):6.3f}")
    print(f"  naive:       MAE {mean_absolute_error(actual, naive):6.1f}   R^2 {r2_score(actual, naive):6.3f}")


print(f"train rows: {train.sum():,}   test rows: {test.sum():,}")
report(DEFAULT_RULES, "standard PPR")
report(ALT_RULES, "alternate rules (no PPR, 6-pt pass TD) - v2 NOT retrained")
