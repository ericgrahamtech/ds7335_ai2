import difflib
import json
import os
from datetime import date, datetime

import duckdb
import pandas as pd
import streamlit as st

from pipeline import run_chat, narrate, standalone_question, DB_PATH, CONTEXT_WINDOW
from schema_check import (get_schema, load_snapshot, save_snapshot, diff_schemas,
                          check_queries, draft_update, load_changelog, append_changelog,
                          current_layer_version)

REPORTS_FILE = "reports.json"


def load_reports():
    if os.path.exists(REPORTS_FILE):
        with open(REPORTS_FILE) as f:
            return json.load(f)
    return []


def save_reports(reports):
    with open(REPORTS_FILE, "w") as f:
        json.dump(reports, f, indent=2)


CHATS_FILE = "chats.json"
TURN_KEYS = ["question", "sql", "error", "answer", "nrows", "preview",
             "latency", "tokens", "input_tokens", "rebuild_of"]


def load_chats():
    if os.path.exists(CHATS_FILE):
        with open(CHATS_FILE) as f:
            return json.load(f)
    return []


def save_chats(chats):
    with open(CHATS_FILE, "w") as f:
        json.dump(chats, f, indent=2)


def serialize_turn(t):
    d = {k: t.get(k) for k in TURN_KEYS}
    if t.get("df") is not None:
        # snapshot capped at 200 rows -- chat history is an archive, reports stay live
        d["df_json"] = json.loads(t["df"].head(200).to_json(orient="split", date_format="iso"))
    return d


def deserialize_turn(d):
    t = {k: d.get(k) for k in TURN_KEYS}
    t["df"] = None
    if d.get("df_json"):
        t["df"] = pd.DataFrame(d["df_json"]["data"], columns=d["df_json"]["columns"])
    return t


def autosave_chat():
    if not st.session_state.turns:
        return
    chats = load_chats()
    if st.session_state.get("chat_id") is None:
        st.session_state.chat_id = datetime.now().isoformat(timespec="seconds")
        chats.append({"id": st.session_state.chat_id,
                      "title": st.session_state.turns[0]["question"][:60],
                      "turns": []})
    for c in chats:
        if c["id"] == st.session_state.chat_id:
            c["turns"] = [serialize_turn(t) for t in st.session_state.turns]
    save_chats(chats)


st.set_page_config(page_title="Meridian Supply Co.", layout="wide")
st.title("Meridian Supply Co. — Ask Your Database")
st.markdown(
    "Since 1992, **Meridian Supply Co.** has distributed industrial parts to "
    "15,000 customers across 25 nations and 5 regions, sourced from 1,000 "
    "suppliers worldwide. Ask a question about the business in plain English — "
    "answers come from generated, validated SQL, never from the model's imagination."
)

with st.sidebar:
    model = st.selectbox("Model", ["claude-haiku-4-5", "claude-sonnet-5"])
    use_sl = st.toggle("Use semantic layer", value=True)
    if st.button("New conversation"):
        st.session_state.turns = []
        st.session_state.chat_id = None

if "turns" not in st.session_state:
    st.session_state.turns = []

with st.sidebar:
    last_ctx = next((t["input_tokens"] for t in reversed(st.session_state.turns)
                     if t.get("input_tokens")), 0)
    pct = last_ctx / CONTEXT_WINDOW
    st.progress(min(pct, 1.0), text=f"Context: {last_ctx:,} / {CONTEXT_WINDOW:,} tokens ({pct:.1%})")

    st.divider()
    st.write("**Chat history**")
    for c in reversed(load_chats()):
        col_t, col_d = st.columns([5, 1])
        active = c["id"] == st.session_state.get("chat_id")
        if col_t.button(c["title"] or "untitled", key=f"chat{c['id']}",
                        type="primary" if active else "secondary", use_container_width=True):
            st.session_state.turns = [deserialize_turn(d) for d in c["turns"]]
            st.session_state.chat_id = c["id"]
            st.rerun()
        if col_d.button("🗑️", key=f"chatdel{c['id']}"):
            save_chats([x for x in load_chats() if x["id"] != c["id"]])
            if active:
                st.session_state.turns = []
                st.session_state.chat_id = None
            st.rerun()

tab_chat, tab_reports, tab_admin = st.tabs(["Chat", "Saved Reports", "Admin"])

with tab_chat:
    for i, t in enumerate(st.session_state.turns):
        with st.chat_message("user"):
            st.write(t["question"])
        with st.chat_message("assistant"):
            if t["sql"]:
                with st.expander("Generated SQL"):
                    st.code(t["sql"], language="sql")
            if t["error"]:
                st.error(t["error"])
            else:
                st.write(t["answer"])
                if t.get("df") is not None:
                    st.dataframe(t["df"])
                    c1, c2 = st.columns([1, 6])
                    c1.download_button("Export to CSV", t["df"].to_csv(index=False).encode(),
                                       file_name=f"result_{i}.csv", mime="text/csv", key=f"csv{i}")
                    if t.get("rebuild_of") is not None:
                        if c2.button("Update saved report", key=f"upd{i}"):
                            reports = load_reports()
                            if t["rebuild_of"] < len(reports):
                                rep = reports[t["rebuild_of"]]
                                rep.setdefault("sql_history", []).append(rep["sql"])
                                rep["sql"] = t["sql"]
                                rep["built_against"] = current_layer_version()
                                rep["saved"] = str(date.today())
                                save_reports(reports)
                                st.toast(f"Report '{rep['name']}' updated")
                    elif c2.button("Save Report", key=f"savebtn{i}"):
                        with st.spinner("Writing standalone question..."):
                            sq = standalone_question(t["question"], st.session_state.turns[:i],
                                                     model=model)
                        st.session_state.pending_save = {"i": i, "question": sq, "sql": t["sql"]}
                        st.rerun()
            if st.session_state.get("pending_save", {}).get("i") == i:
                ps = st.session_state.pending_save
                st.markdown("**Save as report** — the question is stored standalone so the "
                            "report can be rebuilt without this conversation:")
                name = st.text_input("Report name", placeholder="Name this report...", key=f"ps_name{i}")
                sq = st.text_area("Standalone question", value=ps["question"], key=f"ps_q{i}")
                cc1, cc2 = st.columns([1, 6])
                if cc1.button("Confirm save", key="ps_ok"):
                    if not name.strip():
                        st.error("Please name the report before saving.")
                    else:
                        reports = load_reports()
                        reports.append({"name": name.strip(), "question": sq, "sql": ps["sql"],
                                        "saved": str(date.today()),
                                        "built_against": current_layer_version(),
                                        "sql_history": []})
                        save_reports(reports)
                        del st.session_state.pending_save
                        st.toast("Saved — see the Saved Reports tab")
                        st.rerun()
                if cc2.button("Cancel", key="ps_cancel"):
                    del st.session_state.pending_save
                    st.rerun()
            ctx = f", context {t['input_tokens'] / CONTEXT_WINDOW:.1%}" if t.get("input_tokens") else ""
            st.caption(f"{t['latency']:.1f}s, {t['tokens']} tokens{ctx}")

    question = st.chat_input("Ask about the business...")
    if question:
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"), st.spinner("Thinking..."):
            r = run_chat(question, st.session_state.turns, model=model, use_semantic_layer=use_sl)
            turn = {"question": question, "sql": r["sql"], "error": r["error"],
                    "answer": r["answer"], "df": None, "nrows": 0, "preview": "",
                    "latency": r["latency"], "tokens": r["tokens"]}
            if r["df"] is not None:
                turn["answer"] = narrate(question, r["df"])
                turn["df"] = r["df"]
                turn["nrows"] = len(r["df"])
                turn["preview"] = r["df"].head(5).to_string()
        st.session_state.turns.append(turn)
        autosave_chat()
        st.rerun()

with tab_reports:
    reports = load_reports()
    layer_version = current_layer_version()
    if not reports:
        st.info("No saved reports yet. Ask a question in Chat and hit Save Report.")
    for i, rep in enumerate(reports):
        c_name, c_up, c_down, c_rename, c_del = st.columns([8, 1, 1, 1, 1])
        c_name.subheader(rep["name"])
        if c_up.button("↑", key=f"up{i}") and i > 0:
            reports[i - 1], reports[i] = reports[i], reports[i - 1]
            save_reports(reports)
            st.rerun()
        if c_down.button("↓", key=f"down{i}") and i < len(reports) - 1:
            reports[i + 1], reports[i] = reports[i], reports[i + 1]
            save_reports(reports)
            st.rerun()
        with c_rename.popover("✏️"):
            new_name = st.text_input("Rename", value=rep["name"], key=f"rn{i}")
            if st.button("Save", key=f"rnb{i}"):
                rep["name"] = new_name
                save_reports(reports)
                st.rerun()
        if c_del.button("🗑️", key=f"del{i}"):
            reports.pop(i)
            save_reports(reports)
            st.rerun()

        stale = rep.get("built_against", "0") != layer_version
        with st.expander("SQL"):
            st.code(rep["sql"], language="sql")
        run_err = None
        try:
            con = duckdb.connect(DB_PATH, read_only=True)
            df = con.execute(rep["sql"]).df()
            con.close()
            st.dataframe(df)
            st.download_button("Export to CSV", df.to_csv(index=False).encode(),
                               file_name=f"{rep['name'][:40]}.csv", mime="text/csv", key=f"repcsv{i}")
            st.caption(f"saved {rep['saved']}, refreshed {date.today()}, {len(df)} rows")
        except Exception as e:
            run_err = str(e).splitlines()[0]
            st.error(f"report failed to run: {run_err}")

        if stale or run_err:
            if stale:
                st.warning("This report was built against an older schema.")
            if st.button("Rebuild in chat", key=f"rebuild{i}"):
                entries = [e for e in load_changelog()
                           if e["version"] > rep.get("built_against", "0")]
                changes_txt = "\n".join(f"- {c}" for e in entries for c in e["changes"]) or "- (none recorded)"
                status = (f"It currently fails with: {run_err}" if run_err
                          else "It still runs, but the schema has changed since it was built.")
                prompt = (f"Rebuild this saved report against the current schema.\n"
                          f"Report name: {rep['name']}\n"
                          f"Original question: {rep['question']}\n"
                          f"Previous SQL:\n```sql\n{rep['sql']}\n```\n"
                          f"{status}\n"
                          f"Schema changes since it was built:\n{changes_txt}\n"
                          f"Write updated SQL that answers the original question.")
                with st.spinner("Rebuilding..."):
                    r = run_chat(prompt, [], model=model, use_semantic_layer=True)
                    turn = {"question": prompt, "sql": r["sql"], "error": r["error"],
                            "answer": r["answer"], "df": None, "nrows": 0, "preview": "",
                            "latency": r["latency"], "tokens": r["tokens"], "rebuild_of": i}
                    if r["df"] is not None:
                        turn["answer"] = narrate(rep["question"], r["df"])
                        turn["df"] = r["df"]
                        turn["nrows"] = len(r["df"])
                        turn["preview"] = r["df"].head(5).to_string()
                st.session_state.turns.append(turn)
                autosave_chat()
                st.toast("Rebuilt — review it in the Chat tab, then hit Update saved report")
        st.divider()

with tab_admin:
    st.subheader("Update Schema")
    st.caption("Detect database schema drift, test every verified query and saved report "
               "against the live schema, and review an LLM-drafted semantic layer update.")

    if st.button("Check for schema changes"):
        con = duckdb.connect(DB_PATH, read_only=True)
        st.session_state.live_schema = get_schema(con)
        st.session_state.schema_changes = diff_schemas(load_snapshot(), st.session_state.live_schema)
        st.session_state.check_results = check_queries(con)
        con.close()

    if "schema_changes" in st.session_state:
        changes = st.session_state.schema_changes
        if not changes:
            st.success("No schema changes since the last accepted snapshot.")
        else:
            st.warning(f"{len(changes)} schema change(s) detected:")
            for c in changes:
                st.write("- " + c)

        st.write("**Query health** (verified queries + saved reports):")
        for label, err in st.session_state.check_results:
            if err:
                st.error(f"{label} — {err}")
            else:
                st.write(f"✅ {label}")

        if changes and st.button("Draft semantic layer update"):
            with st.spinner("Drafting proposal..."):
                st.session_state.proposal = draft_update(
                    changes, st.session_state.check_results, model=model)

    if st.session_state.get("proposal"):
        st.subheader("Proposed semantic layer change")
        with open("semantic_layer.yaml") as f:
            current = f.read()
        diff = "\n".join(difflib.unified_diff(
            current.splitlines(), st.session_state.proposal.splitlines(),
            "current", "proposed", lineterm=""))
        st.code(diff if diff else "(no differences)", language="diff")

        def accept_layer(text):
            with open("semantic_layer.yaml", "w") as f:
                f.write(text + "\n")
            save_snapshot(st.session_state.live_schema)
            append_changelog(st.session_state.schema_changes)
            for k in ("proposal", "schema_changes", "check_results", "live_schema"):
                st.session_state.pop(k, None)

        c1, c2, c3 = st.columns(3)
        if c1.button("Accept", type="primary"):
            accept_layer(st.session_state.proposal)
            st.toast("Semantic layer updated — saved reports are now flagged for rebuild")
            st.rerun()
        with c2.popover("Reject with reason"):
            reason = st.text_input("Reason", key="reject_reason")
            if st.button("Reject", key="reject_btn"):
                with open("schema_reviews.log", "a") as f:
                    f.write(f"{datetime.now().isoformat()} REJECTED: {reason}\n")
                st.session_state.pop("proposal", None)
                st.toast("Proposal rejected and logged")
                st.rerun()
        with c3.popover("Hand-edit"):
            edited = st.text_area("Edit before accepting", value=st.session_state.proposal,
                                  height=400, key="hand_edit")
            if st.button("Save edited version", key="hand_edit_btn"):
                accept_layer(edited)
                st.toast("Edited semantic layer saved — saved reports are now flagged for rebuild")
                st.rerun()
