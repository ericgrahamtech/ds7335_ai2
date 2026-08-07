"""Build the player-season feature table: season-N features, season-N+1 targets."""
import pandas as pd

from scoring import DEFAULT_RULES, add_derived_stats, season_totals

POSITIONS = ["QB", "RB", "WR", "TE"]

VOLUME_STATS = [
    "attempts", "passing_yards", "passing_tds", "passing_interceptions",
    "carries", "rushing_yards", "rushing_tds",
    "targets", "receptions", "receiving_yards", "receiving_tds",
]

# every stat a league can score (the keys of a rules dict)
SCORED_STATS = list(DEFAULT_RULES)


def build_feature_table(
    stats_path="data/player_stats.parquet",
    rosters_path="data/rosters.parquet",
    require_target=True,
):
    """One row per player-season. require_target=False keeps rows with no next
    season yet (NaN targets) so the latest season can be used for projections."""
    df = pd.read_parquet(stats_path)
    df = df[(df["season_type"] == "REG") & (df["position"].isin(POSITIONS))]
    df = add_derived_stats(df)

    # season totals: fantasy points (standard PPR) + every raw/scored stat
    points = season_totals(df, DEFAULT_RULES)
    stat_cols = VOLUME_STATS + [s for s in SCORED_STATS if s not in VOLUME_STATS]
    totals = df.groupby(["player_id", "season"], as_index=False)[stat_cols].sum()
    table = points.merge(totals, on=["player_id", "season"])

    for c in VOLUME_STATS:
        table[c + "_pg"] = table[c] / table["games"]

    # age at season start, from that season's roster birth date
    rosters = pd.read_parquet(rosters_path).drop_duplicates(["season", "gsis_id"])
    rosters["birth_date"] = pd.to_datetime(rosters["birth_date"])
    table = table.merge(
        rosters, left_on=["player_id", "season"], right_on=["gsis_id", "season"], how="left"
    )
    season_start = pd.to_datetime(table["season"].astype(str) + "-09-01")
    table["age"] = (season_start - table["birth_date"]).dt.days / 365.25
    table["age"] = table["age"].fillna(table["age"].median())
    table = table.drop(columns=["gsis_id", "birth_date"])

    # targets: the same player's points AND stat totals the FOLLOWING season.
    # shifting next season back one year lines it up with season-N features,
    # so every feature comes from season N and nothing later.
    nxt = table[["player_id", "season", "points"] + SCORED_STATS].copy()
    nxt["season"] -= 1
    nxt.columns = ["player_id", "season"] + [
        "target_" + c for c in ["points"] + SCORED_STATS
    ]
    how = "inner" if require_target else "left"
    table = table.merge(nxt, on=["player_id", "season"], how=how)

    # need a minimum of evidence in season N; fringe players are all noise
    table = table[table["games"] >= 4]
    return table.reset_index(drop=True)
