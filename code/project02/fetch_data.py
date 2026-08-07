"""One-time data pull via nflreadpy: weekly player stats + rosters (for birthdates)."""
from pathlib import Path

import nflreadpy as nfl

SEASONS = list(range(2011, 2026))

stats = nfl.load_player_stats(SEASONS).to_pandas()
rosters = nfl.load_rosters(SEASONS).to_pandas()
rosters = rosters[["season", "gsis_id", "birth_date"]].dropna(subset=["gsis_id"])

Path("data").mkdir(exist_ok=True)
stats.to_parquet("data/player_stats.parquet")
rosters.to_parquet("data/rosters.parquet")

print(f"stats: {len(stats):,} rows, seasons {stats['season'].min()}-{stats['season'].max()}")
print(f"rosters: {len(rosters):,} rows")
