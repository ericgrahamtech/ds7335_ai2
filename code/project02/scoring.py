"""Compute fantasy points from weekly stats under custom league scoring rules."""
import pandas as pd

# points per unit of each stat (standard PPR defaults)
DEFAULT_RULES = {
    "passing_yards": 0.04,
    "passing_tds": 4.0,
    "passing_interceptions": -2.0,
    "rushing_yards": 0.1,
    "rushing_tds": 6.0,
    "receptions": 1.0,
    "receiving_yards": 0.1,
    "receiving_tds": 6.0,
    "fumbles_lost": -2.0,
    "two_point_conversions": 2.0,
    "special_teams_tds": 6.0,
}


def add_derived_stats(df):
    """Combine the split fumble/2pt columns into the single stats leagues score on."""
    df = df.copy()
    df["fumbles_lost"] = (
        df["sack_fumbles_lost"] + df["rushing_fumbles_lost"] + df["receiving_fumbles_lost"]
    )
    df["two_point_conversions"] = (
        df["passing_2pt_conversions"]
        + df["rushing_2pt_conversions"]
        + df["receiving_2pt_conversions"]
    )
    return df


def weekly_points(df, rules):
    pts = pd.Series(0.0, index=df.index)
    for stat, value in rules.items():
        pts += df[stat].fillna(0) * value
    return pts


def season_totals(df, rules):
    """Aggregate weekly rows to one row per player-season with points and ranks."""
    df = df.copy()
    df["points"] = weekly_points(df, rules)
    out = df.groupby(
        ["player_id", "player_display_name", "position", "season"], as_index=False
    ).agg(points=("points", "sum"), games=("week", "nunique"))
    out["ppg"] = out["points"] / out["games"]
    out["overall_rank"] = (
        out.groupby("season")["points"].rank(ascending=False, method="min").astype(int)
    )
    out["pos_rank"] = (
        out.groupby(["season", "position"])["points"]
        .rank(ascending=False, method="min")
        .astype(int)
    )
    return out
