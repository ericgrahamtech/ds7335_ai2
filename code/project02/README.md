# Fantasy Calculator

A fantasy football league analyzer: score 15 seasons of NFL history under *your*
league's rules, and project next season — with projections that re-score
instantly when you change the rules.

## The idea

Most projection tools predict fantasy points under one fixed scoring system.
This app instead trains one linear model per **stat category** (yards, TDs,
receptions, interceptions...), then applies your league's scoring rules to the
predicted stats:

```
projected_points = Σ  pred_stat × your_rules[stat]
```

One set of stat models serves every league. Toggle PPR off or bump passing TDs
to 6 points in the sidebar, and every ranking — historical and projected —
recomputes with no retraining. `models_v2.py` shows this per-stat approach
matches a points-trained model under standard PPR and transfers to alternate
rule sets for free.

## Features

- **Custom scoring** — every rule (per-yard, TDs, turnovers, PPR, 2-pt) is a
  sidebar input; defaults are standard PPR
- **Historical ranks** — one row per player-season (2011–2025), points, PPG,
  overall and positional rank under your rules, with a starter-pool cutoff from
  your league's team count and roster slots
- **Next-season projections** — per-stat linear models trained on every
  completed season pair (features: age, games, per-game volume profile,
  position), scored under your rules

## Model notes

Time-based evaluation: train on 2011–2023 feature seasons, test on 2024
features predicting 2025 outcomes. Baselines: naive repeat-last-season and a
directly points-trained MLR (`models.py`). The per-stat ensemble matches the
direct model and beats naive, and — the point — transfers to any rule set
without retraining (`models_v2.py`). Counts are clipped at zero; players with
under 4 games in the feature season are dropped as noise.

## Quickstart

```bash
pip install -r requirements.txt
python fetch_data.py        # pulls weekly stats + rosters (2011-2025) via nflreadpy
streamlit run app.py
```

Model evaluation scripts print comparisons to stdout:

```bash
python models.py      # v1: points-trained MLR vs naive baseline
python models_v2.py   # v2: per-stat models, evaluated under two rule sets
```

## Layout

| File | Purpose |
|---|---|
| `fetch_data.py` | One-time data pull (nflreadpy → parquet) |
| `scoring.py` | Rules dict, derived stats, weekly/season point totals and ranks |
| `features.py` | Player-season feature table: season-N features, season-N+1 targets |
| `models.py` | v1: direct points regression + baseline comparison |
| `models_v2.py` | v2: per-stat models, rule-set transfer evaluation |
| `projections.py` | Trains per-stat models on all completed pairs, projects the upcoming season |
| `app.py` | Streamlit UI: scoring sidebar, historical ranks, projections |

## Limits

Linear models only — no injury, depth-chart, or team-context signal; rookie
seasons can't be projected (no season-N features); kickers and defenses aren't
scored. Data comes from the excellent [nflverse](https://github.com/nflverse)
project via `nflreadpy`.
