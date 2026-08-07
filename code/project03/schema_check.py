import json
import re
from datetime import datetime

import yaml

from pipeline import client

SNAPSHOT_FILE = "schema_snapshot.json"
CHANGELOG_FILE = "schema_changelog.json"


def load_changelog():
    try:
        with open(CHANGELOG_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def append_changelog(changes):
    log = load_changelog()
    version = datetime.now().isoformat(timespec="seconds")
    log.append({"version": version, "changes": changes})
    with open(CHANGELOG_FILE, "w") as f:
        json.dump(log, f, indent=2)
    return version


def current_layer_version():
    log = load_changelog()
    return log[-1]["version"] if log else "0"


def get_schema(con):
    rows = con.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "ORDER BY table_name, ordinal_position"
    ).fetchall()
    schema = {}
    for t, c, d in rows:
        schema.setdefault(t, {})[c] = d
    return schema


def load_snapshot():
    with open(SNAPSHOT_FILE) as f:
        return json.load(f)


def save_snapshot(schema):
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(schema, f, indent=2)


def diff_schemas(old, new):
    changes = []
    for t in sorted(new.keys() - old.keys()):
        changes.append(f"table added: {t}")
    for t in sorted(old.keys() - new.keys()):
        changes.append(f"table removed: {t}")
    for t in sorted(old.keys() & new.keys()):
        oc, nc = old[t], new[t]
        for c in sorted(nc.keys() - oc.keys()):
            changes.append(f"column added: {t}.{c} ({nc[c]})")
        for c in sorted(oc.keys() - nc.keys()):
            changes.append(f"column removed: {t}.{c}")
        for c in sorted(oc.keys() & nc.keys()):
            if oc[c] != nc[c]:
                changes.append(f"type changed: {t}.{c} {oc[c]} -> {nc[c]}")
    return changes


def check_queries(con):
    # EXPLAIN every verified query and saved report against the live schema
    checks = []
    with open("semantic_layer.yaml") as f:
        layer = yaml.safe_load(f)
    for vq in layer.get("verified_queries", []):
        checks.append(("verified query: " + vq["question"], vq["sql"]))
    try:
        with open("reports.json") as f:
            reports = json.load(f)
    except FileNotFoundError:
        reports = []
    for r in reports:
        checks.append(("saved report: " + r["name"], r["sql"]))

    results = []
    for label, sql in checks:
        try:
            con.execute("EXPLAIN " + sql)
            results.append((label, None))
        except Exception as e:
            results.append((label, str(e).splitlines()[0]))
    return results


def draft_update(changes, check_results, model="claude-sonnet-5"):
    with open("semantic_layer.yaml") as f:
        current = f.read()
    broken = [f"- {label}: {err}" for label, err in check_results if err]
    prompt = f"""Our database schema has changed. Update the semantic layer to match.

Current semantic layer:
```yaml
{current}
```

Schema changes detected:
{chr(10).join('- ' + c for c in changes)}

Queries now failing against the new schema:
{chr(10).join(broken) if broken else '- none'}

Return the complete updated semantic layer in a ```yaml code block.
- Update table/column references and fix any verified queries that now fail.
- For new columns, add a brief factual description; if the business meaning is not
  obvious from the name, mark it 'TODO: confirm meaning with data team'.
- Do not change metric definitions unless a schema change forces it."""
    resp = client().messages.create(
        model=model, max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    m = re.search(r"```yaml\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()
