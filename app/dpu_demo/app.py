"""Data Product Usability (DPU) - demo app.

Page 1: enter a dbGaP study (phs number) or source-paper PMID, press Start.
Page 2: the story of the data product.

Prototype: results are pre-computed (Tool 1 pilot run, see data/studies.json
'as_of'). Start does NOT run Tool 1 / Tool 2. Tool 2 is a placeholder.
"""
import json
import time
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Data Product Usability - demo", layout="wide")

DATA = Path(__file__).parent / "data"
REUSE_GROUPS = {
    "A Acquisition": "Obtained the data (A)",
    "B Listed by section": "Named in data / methods (B)",
    "D Acknowledgement": "Acknowledged the data (D)",
}
TABLES = ["papers", "grants", "requesters", "pathways", "dbgap_check",
          "key_numbers", "pathway_coverage", "requester_summary",
          "decision_summary"]
UNNAMED = "(source not named in the sentence)"
OPTIONAL = ["tool2_papers", "funder_sources", "tool2_sources",
            "tool2_source_status"]


# ---------------------------------------------------------------- data
@st.cache_data
def load():
    t = {n: pd.read_csv(DATA / f"{n}.csv", dtype={"pmid": "string"})
         for n in TABLES}
    for n in OPTIONAL:
        f = DATA / f"{n}.csv"
        t[n] = pd.read_csv(f, dtype={"pmid": "string"}) if f.exists() else None
    meta = json.loads((DATA / "studies.json").read_text())
    return t, meta


T, META = load()
STUDIES = META["studies"]
AS_OF = META["as_of"]


def as_of(acc):
    return STUDIES[acc].get("as_of", AS_OF)


def kget(K, col, default=0):
    """Value from a summary row, or default when the row/column is missing."""
    if K is None or col not in K.index or pd.isna(K[col]):
        return default
    return K[col]


def option_label(acc):
    s = STUDIES[acc]
    t = s.get("title") or s.get("label", "")
    parts = [acc, s.get("short_name", ""), t]
    return " - ".join(p for p in parts if p)


def resolve(text):
    """phs number (any version suffix), source PMID or short name -> accession."""
    q = (text or "").strip().lower().replace(" ", "")
    q = q.removeprefix("pmid:").removeprefix("pmid")
    if not q:
        return None
    for acc, s in STUDIES.items():
        if q.startswith(acc) or q in s.get("source_pmids", []):
            return acc
    for acc, s in STUDIES.items():
        short = s.get("short_name", "").lower().replace(" ", "")
        if short and q in (short, short.removeprefix("ccdi")):
            return acc
    return None


def truthy(v):
    return str(v).strip().lower() in ("true", "yes", "1", "y")


def row(name, acc):
    df = T[name]
    df = df[df["accession"] == acc]
    return df.iloc[0] if len(df) else None


# ---------------------------------------------------------------- helpers
def section(num, title, how):
    st.divider()
    st.subheader(f"{num}. {title}")
    st.caption(f"How to read: {how}")


def hbar(df, x, y, color=None, top=15, xlab="papers"):
    if df.empty:
        st.info("No data for this study.")
        return
    keep = df.groupby(y)[x].sum().sort_values(ascending=False).head(top).index
    df = df[df[y].isin(keep)]
    fig = px.bar(df, x=x, y=y, color=color, orientation="h",
                 text=None if color else x, labels={x: xlab, y: ""})
    fig.update_layout(yaxis={"categoryorder": "total ascending"},
                      height=max(260, 30 * len(keep) + 90),
                      margin=dict(l=10, r=10, t=10, b=10),
                      legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)


def donut(labels, values, colors=None):
    d = pd.DataFrame({"label": labels, "n": values})
    d = d[d.n > 0]
    fig = px.pie(d, names="label", values="n", hole=0.55,
                 color="label", color_discrete_map=colors or {})
    fig.update_traces(textinfo="value+percent", sort=False)
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                      legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)


PUBMED = st.column_config.LinkColumn(
    "PMID", display_text=r"https://pubmed\.ncbi\.nlm\.nih\.gov/(\d+)")


def with_link(df):
    df = df.copy()
    df["pmid"] = "https://pubmed.ncbi.nlm.nih.gov/" + df["pmid"].astype(str)
    return df


def table(df, height=320):
    st.dataframe(with_link(df), hide_index=True, use_container_width=True,
                 height=height, column_config={"pmid": PUBMED})


ROLE_HELP = ("Counted funders = research funding + infrastructure (e.g. P30 cancer "
             "center grants). Personnel support (fellowships, training and career "
             "awards, chairs, or 'XX is supported by ...') is listed separately and "
             "not counted. Where the paper names the grant, its wording decides.")


def split_roles(df):
    """(counted rows, personnel-support rows). Older data without roles: all counted."""
    if "counted" not in df:
        return df, df.iloc[0:0]
    c = df.counted.astype(str).str.lower().eq("true")
    return df[c], df[df.role.astype(str).eq("personnel")]


def grant_table(df, height=320):
    keys = [k for k in ("funder_normalised", "grant_key", "pmid") if k in df]
    cols = [c for c in ("funder_normalised", "grant_id", "role", "found_in",
                        "name_note", "pmid", "year", "quote") if c in df]
    table(df.drop_duplicates(keys)[cols], height=height)


SOURCE_HELP = ("Where each funder was found in the paper: Acknowledgement text, the "
               "publisher's Funding section, Europe PMC grant metadata - one funder "
               "is often found by more than one route. 'names as written' and "
               "'name notes' show every spelling merged or tidied.")


def funder_source_table(acc, grp, height=320):
    FS = T.get("funder_sources")
    if FS is None:
        st.info("Funder source table not available in this data snapshot.")
        return
    d = FS[(FS.accession == acc) & (FS.positive_group == grp)]
    cols = [c for c in ("funder", "counted", "roles", "papers", "grant numbers",
                        "papers: Acknowledgement text",
                        "papers: Funding section (publisher)",
                        "papers: Europe PMC metadata", "found in",
                        "names as written", "name notes") if c in d]
    st.dataframe(d[cols], hide_index=True, use_container_width=True,
                 height=height)


def n_grants(df):
    k = df.grant_key.dropna().astype(str)
    return k[k != ""].nunique()


SOURCE_FLOW = """digraph {
  rankdir=TB; node [shape=box, style="rounded,filled", fillcolor="#f5f5f5",
  fontname="Helvetica", fontsize=11]; edge [fontname="Helvetica", fontsize=10];
  entry [label="Entry", shape=diamond, fillcolor="#e8eef7"];
  pmid  [label="PMID(s) entered by user\\n= source PMIDs", fillcolor="#d9f0d3"];
  t1    [label="Tool 1 runs on the phs number"];
  gen   [label="Tool 1 Generated papers (rule E)?", shape=diamond, fillcolor="#e8eef7"];
  opt   [label="User choice: include dbGaP\\nstudy-page publications?\\n(default: no)", shape=diamond, fillcolor="#fff2cc"];
  db    [label="dbGaP study page: publications?", shape=diamond, fillcolor="#e8eef7"];
  lst   [label="listed in the scope table,\\nnot used as source"];
  addg  [label="add: Tool 1 Generated (rule E)"];
  addd  [label="add: dbGaP study page"];
  any   [label="Any source PMID?", shape=diamond, fillcolor="#e8eef7"];
  run   [label="Tool 2 runs on the union\\n(each PMID keeps its 'found by')", fillcolor="#d9f0d3"];
  none  [label="Report: no source PMID\\nTool 2 not run - no guessing", fillcolor="#fde0dd"];
  entry -> pmid [label=" PMID"]; entry -> t1 [label=" phs number"];
  pmid -> run;
  t1 -> gen; t1 -> opt;
  opt -> db [label=" yes"]; opt -> lst [label=" no"]; lst -> any;
  gen -> addg [label=" yes"]; db -> addd [label=" yes"];
  addg -> any; addd -> any;
  gen -> any [label=" no: nothing added"]; db -> any [label=" no: nothing added"];
  any -> run [label=" yes"]; any -> none [label=" no"];
}"""


def tool2_sources_block(acc):
    """Scope of Tool 2: which source PMIDs, and where each came from."""
    s = STUDIES[acc]
    with st.expander("How Tool 2 gets its source papers (rule)"):
        st.graphviz_chart(SOURCE_FLOW, use_container_width=True)
        st.caption("Entry by phs number: source PMIDs = Tool 1 Generated "
                   "(rule E) papers, plus the dbGaP study-page publications "
                   "only if the user chooses to include them (off by default; "
                   "what the dbGaP list means is not yet confirmed). Nothing "
                   "used -> no source PMID; Tool 2 does not search for or "
                   "pick a source paper itself.")
    SRC, STT = T.get("tool2_sources"), T.get("tool2_source_status")
    if SRC is None:
        return
    src = SRC[SRC.accession == acc]
    stt = STT[STT.accession == acc] if STT is not None else STT
    st.markdown("**Tool 2 scope - source papers for this study**")
    if stt is not None and not stt.empty:
        r = stt.iloc[0]
        st.caption(f"dbGaP check: {r.dbgap_check} | Tool 1 check: "
                   f"{r.tool1_check}")
    src = src.rename(columns={"source_pmid": "pmid", "found_by": "found by"})
    src["pmid"] = src.pmid.astype(str)
    src["year"] = src.year.astype("string").str.replace(r"\.0$", "",
                                                        regex=True)
    dbgap_only = src["found by"].eq("dbGaP study page")
    n_db = int(src["found by"].str.contains("dbGaP").sum())
    inc = st.toggle(
        "Include dbGaP study-page publications as source PMIDs",
        value=bool(s.get("tool2_dbgap_included", False)),
        key=f"t2_dbgap_{acc}", disabled=n_db == 0,
        help="Off by default. What the dbGaP 'Publications' list means is "
             "not yet confirmed: it may hold the data-generating paper, "
             "later reuse papers, or both. Tool 1 Generated papers are "
             "always used.")
    if s.get("tool2_dbgap_included") and n_db:
        st.caption("The pilot run below was made with dbGaP study-page "
                   "publications **included** (switch on). Turning the switch "
                   "off shows what the default rule would use; it does not "
                   "change the results below.")
    pilot_only = src["found by"].str.contains("pilot only")
    src["used as source"] = (inc | ~dbgap_only) & ~pilot_only
    used = src[src["used as source"]]
    if used.empty:
        why = ("the dbGaP study page lists no publication" if n_db == 0 else
               f"the {n_db} dbGaP study-page publication(s) are not included")
        st.warning(f"No source PMID: Tool 1 found no Generated paper and "
                   f"{why}. Tool 2 is not run for this study (no guessing).")
        if src.empty:
            return
    cols = ["pmid", "found by", "used as source", "year", "first_author",
            "title"]
    ran = s.get("tool2") == "run"
    if ran:
        cols.append("used_in_pilot_run")
    table(src[cols], height=min(360, 60 + 35 * len(src)))
    st.caption(f"{len(used)} source PMID(s) used: "
               f"{int((~dbgap_only & src['found by'].str.contains('Tool 1')).sum())}"
               f" Tool 1 Generated, "
               f"{int((dbgap_only & src['used as source']).sum())} dbGaP study "
               f"page only. {int(dbgap_only.sum())} PMID(s) are on the dbGaP "
               "page only (not found by Tool 1).")
    if ran:
        pilot = src.used_in_pilot_run.astype(str).str.lower().eq("true")
        n_new = int((src["used as source"] & ~pilot).sum())
        st.caption(f"The pilot results below used only the PMID(s) marked "
                   f"'used_in_pilot_run'. "
                   + (f"With the choice above, Tool 2 would add {n_new} source "
                      "PMID(s); results will change when Tool 2 is re-run."
                      if n_new else "The choice above uses the same PMID(s)."))


TOOL2_TITLE = "Tool 2: Identify Data Reuse via citation (with/wo phs number)"


def tool2_section(acc, tool1_pmids, num=8):
    section(num, TOOL2_TITLE,
            "papers that cite the source paper(s) of this dataset, with or "
            "without the phs number in the text. Tool 2 runs on its own: "
            "Tool 1 only supplies the source papers (its Generated papers); "
            "no Tool 2 result feeds sections 1-7.")
    tool2_block(acc, tool1_pmids)


def tool2_block(acc, tool1_pmids):
    """Tool 2: papers that cite the source paper, classified from the citing
    sentence. Only Tool 1 Generated papers feed in (as source PMIDs)."""
    s = STUDIES[acc]
    tool2_sources_block(acc)
    T2 = T.get("tool2_papers")
    if T2 is None or s.get("tool2") != "run":
        st.info("Tool 2 was not run for this study. It starts from the papers "
                "that cite the source paper and reads the sentence that cites "
                "it (rule C: used the data; G: compared with it; F: "
                "background).")
        return
    d = T2[T2.accession == acc].copy()
    # Tool 2's own full-text check: does the citing paper also write the phs?
    d["phs in text"] = d.accession_also_found.astype(str).str.lower().eq("true")
    ft = d[d.rule != "X"]
    located = ft[ft.rule != "N"]
    used = d[d.rule == "C"]
    used_no, used_phs = used[~used["phs in text"]], used[used["phs in text"]]
    n_conf = int((used_no.confidence >= 0.95).sum())
    n_anal = int(((used_no.confidence >= 0.80) & (used_no.confidence < 0.95)).sum())
    src = "; ".join(f"PMID {p}" for p in s.get("source_pmids", []))
    st.markdown(
        f"**What this shows:** papers that **cite the source paper** ({src}), "
        "found with iCite + Semantic Scholar. Tool 1 only supplies source "
        "papers (its Generated papers); Tool 2 classifies **on its own**, "
        "without Tool 1 labels. It finds the source paper in each "
        "reference list and reads only the sentence that cites it: data use "
        "(rule C), background (F) or comparison with published results (G). "
        f"It also checks the full text for **{acc}**, so citation-only reuse "
        "(no phs number in the text - invisible to a phs search) is shown "
        "apart from reuse where the phs number is also written.")
    st.caption(s.get("tool2_note", ""))
    c = st.columns(5)
    c[0].metric("Citing papers checked", len(d))
    c[1].metric("... with full text", len(ft))
    c[2].metric("Source paper located",
                f"{100 * len(located) / len(ft):.0f}%" if len(ft) else "n/a",
                help="share of full-text citing papers where the citation of "
                     "the source paper was found in the text")
    c[3].metric("Data use, citation only", len(used_no),
                help=f"rule C, phs number not in the text: {n_conf} "
                     f"data access stated, {n_anal} analysis wording only "
                     f"(review), {len(used_no) - n_conf - n_anal} weak "
                     "wording (review). "
                     "This is the reuse a phs-number search cannot find.")
    c[4].metric("Data use, citation + phs", len(used_phs),
                help="rule C, and the paper also writes the phs number")
    order = ["Used, citation only (data access stated)",
             "Used, citation only (analysis wording only, review)",
             "Used, citation only (weak wording, review)",
             "Used, citation + phs in text",
             "Cited only (background)", "Cited only (comparison)",
             "Review (cohort found, no rule)",
             "Citation not located", "No full text"]
    family = {"Used, citation only (data access stated)": "Used the data",
              "Used, citation only (analysis wording only, review)": "Used the data",
              "Used, citation only (weak wording, review)": "Used the data",
              "Used, citation + phs in text": "Used the data",
              "Cited only (background)": "Cited only",
              "Cited only (comparison)": "Cited only",
              "Review (cohort found, no rule)": "Needs review",
              "Citation not located": "Not assessable",
              "No full text": "Not assessable"}

    def bar_label(r):
        if r.rule != "C":
            return r.decision
        if r["phs in text"]:
            return "Used, citation + phs in text"
        if r.confidence >= 0.95:
            return "Used, citation only (data access stated)"
        if r.confidence >= 0.80:
            return "Used, citation only (analysis wording only, review)"
        return "Used, citation only (weak wording, review)"

    d["bar"] = d.apply(bar_label, axis=1)
    dc = (d.groupby("bar").agg(papers=("pmid", "size"),
                               phs=("phs in text", "sum")).reset_index()
          .rename(columns={"bar": "decision"}))
    cats = [o for o in order if o in set(dc.decision)] + \
        sorted(set(dc.decision) - set(order))
    dc["group"] = dc.decision.map(family).fillna("Other")
    fig = px.bar(dc, x="papers", y="decision", color="group", text="papers",
                 orientation="h", labels={"decision": "", "group": ""},
                 category_orders={"decision": cats},
                 color_discrete_map={"Used the data": "#1b7837",
                                     "Cited only": "#2166ac",
                                     "Needs review": "#e08214",
                                     "Not assessable": "#9e9e9e"})
    fig.update_layout(height=max(260, 34 * len(cats) + 90),
                      margin=dict(l=10, r=10, t=10, b=10),
                      legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)
    n_phs = int(d["phs in text"].sum())
    other = dc[~dc.decision.str.startswith("Used") & (dc.phs > 0)]
    st.caption(
        f"phs number in the text: {n_phs} of {len(d)} citing papers "
        f"({len(used_phs)} data use"
        + "".join(f"; {int(r.phs)} {r.decision.lower()}"
                  for r in other.itertuples())
        + "). Labels come from the citing sentence only; a paper labelled "
        "'cited only' here can still be data use by its phs number - see "
        "Tool 1.")
    with st.expander("Data use papers (rule C) with the citing sentence"):
        table(used.sort_values("phs in text")[[
            "pmid", "year", "first_author", "journal", "title", "decision",
            "phs in text", "deciding_quote"]], height=300)


# ---------------------------------------------------------------- page 1
def page_input():
    st.title("Data Product Usability")
    st.markdown(
        "Treat a dataset as a **product** and tell its story: who funded it, "
        "who reuses it, who funds the reuse, where people get the data, and "
        "how much reuse comes from ever-approved dbGaP data users.")
    collections = sorted({s.get("collection", "Demo")
                          for s in STUDIES.values()})
    with st.form("start"):
        a, b = st.columns([1, 3])
        coll = a.selectbox("Collection", ["All"] + collections)
        accs = [x for x, s in STUDIES.items()
                if coll == "All" or s.get("collection", "Demo") == coll]
        pick = b.selectbox("Pick a study", accs, index=None,
                           format_func=option_label,
                           placeholder="choose from the list ...")
        q = st.text_input(
            "... or type a dbGaP study accession (phs number) or the PMID "
            "of a paper that generated the data",
            placeholder="e.g. phs000452 or 29301960")
        go = st.form_submit_button("Start", type="primary")
    st.caption("Tip: the Collection filter applies to the list when you "
               "press Start; typed text wins over the list.")
    with st.expander("All studies at a glance"):
        portfolio()
    st.caption(f"{len(STUDIES)} studies in this demo. Prototype - results "
               f"pre-computed as of {AS_OF}; Start does not run the tools.")
    if go:
        acc = resolve(q) or (resolve(pick) if pick else None)
        if not acc:
            st.error("Not in this demo. Try one of: "
                     + ", ".join(STUDIES) + ".")
            return
        run_fake(acc)


def portfolio():
    K = T["key_numbers"].set_index("accession")
    rows = []
    for acc, s in STUDIES.items():
        k = K.loc[acc] if acc in K.index else None
        rows.append({
            "study": acc,
            "title": s.get("title") or s.get("label", ""),
            "collection": s.get("collection", "Demo"),
            "generated papers": int(kget(k, "Generated papers")),
            "reuse papers": int(kget(k, "Reuse papers")),
            "reuse by approved requester": kget(
                k, "Reuse papers by approved requester (Strong + Medium)",
                None),
            "% by approved requester": kget(k, "% of Reuse papers", None),
            "reuse funders": int(kget(k, "Reuse: funders")),
            "on dbGaP study page": int(kget(k, "dbGaP study page papers")),
        })
    df = pd.DataFrame(rows).sort_values("reuse papers", ascending=False)
    df["reuse by approved requester"] = pd.to_numeric(
        df["reuse by approved requester"]).astype("Int64")
    st.caption("How to read: one row per study, sorted by number of reuse "
               "papers. Generated = papers that produced the data; Reuse = "
               "papers that used it (rules A, B, D).")
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"% by approved requester":
                                st.column_config.NumberColumn(format="%.0f%%")})


def run_fake(acc):
    steps = [
        f"Resolving {acc} and its source paper(s)",
        "Searching Europe PMC full text for the accession",
        "Tool 1: classifying papers that name the accession (rules E, A, B, D)",
        "Tool 2: papers that cite the source paper (placeholder)",
        "Extracting funders and grant numbers",
        "Matching authors to ever-approved dbGaP requesters",
        "Capturing data pathways (where the data came from)",
    ]
    with st.status("Running Data Product Usability tools...",
                   expanded=True) as s:
        for m in steps:
            st.write(m)
            time.sleep(0.5)
        s.update(label="Done", state="complete")
    st.session_state.acc = acc
    st.session_state.page = "results"
    st.rerun()


# ---------------------------------------------------------------- page 2
def page_results(acc):
    s = STUDIES[acc]
    P = T["papers"][T["papers"].accession == acc]
    gen = P[P.group == "E Generated"]
    reuse = P[P.group.isin(REUSE_GROUPS)].copy()
    reuse["how"] = reuse.group.map(REUSE_GROUPS)
    K = row("key_numbers", acc)
    RS = row("requester_summary", acc)
    G = T["grants"][T["grants"].accession == acc]
    gg_all = G[G.positive_group == "Generated"]
    rg_all = G[G.positive_group == "Reuse"]
    gg, gg_pers = split_roles(gg_all)
    rg, rg_pers = split_roles(rg_all)
    W = T["pathways"][T["pathways"].accession == acc]

    has_list = kget(K, "% of Reuse papers", None) is not None
    n_appr = int(kget(K, "Reuse papers by approved requester (Strong + Medium)"))
    pct = float(kget(K, "% of Reuse papers"))
    appr_txt = (f"{n_appr} ({pct:.0f}%) of reuse papers include an "
                "ever-approved dbGaP requester" if has_list else
                "no dbGaP approved-requester list is available")
    n_page = int(kget(K, "dbGaP study page papers"))
    AS_OF = as_of(acc)

    with st.sidebar:
        st.markdown(f"### {acc}")
        st.caption(s.get("title") or s.get("label", ""))
        st.caption(f"Version: {s.get('version') or 'n/a'}")
        st.caption(f"As of {AS_OF}")
        if st.button("New search", use_container_width=True):
            st.session_state.page = "input"
            st.rerun()
        st.divider()
        st.caption(
            "Generated = paper that produced the dataset (rule E). "
            "Reuse = paper that used it (rules A, B, D). "
            "Ever-approved requester = approved, closed or expired dbGaP "
            "data access request; Strong + Medium name matches counted.")

    # 0. headline
    st.title(f"The story of {acc}")
    st.markdown(
        f"#### As of {AS_OF}: {len(gen)} paper(s) generated this dataset; "
        f"{len(reuse)} papers reused it; {appr_txt}. The dbGaP study "
        f"page lists {n_page} paper(s).")
    st.caption((s.get("title") or s.get("label", ""))
               + ". Prototype - pre-computed results. Sections 1-7 use "
               "Tool 1 only (papers that write the phs number); section 8 "
               "is Tool 2 (papers that cite the source paper).")
    if len(gen) + len(reuse) == 0:
        st.info(
            f"As of {AS_OF}, Tool 1 found no paper in Europe PMC that names "
            f"{acc} and generated or reused the data "
            f"({len(P)} paper(s) mention it without a rule applying). "
            "Newer studies often have no publications yet; papers that cite "
            "the data only through the source paper are in Tool 2 below.")
        tool2_section(acc, set(P.pmid.dropna()))
        return
    c = st.columns(5)
    c[0].metric("Generated papers", len(gen))
    c[1].metric("Reuse papers", len(reuse))
    c[2].metric("Funders of reuse", rg.funder_normalised.nunique(),
                help=ROLE_HELP)
    c[3].metric("Reuse by approved requester",
                f"{pct:.0f}%" if has_list else "n/a",
                help=f"{n_appr} of {len(reuse)} reuse papers")
    c[4].metric("On dbGaP study page", n_page)

    # 1. funders of the dataset
    section(1, "Who funded the dataset",
            "funders and grant numbers acknowledged by the paper(s) that "
            "generated the data. Bar length = number of generating papers "
            "naming the funder.")
    if gen.decision.str.contains("needs review", na=False).any():
        nr = int(gen.decision.str.contains("needs review", na=False).sum())
        st.warning(f"{nr} of {len(gen)} 'Generated' labels need review - "
                   "some may be reuse papers. Funders below may change.")
    st.markdown(
        f"{len(gen)} generating paper(s) name "
        f"**{gg.funder_normalised.nunique()} funders** (research + "
        f"infrastructure) with **{n_grants(gg)} grant numbers**; "
        f"{gg_pers.funder_normalised.nunique()} more give personnel support.",
        help=ROLE_HELP)
    if len(gen) == 0:
        st.caption("No generating paper found by Tool 1 for this study - "
                   "the data may have been released before or without a "
                   "paper naming the accession.")
    a, b = st.columns([3, 2])
    with a:
        f1, f2, f3, f4 = st.tabs(["Funders", "Personnel support",
                                  "Where found", "All grants"])
        with f1:
            by = (gg.groupby("funder_normalised")
                  .agg(papers=("pmid", "nunique")).reset_index())
            hbar(by, "papers", "funder_normalised")
            grant_table(gg, height=220)
        with f2:
            st.caption("Pays for a person, not counted as a funder of the "
                       "dataset.")
            grant_table(gg_pers, height=260)
        with f3:
            st.caption(SOURCE_HELP)
            funder_source_table(acc, "Generated", height=260)
        with f4:
            st.caption("Every grant record with its role, where it was found "
                       "and the quote.")
            grant_table(gg_all, height=260)
    with b:
        st.markdown("**Generating paper(s)**")
        table(gen[["pmid", "year", "first_author", "journal", "title"]],
              height=250)

    # 2. reuse
    section(2, "How people reuse the dataset",
            "Tool 1 reuse papers (they write the phs number), by "
            "publication year and by how we "
            "know (the rule that decided). Confidence: Confirmed > Probable "
            "> Possible.")
    a, b = st.columns([3, 2])
    with a:
        yr = reuse.groupby(["year", "how"]).size().reset_index(name="papers")
        fig = px.bar(yr, x="year", y="papers", color="how",
                     labels={"year": "", "how": ""})
        fig.update_layout(height=340, xaxis=dict(dtick=1),
                          margin=dict(l=10, r=10, t=10, b=10),
                          legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    with b:
        dc = reuse.decision.value_counts()
        donut(dc.index.tolist(), dc.values.tolist(),
              {"Confirmed use": "#1b7837", "Probable use": "#7fbf7b",
               "Possible use": "#d9f0d3"})
    n_rev = int((P.group == "Review no rule").sum())
    if n_rev:
        st.caption(f"{n_rev} more paper(s) name the accession but no rule "
                   "applied - not counted, left for curator review.")
    st.caption("Reuse found only through citation of the source paper is "
               "in section 8 (Tool 2).")

    # 3. funders of reuse
    section(3, "Who funds the reuse",
            "funders acknowledged by the reuse papers. Bar length = number "
            "of reuse papers naming the funder. Compare with section 1 to "
            "see how far the dataset travels beyond its original funders.")
    gen_f = set(gg.funder_normalised.dropna())
    reu_f = set(rg.funder_normalised.dropna())
    nih_p = rg[rg.funder_normalised.str.startswith("NIH", na=False)]
    c = st.columns(4)
    c[0].metric("Reuse papers with funding info", rg_all.pmid.nunique())
    c[1].metric("Funders", rg.funder_normalised.nunique(), help=ROLE_HELP)
    c[2].metric("Grant numbers", n_grants(rg),
                help=f"{rg_pers.funder_normalised.nunique()} more funders "
                     "give personnel support (not counted)")
    c[3].metric("Funders new vs. generation", len(reu_f - gen_f),
                help=f"{len(reu_f & gen_f)} funder(s) fund both")
    st.markdown(
        f"**{nih_p.pmid.nunique()}** reuse papers acknowledge NIH; "
        f"**{len(reu_f - gen_f)}** of {len(reu_f)} reuse funders did not "
        "fund the generating paper(s).")
    t1, t2, t3 = st.tabs(["Top funders", "NIH institutes",
                          "Personnel support"])
    with t1:
        by = (rg.groupby("funder_normalised")
              .agg(papers=("pmid", "nunique")).reset_index())
        by["also funded generation"] = by.funder_normalised.isin(gen_f).map(
            {True: "also funded generation", False: "reuse only"})
        hbar(by, "papers", "funder_normalised",
             color="also funded generation")
    with t2:
        by = (nih_p.groupby("funder_normalised")
              .agg(papers=("pmid", "nunique")).reset_index())
        hbar(by, "papers", "funder_normalised")
    with t3:
        st.caption("Pays for a person (fellowship, training or career "
                   "award, chair) - not counted above.")
        by = (rg_pers.groupby("funder_normalised")
              .agg(papers=("pmid", "nunique")).reset_index())
        hbar(by, "papers", "funder_normalised")
    with st.expander("Where each funder was found (curation table)"):
        st.caption(SOURCE_HELP)
        funder_source_table(acc, "Reuse")
    with st.expander("All grants with role, where found and quote"):
        grant_table(rg_all)

    # 4. pathways
    section(4, "Where people get the data (Tool 1 papers only)",
            "Tool 1 reuse papers only (papers that write the phs number); "
            "Tool 2 citation-route papers are not included yet. Shows "
            "sentences in reuse papers that say where THIS dataset came "
            "from (obtained from / available in / deposited in). Colour = "
            "wording. Sources are the names the papers use - no fixed "
            "repository list.")
    cov = T["pathway_coverage"]
    cov = cov[(cov.accession == acc) & (cov["positive group"] == "Reuse")]
    if len(cov):
        cv = cov.iloc[0]
        c = st.columns(3)
        c[0].metric("Reuse papers stating a pathway",
                    int(cv["papers stating a pathway for this dataset"]))
        c[1].metric("... naming a source",
                    int(cv["of which a source is named"]))
        c[2].metric("No pathway sentence",
                    int(cv["papers with no pathway sentence"]))
    wr = W[(W.scope == "this dataset") & (W.positive_group == "Reuse")]
    src = (wr.groupby(["data_source_group", "direction"]).pmid.nunique()
           .reset_index(name="papers"))
    t1, t2 = st.tabs(["Source of this dataset",
                      "Other data combined in the same papers"])
    with t1:
        hbar(src, "papers", "data_source_group", color="direction")
    with t2:
        st.caption("Other datasets/resources the reuse papers name. Some "
                   "entries are cohort or author names (known noise).")
        wo = W[(W.scope != "this dataset") & (W.positive_group == "Reuse")
               & (W.data_source_group != UNNAMED)]
        oth = (wo.groupby("data_source_group").pmid.nunique()
               .reset_index(name="papers"))
        hbar(oth, "papers", "data_source_group")
    with st.expander("Pathway sentences (exact quotes)"):
        table(wr[["pmid", "year", "direction", "data_source_group",
                  "section", "quote"]])

    # 5. approved requesters
    section(5, "How much reuse comes from ever-approved data users",
            "a reuse paper counts when an author matches an ever-approved "
            "dbGaP requester for this study. Strong = name + affiliation + "
            "published after approval; Medium = name + date, affiliation "
            "differs; Weak = not counted.")
    if RS is None or not truthy(RS["requester list available"]) \
            or len(reuse) == 0:
        st.info("No dbGaP requester list available for this study.")
    else:
        strong, med = int(RS["Strong"]), int(RS["Medium"])
        weak = int(RS["Weak only (not counted)"])
        n_reu = int(RS["reuse papers (A, B, D)"])
        none = max(n_reu - strong - med - weak, 0)
        a, b = st.columns([2, 3])
        with a:
            donut(["Strong", "Medium", "Weak (not counted)", "No match"],
                  [strong, med, weak, none],
                  {"Strong": "#08519c", "Medium": "#6baed6",
                   "Weak (not counted)": "#c6dbef", "No match": "#e0e0e0"})
        with b:
            st.markdown(
                f"**{strong + med} of {n_reu}** reuse papers "
                f"({pct:.0f}%) include an ever-approved requester. The rest "
                "may come from collaborators of approved users, from data "
                "re-distributed by other resources (see section 4), or "
                "from requesters whose names did not match.")
            R = T["requesters"]
            R = R[(R.accession == acc) & (R.positive_group == "Reuse")
                  & (R.counted.astype(str).str.lower() == "true")]
            top = (R.groupby(["requester", "requester_org"]).pmid.nunique()
                   .reset_index(name="reuse papers")
                   .sort_values("reuse papers", ascending=False))
            st.dataframe(top.head(15), hide_index=True,
                         use_container_width=True, height=300)
        with st.expander("Requester matches (detail)"):
            table(R[["pmid", "year", "match_level", "requester",
                     "requester_status", "initial_approval_date",
                     "matched_author", "author_affiliation", "match_note"]])

    # 6. dbGaP study page
    section(6, "dbGaP study page vs. this tool",
            "papers listed in the Publications section of the dbGaP study "
            "page, compared with papers found by Tool 1.")
    n_tool = len(gen) + len(reuse)
    a, b = st.columns([2, 3])
    with a:
        cmp_ = pd.DataFrame({"source": ["dbGaP study page", "Tool 1"],
                             "papers": [n_page, n_tool]})
        fig = px.bar(cmp_, x="source", y="papers", text="papers",
                     color="source", labels={"source": ""})
        fig.update_layout(height=300, showlegend=False,
                          margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with b:
        st.markdown(
            f"The study page lists **{n_page}** paper(s); Tool 1 finds "
            f"**{n_tool}** (Generated + Reuse) and adds "
            f"**{int(kget(K, 'Tool 1 positives not on study page'))}** not on the "
            "page." + (" The study page under-reports use of this dataset."
                       if n_tool > n_page else ""))
        D = T["dbgap_check"]
        D = D[(D.accession == acc) & D.pmid.notna()]
        if len(D):
            table(D[["pmid", "dbgap_title", "tool1_group", "tool1_decision",
                     "approved_requester_match"]], height=200)

    # 7. evidence
    section(7, "Evidence for Tool 1 labels (Tool 1 papers only)",
            "the quote behind every Tool 1 label in sections 1-6: one row "
            "per paper that writes the phs number, with the sentence that "
            "decided its group. Tool 2 papers and their citing sentences "
            "are in section 8. Filter by group; download as CSV.")
    with st.expander("Legend - what the groups and columns mean",
                     expanded=True):
        st.markdown(
            "| Group | Counted as | Deciding sentence |\n"
            "| --- | --- | --- |\n"
            "| E Generated | Generated this dataset | says the authors "
            "deposited / generated the data under this phs number |\n"
            "| A Acquisition | Reuse | phs number + an access verb "
            "(obtained, downloaded, retrieved, accessed, ...) |\n"
            "| B Listed by section | Reuse | phs number listed as a data "
            "source in methods, data availability, tables, ... (no access "
            "verb) |\n"
            "| D Acknowledgement | Reuse | phs number only in the "
            "acknowledgements (weaker evidence) |\n"
            "| Review no rule | Not counted | phs number found, but no rule "
            "fits - needs a human read |\n\n"
            "**Columns:** `group` and `decision` = Tool 1 label; "
            "`deciding_section` = where in the paper the sentence is; "
            "`deciding_quote` = the exact sentence; "
            "`approved_requester_author` = an author matches an "
            "ever-approved dbGaP requester (section 5). Labels are made by "
            "word rules and are not yet checked by a person.")
    groups = ["E Generated", *REUSE_GROUPS, "Review no rule"]
    pick = st.multiselect("Groups", groups, default=groups)
    ev = P[P.group.isin(pick)][[
        "pmid", "year", "first_author", "journal", "title", "group",
        "decision", "approved_requester_author", "deciding_section",
        "deciding_quote"]].sort_values("year", ascending=False)
    table(ev, height=420)
    st.download_button("Download papers (CSV)", ev.to_csv(index=False),
                       file_name=f"dpu_{acc}_papers_{AS_OF}.csv",
                       mime="text/csv")

    # 8. Tool 2
    tool2_section(acc, set(P.pmid.dropna()))


# ---------------------------------------------------------------- router
st.session_state.setdefault("page", "input")
if st.session_state.page == "results" and st.session_state.get("acc"):
    page_results(st.session_state.acc)
else:
    page_input()
