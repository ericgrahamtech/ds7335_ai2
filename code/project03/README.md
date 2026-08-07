# Ask Your Database

Natural-language questions over a TPC-H database, answered with generated,
validated SQL. See SPEC.md for design.

## Setup

```
pip install -r requirements.txt
cp .env.example .env        # then put your Anthropic API key in .env
python gen_data.py          # builds tpch.duckdb (~100MB, dates shifted to present)
```

## Run

```
streamlit run app.py                          # demo UI
python eval.py --model claude-haiku-4-5       # eval with semantic layer
python eval.py --model claude-sonnet-5 --no-semantic-layer   # baseline
```
