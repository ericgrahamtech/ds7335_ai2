"""Fantasy football league analyzer: custom scoring, historical ranks, projections."""
import pandas as pd
import streamlit as st

from projections import project_next_season
from scoring import DEFAULT_RULES, add_derived_stats, season_totals

POSITIONS = ["QB", "RB", "WR", "TE"]

RULE_LABELS = {
    "passing_yards": "Per passing yard",
    "passing_tds": "Passing TD",
    "passing_interceptions": "Interception thrown",
    "rushing_yards": "Per rushing yard",
    "rushing_tds": "Rushing TD",
    "receptions": "Reception",
    "receiving_yards": "Per receiving yard",
    "receiving_tds": "Receiving TD",
    "fumbles_lost": "Fumble lost",
    "two_point_conversions": "2-pt conversion",
    "special_teams_tds": "Special teams TD",
}

st.set_page_config(page_title="League Analyzer", layout="wide")


@st.cache_data
def load_stats():
    df = pd.read_parquet("data/player_stats.parquet")
    df = df[(df["season_type"] == "REG") & (df["position"].isin(POSITIONS))]
    return add_derived_stats(df)


@st.cache_data
def load_projections():
    return project_next_season()


df = load_stats()

# ---- sidebar: league settings ----
st.sidebar.header("Scoring rules")
rules = {}
for stat, default in DEFAULT_RULES.items():
    step = 0.01 if abs(default) < 1 else 0.5
    rules[stat] = st.sidebar.number_input(
        RULE_LABELS[stat], value=default, step=step, format="%.2f"
    )

st.sidebar.header("Roster slots")
teams = st.sidebar.number_input("Teams in league", 2, 20, 12)
slots = {}
for pos, default in [("QB", 1), ("RB", 2), ("WR", 2), ("TE", 1), ("FLEX", 1)]:
    slots[pos] = st.sidebar.number_input(f"{pos} slots", 0, 5, default)

st.title("Fantasy League Analyzer")
proj = load_projections()
proj_year = int(proj["projected_season"].iloc[0])
tab_hist, tab_proj = st.tabs(["Season rankings", f"{proj_year} projections"])

# ---- historical rankings ----
with tab_hist:
    totals = season_totals(df, rules)
    season = st.selectbox("Season", sorted(totals["season"].unique(), reverse=True))
    year = totals[totals["season"] == season].sort_values("points", ascending=False).copy()

    # flag the starter pool implied by the roster settings
    year["starter"] = False
    for pos in POSITIONS:
        idx = year[year["position"] == pos].nlargest(teams * slots[pos], "points").index
        year.loc[idx, "starter"] = True
    flex = year[~year["starter"] & year["position"].isin(["RB", "WR", "TE"])]
    year.loc[flex.nlargest(teams * slots["FLEX"], "points").index, "starter"] = True

    query = st.text_input("Player search", placeholder="e.g. Tyreek Hill")
    if query:
        hits = year[year["player_display_name"].str.contains(query, case=False, regex=False)]
        if hits.empty:
            st.warning(f"No {season} match for '{query}'")
        for _, r in hits.head(5).iterrows():
            st.markdown(
                f"**{r['player_display_name']}** — {r['points']:.1f} pts, "
                f"{r['position']}{r['pos_rank']}, #{r['overall_rank']} overall "
                f"({r['games']} games, {r['ppg']:.1f} ppg)"
            )

    pos_filter = st.multiselect("Positions", POSITIONS, default=POSITIONS, key="hist_pos")
    table = year[year["position"].isin(pos_filter)]

    n_starters = int(year["starter"].sum())
    st.caption(
        f"{len(table)} players | starter pool under these settings: "
        f"{n_starters} ({teams} teams x {sum(slots.values())} lineup slots)"
    )
    st.dataframe(
        table[
            ["overall_rank", "player_display_name", "position", "pos_rank",
             "points", "games", "ppg", "starter"]
        ].round({"points": 1, "ppg": 1}),
        hide_index=True,
        width="stretch",
        column_config={
            "overall_rank": "#",
            "player_display_name": "Player",
            "position": "Pos",
            "pos_rank": "Pos rank",
            "points": "Points",
            "games": "G",
            "ppg": "PPG",
            "starter": "Starter pool",
        },
    )

# ---- next-season projections ----
with tab_proj:
    st.caption(
        "Linear models predict each stat category from last season's profile; "
        "your scoring rules are applied to the predicted stats. Changing rules "
        "in the sidebar re-scores instantly — no retraining."
    )
    p = proj.copy()
    p["proj_points"] = sum(p["pred_" + s] * v for s, v in rules.items())
    p = p.sort_values("proj_points", ascending=False)
    p["overall_rank"] = range(1, len(p) + 1)
    p["pos_rank"] = p.groupby("position")["proj_points"].rank(
        ascending=False, method="min"
    ).astype(int)

    pos_filter = st.multiselect("Positions", POSITIONS, default=POSITIONS, key="proj_pos")
    show = p[p["position"].isin(pos_filter)]

    st.dataframe(
        show[
            ["overall_rank", "player_display_name", "position", "pos_rank",
             "proj_points", "points", "pred_receptions", "pred_rushing_yards",
             "pred_receiving_yards", "pred_passing_yards"]
        ].round(1),
        hide_index=True,
        width="stretch",
        column_config={
            "overall_rank": "#",
            "player_display_name": "Player",
            "position": "Pos",
            "pos_rank": "Pos rank",
            "proj_points": f"Proj {proj_year} pts",
            "points": f"{proj_year - 1} pts",
            "pred_receptions": "Proj rec",
            "pred_rushing_yards": "Proj rush yds",
            "pred_receiving_yards": "Proj rec yds",
            "pred_passing_yards": "Proj pass yds",
        },
    )
