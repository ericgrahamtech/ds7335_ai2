"""Train per-stat models on every completed season pair, project the upcoming season."""
import pandas as pd
from sklearn.linear_model import LinearRegression

from features import build_feature_table
from scoring import DEFAULT_RULES


def project_next_season():
    """Predicted stat totals for next season, one row per player. Score them
    with any rules dict: points = sum(pred_<stat> * rules[stat])."""
    table = build_feature_table(require_target=False)
    feature_cols = ["age", "games", "points", "ppg"] + [
        c for c in table.columns if c.endswith("_pg")
    ]
    X = pd.get_dummies(table[feature_cols + ["position"]], columns=["position"])

    latest = table["season"].max()
    train = table["target_points"].notna()  # every completed N -> N+1 pair
    predict = table["season"] == latest

    out = table.loc[
        predict, ["player_id", "player_display_name", "position", "points", "games"]
    ].copy()
    for stat in DEFAULT_RULES:
        m = LinearRegression().fit(X[train], table.loc[train, "target_" + stat])
        out["pred_" + stat] = m.predict(X[predict]).clip(min=0)
    out["projected_season"] = latest + 1
    return out.reset_index(drop=True)
