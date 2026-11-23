"""RUS (dbGaP Research Use Statement) data-use results: loading and queries.

Shared by the DPU demo app (page 2_RUS_explorer.py) and the DPU MCP server.
Data: data/rus/rus_statements.csv.gz (one row per unique statement),
      data/rus/rus_requests.csv.gz  (one row per non-rejected request, key_id links them),
      data/rus/rus_meta.json        (as_of date, method, how_to_read).
Pure pandas: no LLM calls here; results were pre-computed by the
rus-data-use-classifier skill (two models, agreed answers kept).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

RUS_DIR = Path(__file__).parent / "data" / "rus"

GROUP_LABELS = {
    "BIOLOGY": "Biology",
    "TOOL": "Tool",
    "TOOL_OR_BIOLOGY (models differ)": "Tool or biology (models differ)",
    "OPERATIONS": "Operations",
    "REVIEW (models differ)": "Review (models differ)",
    "UNCLEAR": "Unclear",
}
STAGE_LABELS = {
    "PRECLINICAL": "Preclinical",
    "CLINICAL": "Clinical",
    "PRECLINICAL_OR_CLINICAL (models differ)": "Preclinical or clinical (models differ)",
}
TOPIC_LABELS = {
    "clinical_outcome": "Clinical outcome",
    "treatment_response": "Treatment response",
    "diagnosis": "Diagnosis",
    "adverse_event": "Adverse event",
    "other": "Other",
    "REVIEW (models differ)": "Topic differs (models differ)",
}
AI_LABELS = {"AI": "Uses AI", "no AI": "No AI", "REVIEW": "AI flag differs"}
AI_ROLE_LABELS = {"build": "Build AI", "apply": "Apply AI", "REVIEW": "Build vs apply differs"}
# Rejected requests are removed before classification and are not in the data.
STATUSES = ["approved", "closed", "expired"]
DEFAULT_STATUSES = STATUSES
NOT_CLASSIFIED = "Not classified"  # safety label; should not occur


@lru_cache(maxsize=1)
def load() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (statements, requests, meta) with readable label columns added."""
    s = pd.read_csv(RUS_DIR / "rus_statements.csv.gz")
    r = pd.read_csv(RUS_DIR / "rus_requests.csv.gz", dtype={"wlid": "string"})
    meta = json.loads((RUS_DIR / "rus_meta.json").read_text())
    s["group"] = s["final_group"].map(GROUP_LABELS).fillna(s["final_group"])
    s["stage"] = s["final_stage"].map(STAGE_LABELS).fillna("")
    s["topic"] = s["final_topic"].map(TOPIC_LABELS).fillna("")
    s["ai"] = s["final_ai"].map(AI_LABELS).fillna("")
    s["ai_role"] = s["final_ai_role"].map(AI_ROLE_LABELS).fillna("")
    s["data_platform_flag"] = s["data_platform_flag"].fillna(False).astype(bool)
    r["phs"] = r["phs"].astype(str)
    r["approval_year"] = pd.to_datetime(
        r["initial_approval_date"], errors="coerce"
    ).fillna(pd.to_datetime(r["date_of_approval"], errors="coerce")).dt.year
    # which studies / DACs each statement belongs to
    keys = r.groupby("key_id").agg(
        dacs=("DAC", lambda x: "; ".join(sorted(set(x.dropna())))),
        studies=("phs", lambda x: "; ".join(sorted(set(x.dropna())))),
    )
    s = s.merge(keys, left_on="key_id", right_index=True, how="left")
    return s, r, meta


def as_of() -> str:
    return load()[2]["as_of"]


def _norm_phs(phs: str | None) -> str | None:
    if not phs:
        return None
    m = re.search(r"phs\d{6}", str(phs).lower())
    return m.group(0) if m else None


def filter_requests(
    dac: str | None = None,
    phs: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    statuses: list[str] | None = None,
) -> pd.DataFrame:
    """Request rows matching DAC / study / approval-year / request-status filters.
    statuses=None keeps every status in the data (approved, closed, expired)."""
    _, r, _ = load()
    rr = r
    if statuses:
        rr = rr[rr["status"].isin(statuses)]
    if dac and dac != "All":
        rr = rr[rr["DAC"] == dac]
    p = _norm_phs(phs)
    if p:
        rr = rr[rr["phs"].str.lower() == p]
    if year_from:
        rr = rr[rr["approval_year"] >= year_from]
    if year_to:
        rr = rr[rr["approval_year"] <= year_to]
    return rr


def filter_statements(
    dac: str | None = None,
    phs: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    groups: list[str] | None = None,
    ai: list[str] | None = None,
    stages: list[str] | None = None,
    topics: list[str] | None = None,
    text: str | None = None,
    statuses: list[str] | None = None,
) -> pd.DataFrame:
    """Unique statements matching all filters. Labels use the readable names
    (e.g. groups=['Biology'], ai=['Uses AI'], stages=['Clinical']).
    dac / phs / year filter on the requests that use the statement."""
    s, r, _ = load()
    rr = filter_requests(dac, phs, year_from, year_to, statuses)
    out = s[s["key_id"].isin(set(rr["key_id"]))] if rr is not r else s
    if groups:
        out = out[out["group"].isin(groups)]
    if ai:
        out = out[out["ai"].isin(ai) | out["ai_role"].isin(ai)]
    if stages:
        out = out[out["stage"].isin(stages)]
    if topics:
        out = out[out["topic"].isin(topics)]
    if text and text.strip():
        words = [w for w in re.split(r"\s+", text.strip().lower()) if w]
        low = out["statement"].fillna("").str.lower()
        mask = pd.Series(True, index=out.index)
        for w in words:
            mask &= low.str.contains(re.escape(w), regex=True)
        out = out[mask]
    return out


def summary(df: pd.DataFrame) -> dict:
    """Counts for a set of statements (from filter_statements)."""
    bio = df[df["group"] == "Biology"]
    clin = df[df["stage"] == "Clinical"]
    n = len(df)
    return {
        "statements": n,
        "by_group": df["group"].value_counts().to_dict(),
        "uses_ai": int((df["ai"] == "Uses AI").sum()),
        "uses_ai_share": round(float((df["ai"] == "Uses AI").mean()), 3) if n else 0.0,
        "ai_role": df.loc[df["ai"] == "Uses AI", "ai_role"].value_counts().to_dict(),
        "biology_by_stage": bio["stage"].value_counts().to_dict(),
        "clinical_by_topic": clin["topic"].value_counts().to_dict(),
        "data_platform_built": int(df["data_platform_flag"].sum()),
    }


def by_year(df: pd.DataFrame) -> pd.DataFrame:
    """Per first-approval year: statements, AI share, build/apply AI, tool share,
    clinical share of biology."""
    d = df.dropna(subset=["first_year"]).copy()
    d["first_year"] = d["first_year"].astype(int)
    g = d.groupby("first_year")
    out = pd.DataFrame({
        "statements": g.size(),
        "ai_share": g["ai"].apply(lambda x: (x == "Uses AI").mean()),
        "build_ai": g["ai_role"].apply(lambda x: (x == "Build AI").sum()),
        "apply_ai": g["ai_role"].apply(lambda x: (x == "Apply AI").sum()),
        "tool_share": g["group"].apply(lambda x: (x == "Tool").mean()),
    })
    bio = d[d["group"] == "Biology"]
    out["clinical_share_of_biology"] = bio.groupby("first_year")["stage"].apply(
        lambda x: (x == "Clinical").mean())
    return out.fillna(0).reset_index().rename(columns={"first_year": "year"})


def requests_for(df: pd.DataFrame, requests: pd.DataFrame | None = None) -> pd.DataFrame:
    """Request rows (wlid, study, requestor, ...) for a set of statements.
    Pass `requests` (from filter_requests) to keep only requests matching the
    same DAC / study / year filters."""
    r = load()[1] if requests is None else requests
    cols = ["key_id", "group", "ai", "ai_role", "stage", "topic"]
    return r.merge(df[cols], on="key_id", how="inner")


def requests_labeled(requests: pd.DataFrame) -> pd.DataFrame:
    """Request rows with their statement's labels (group = NOT_CLASSIFIED only if a
    statement is missing, which should not happen)."""
    s = load()[0]
    cols = ["key_id", "group", "ai", "ai_role", "stage", "topic"]
    out = requests.merge(s[cols], on="key_id", how="left")
    out["group"] = out["group"].fillna(NOT_CLASSIFIED)
    return out.fillna({"ai": "", "ai_role": "", "stage": "", "topic": ""})


def status_counts(requests: pd.DataFrame) -> pd.DataFrame:
    """Requests by status x main group (for the status chart)."""
    lab = requests_labeled(requests)
    return lab.groupby(["status", "group"]).size().reset_index(name="requests")


# ---------------------------------------------------------------- MCP helpers
AI_CHOICES = ["Uses AI", "Build AI", "Apply AI", "No AI", "AI flag differs"]


def _check(name: str, values: list[str] | None, allowed: list[str]) -> str | None:
    bad = [v for v in (values or []) if v not in allowed]
    return f"Unknown {name}: {bad}. Allowed: {allowed}" if bad else None


def _filters(dac, phs, year_from, year_to, statuses, groups, ai, stages, topics, text):
    """Validate MCP inputs, then return (statements, requests, error)."""
    for err in (
        _check("dac", [dac] if dac else None, ["All", "NCI DAC", "Kids First DAC"]),
        _check("statuses", statuses, STATUSES),
        _check("groups", groups, list(GROUP_LABELS.values())),
        _check("ai", ai, AI_CHOICES),
        _check("stages", stages, list(STAGE_LABELS.values())),
        _check("topics", topics, list(TOPIC_LABELS.values())),
    ):
        if err:
            return None, None, err
    if phs and _norm_phs(phs) is None:
        return None, None, f"'{phs}' is not a phs accession (expected e.g. phs002371)."
    if phs and _norm_phs(phs) not in set(load()[1]["phs"].str.lower()):
        return None, None, (f"{_norm_phs(phs)} has no approved, closed or expired NCI / "
                            "Kids First DAC requests in this data.")
    rr = filter_requests(dac, phs, year_from, year_to, statuses)
    st = filter_statements(dac, phs, year_from, year_to, groups, ai, stages, topics, text,
                           statuses)
    return st, requests_for(st, rr), None


def _base(extra: dict | None = None) -> dict:
    meta = load()[2]
    out = {"as_of": meta["as_of"], "how_to_read": meta["how_to_read"]}
    out.update(extra or {})
    return out


def mcp_summary(dac=None, phs=None, year_from=None, year_to=None, statuses=None,
                groups=None, ai=None, stages=None, topics=None, text=None) -> dict:
    """Counts of planned data use for the filtered statements / requests."""
    st, rq, err = _filters(dac, phs, year_from, year_to, statuses, groups, ai, stages,
                           topics, text)
    if err:
        return _base({"error": err})
    s = summary(st)
    yr = by_year(st)
    top = (rq.groupby(["phs", "study_name"]).size().sort_values(ascending=False).head(10)
           .reset_index(name="requests").to_dict("records"))
    return _base({
        "filters": {k: v for k, v in dict(dac=dac, phs=phs, year_from=year_from,
                                          year_to=year_to, statuses=statuses, groups=groups,
                                          ai=ai, stages=stages, topics=topics,
                                          text=text).items() if v},
        "unique_statements": s["statements"],
        "requests": int(len(rq)),
        "studies": int(rq["phs"].nunique()),
        "requests_by_status": rq["status"].value_counts().to_dict(),
        **{k: v for k, v in s.items() if k != "statements"},
        "by_year": yr.round(3).to_dict("records"),
        "top_studies": top,
    })


def mcp_find_requests(dac=None, phs=None, year_from=None, year_to=None, statuses=None,
                      groups=None, ai=None, stages=None, topics=None, text=None,
                      max_results: int = 25) -> dict:
    """Matching requests (newest approval first) with their statement and evidence."""
    st, rq, err = _filters(dac, phs, year_from, year_to, statuses, groups, ai, stages,
                           topics, text)
    if err:
        return _base({"error": err})
    extra = st.set_index("key_id")[["statement", "group_quote"]]
    rq = rq.join(extra, on="key_id").sort_values("approval_year", ascending=False)
    cols = ["wlid", "phs", "study_name", "DAC", "requestor", "affiliation", "project",
            "approval_year", "status", "group", "ai", "ai_role", "stage", "topic",
            "group_quote", "statement"]
    rows = rq[cols].head(max_results).copy()
    rows["statement"] = rows["statement"].str.slice(0, 600)
    rows["approval_year"] = rows["approval_year"].astype("Int64")
    return _base({"total_matching_requests": int(len(rq)),
                  "unique_statements": int(len(st)),
                  "returned": int(len(rows)),
                  "requests": rows.astype(object).where(rows.notna(), None).to_dict("records")})


def mcp_search(text: str, max_results: int = 20) -> dict:
    """Unique statements containing all the words, with labels and evidence."""
    st = filter_statements(text=text)
    st = st.sort_values("n_requests", ascending=False)
    cols = ["key_id", "group", "ai", "ai_role", "stage", "topic", "first_year",
            "n_requests", "studies", "group_quote", "statement"]
    rows = st[cols].head(max_results).copy()
    rows["statement"] = rows["statement"].str.slice(0, 600)
    rows["first_year"] = rows["first_year"].astype("Int64")
    return _base({"query": text, "matching_statements": int(len(st)),
                  "summary": {k: v for k, v in summary(st).items() if k != "statements"},
                  "returned": int(len(rows)),
                  "statements": rows.astype(object).where(rows.notna(), None).to_dict("records")})


def sunburst_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Three-level table: group > biology stage > clinical topic, with counts."""
    h = df[["group", "stage", "topic"]].copy()
    h.loc[h["group"] != "Biology", ["stage", "topic"]] = ""
    h.loc[h["stage"] != "Clinical", "topic"] = ""
    return h.value_counts().reset_index(name="statements")


def sunburst_nodes(df: pd.DataFrame) -> pd.DataFrame:
    """ids / labels / parents / values for a plotly Sunburst (branchvalues='total')."""
    f = sunburst_frame(df)
    rows = []
    for g, n in f.groupby("group")["statements"].sum().items():
        rows.append((g, g, "", int(n)))
    b = f[(f["group"] == "Biology") & (f["stage"] != "")]
    for st_, n in b.groupby("stage")["statements"].sum().items():
        rows.append((f"Biology/{st_}", st_, "Biology", int(n)))
    c = b[(b["stage"] == "Clinical") & (b["topic"] != "")]
    for tp, n in c.groupby("topic")["statements"].sum().items():
        rows.append((f"Biology/Clinical/{tp}", tp, "Biology/Clinical", int(n)))
    return pd.DataFrame(rows, columns=["id", "label", "parent", "value"])
