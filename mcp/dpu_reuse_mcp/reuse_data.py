"""Read-only query logic for the DPU data-reuse MCP server.

Reads the public results tables (CSV snapshot of the DPU pipeline tools) from
./data and answers three questions for one dataset:
  1. who_reuses       - which papers reuse the data
  2. where_from       - where reusers got the data (and what they combined it with)
  3. who_funds_reuse  - which funders support the reuse papers

No network calls, no writes. The pipeline tools are never run from here.
Input: a dbGaP phs accession, the PMID of the paper that generated the data, or words
from the study title (search_studies).
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from functools import lru_cache

import pandas as pd

DATA_DIR = os.getenv(
    "DPU_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
)

# Tool 1 (accession named in paper) decisions counted as reuse.
TOOL1_REUSE = {"Confirmed use", "Probable use"}
TOOL1_REVIEW = {"Possible use", "Unclassified (review)", "Weak evidence"}
# Tool 2 (cites the seed paper) decisions counted as reuse start with "Used".
TOOL2_REUSE_PREFIX = "Used"
UNNAMED_SOURCE = "(source not named in the sentence)"
QUOTE_MAX = 400

_PHS_RE = re.compile(r"^(phs\d{6})(\.v\d+(\.p\d+)?)?$", re.IGNORECASE)
_PMID_RE = re.compile(r"^(?:pmid:?\s*)?(\d{6,9})$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def tables() -> dict:
    """Load all tables once (strings only, blanks as '')."""

    def read(name: str) -> pd.DataFrame:
        return pd.read_csv(
            os.path.join(DATA_DIR, name), dtype=str, keep_default_na=False
        )

    with open(os.path.join(DATA_DIR, "studies.json"), encoding="utf-8") as fh:
        studies = json.load(fh)
    return {
        "studies": studies,
        "papers": read("papers.csv"),            # Tool 1 decisions
        "tool2": read("tool2_papers.csv"),       # Tool 2 decisions
        "tool2_sources": read("tool2_sources.csv"),
        "pathways": read("pathways.csv"),
        "grants": read("grants.csv"),
    }


def as_of() -> str:
    return tables()["studies"].get("as_of", "")


def _short(text: str, n: int = QUOTE_MAX) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 3] + "..."


# --------------------------------------------------------------------------
# Study search: words -> matching studies (by title, short name, label)
# --------------------------------------------------------------------------
_STOPWORDS = {"the", "of", "a", "an", "and", "or", "for", "in", "on", "with", "to", "from",
              "data", "dataset", "datasets", "study", "studies", "dbgap", "project", "by"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def search_studies(term: str, max_results: int = 10) -> dict:
    """Find studies whose title / short name / label / collection contain the search words.

    A word matches when a word in the study text starts with it (e.g. 'atlas' matches
    'Atlas', 'melan' matches 'Melanoma'). score = share of search words matched.
    """
    studies = tables()["studies"]["studies"]
    query = [w for w in _words(term) if w not in _STOPWORDS] or _words(term)
    hits = []
    for phs, s in studies.items():
        text = " ".join(str(s.get(k, "")) for k in ("title", "short_name", "label", "collection"))
        words = _words(text)  # phs numbers are not prefix-matched (a typo must not auto-resolve)
        matched = [q for q in query if any(w.startswith(q) for w in words)]
        if matched:
            hits.append((len(matched) / len(query), phs, s))
    hits.sort(key=lambda h: (-h[0], h[1]))
    matches = []
    for score, phs, s in hits[:max_results]:
        matches.append({
            "accession": phs,
            "title": s.get("title") or s.get("label", ""),
            "collection": s.get("collection", ""),
            "seed_pmids": s.get("source_pmids", []),
            "reuse_papers": int(len(_reuse_papers(phs, False))),
            "match_score": round(score, 2),
        })
    return {
        "term": term,
        "search_words": query,
        "matches": matches,
        "full_matches": sum(1 for h in hits if h[0] == 1.0),
        "as_of": as_of(),
        "how_to_read": (
            "Studies whose title, short name or collection contain the search words. "
            "match_score 1.0 = all words found. reuse_papers = Tool 1 + Tool 2 reuse papers. "
            "Use the accession (phs) with the other tools."
        ),
    }


# --------------------------------------------------------------------------
# Input resolution: phs, PMID or study name -> list of phs accessions
# --------------------------------------------------------------------------
def resolve(identifier: str) -> dict:
    """Turn a phs accession, seed-paper PMID or study name into known study accessions."""
    t = tables()
    studies = t["studies"]["studies"]
    raw = (identifier or "").strip()

    m = _PHS_RE.match(raw)
    if m:
        phs = m.group(1).lower()
        if phs in studies:
            return {"input": raw, "accessions": [phs], "matched_by": "phs accession"}
        return _not_found(raw, f"{phs} is not in the results table yet.")

    m = _PMID_RE.match(raw)
    if m:
        pmid = m.group(1)
        hits: dict[str, str] = {}
        for phs, s in studies.items():
            if pmid in s.get("source_pmids", []):
                hits.setdefault(phs, "seed paper listed for the study")
        src = t["tool2_sources"]
        for phs in src.loc[src["source_pmid"].str.replace(".0", "", regex=False) == pmid, "accession"]:
            hits.setdefault(phs, "seed paper (dbGaP study page or Tool 1)")
        p = t["papers"]
        gen = p[(p["pmid"] == pmid) & p["decision"].str.startswith("Generated")]
        for phs in gen["accession"]:
            hits.setdefault(phs, "paper that generated the data (Tool 1 rule E)")
        if hits:
            return {
                "input": raw,
                "accessions": sorted(hits),
                "matched_by": "seed PMID",
                "match_basis": hits,
            }
        reuse_of = sorted(set(p.loc[(p["pmid"] == pmid) & p["decision"].isin(TOOL1_REUSE), "accession"]))
        note = (
            f"PMID {pmid} is a REUSE paper of {', '.join(reuse_of)}, not a seed paper. "
            "Ask about the phs accession instead." if reuse_of else
            f"PMID {pmid} is not a known seed (data-generating) paper."
        )
        return _not_found(raw, note)

    # Study name or title words
    found = search_studies(raw, max_results=10)
    full = [m for m in found["matches"] if m["match_score"] == 1.0]
    if len(full) == 1:
        return {"input": raw, "accessions": [full[0]["accession"]], "matched_by": "study name",
                "matched_title": full[0]["title"]}
    if found["matches"]:
        return {
            "input": raw,
            "accessions": [],
            "error": (f"Several studies match '{raw}'. Ask the user which one, then use its phs number."
                       if len(full) > 1 else
                       f"No study matches all words of '{raw}'. Closest studies are listed."),
            "candidates": found["matches"],
        }
    return _not_found(raw, f"No study matches '{raw}'. Input must be a phs accession (e.g. phs001493), "
                           "a seed-paper PMID (e.g. 29301960), or words from a study title (e.g. HTAN).")


def _not_found(raw: str, reason: str) -> dict:
    studies = tables()["studies"]["studies"]
    return {
        "input": raw,
        "accessions": [],
        "error": reason,
        "available_studies": [
            {"accession": phs, "title": studies[phs].get("title") or studies[phs].get("label", "")}
            for phs in sorted(studies)
        ],
    }


def _study_info(phs: str) -> dict:
    s = tables()["studies"]["studies"].get(phs, {})
    return {
        "accession": phs,
        "version": s.get("version", ""),
        "title": s.get("title", ""),
        "collection": s.get("collection", ""),
        "seed_pmids": s.get("source_pmids", []),
        "citation_scan_tool2": s.get("tool2", "not run"),
        "citation_scan_note": s.get("tool2_note", ""),
    }


# --------------------------------------------------------------------------
# 1. Who is reusing the data
# --------------------------------------------------------------------------
def _reuse_papers(phs: str, include_review: bool) -> pd.DataFrame:
    """One row per reuse paper (PMID), both routes merged."""
    t = tables()
    keep = TOOL1_REUSE | (TOOL1_REVIEW if include_review else set())
    p = t["papers"]
    a = p[(p["accession"] == phs) & p["decision"].isin(keep)].copy()
    a = pd.DataFrame({
        "pmid": a["pmid"], "year": a["year"], "title": a["title"],
        "journal": a["journal"], "first_author": a["first_author"],
        "decision": a["decision"], "rule": a["deciding_rule"],
        "section": a["deciding_section"], "quote": a["deciding_quote"],
        "approved_requester_author": a["approved_requester_author"].eq("True"),
        "matched_requesters": a["matched_requesters"],
        "route": "accession named in paper (Tool 1)",
    })
    q = t["tool2"]
    b = q[(q["accession"] == phs) & q["decision"].str.startswith(TOOL2_REUSE_PREFIX)].copy()
    if not include_review:
        b = b[~b["decision"].str.contains("review")]
    b = pd.DataFrame({
        "pmid": b["pmid"], "year": b["year"], "title": b["title"],
        "journal": b["journal"], "first_author": b["first_author"],
        "decision": b["decision"], "rule": b["rule"], "section": "",
        "quote": b["deciding_quote"],
        "approved_requester_author": b["approved_requester_author"].eq("True"),
        "matched_requesters": "",
        "route": "cites seed paper, uses its data (Tool 2, preliminary)",
    })
    b = b[~b["pmid"].isin(set(a["pmid"]))]  # Tool 1 wins on overlap
    out = pd.concat([a, b], ignore_index=True).drop_duplicates("pmid")
    return out.sort_values(["year", "pmid"], ascending=False)


def who_reuses(identifier: str, include_review: bool = False, max_papers: int = 25) -> dict:
    r = resolve(identifier)
    if not r["accessions"]:
        return r
    results = []
    for phs in r["accessions"]:
        df = _reuse_papers(phs, include_review)
        results.append({
            "study": _study_info(phs),
            "summary": {
                "reuse_papers": int(len(df)),
                "by_route": {k: int(v) for k, v in df["route"].value_counts().items()},
                "by_decision": {k: int(v) for k, v in df["decision"].value_counts().items()},
                "by_year": {k: int(v) for k, v in sorted(df["year"].value_counts().items())},
                "papers_with_approved_dbgap_requester_author": int(df["approved_requester_author"].sum()),
                "top_journals": dict(Counter(df["journal"]).most_common(5)),
            },
            "papers_shown": int(min(len(df), max_papers)),
            "papers": [
                {**row, "quote": _short(row["quote"])}
                for row in df.head(max_papers).to_dict("records")
            ],
        })
    return {
        "question": "Who is reusing this dataset?",
        "resolved": r,
        "as_of": as_of(),
        "results": results,
        "how_to_read": (
            "Reuse = Tool 1 'Confirmed use' or 'Probable use' (paper names the phs) plus "
            "Tool 2 'Used (data access stated)' (paper cites the seed paper and says it used the data). "
            "Set include_review=true to add borderline papers. Every paper shows the quoted sentence "
            "that decided it. Confidence labels are rule-based, experience-based priors, not a validated score."
        ),
    }


# --------------------------------------------------------------------------
# 2. Where do people get the data
# --------------------------------------------------------------------------
def _source_table(df: pd.DataFrame, top_n: int) -> list[dict]:
    named = df[df["data_source_group"] != UNNAMED_SOURCE]
    g = (named.groupby("data_source_group")
         .agg(papers=("pmid", "nunique"), mentions=("pmid", "size"))
         .sort_values(["papers", "mentions"], ascending=False)
         .head(top_n).reset_index())
    return [{"source": s, "papers": int(p), "mentions": int(m)}
            for s, p, m in g.itertuples(index=False)]


def where_from(identifier: str, top_n: int = 15, max_examples: int = 10) -> dict:
    r = resolve(identifier)
    if not r["accessions"]:
        return r
    pw = tables()["pathways"]
    results = []
    for phs in r["accessions"]:
        d = pw[(pw["accession"] == phs) & (pw["positive_group"] == "Reuse")]
        this = d[d["scope"] == "this dataset"]
        other = d[(d["scope"] == "other data in paper") & d["direction"].isin(["obtained", "analysed"])]
        ex = this[this["data_source_group"] != UNNAMED_SOURCE].head(max_examples)
        results.append({
            "study": _study_info(phs),
            "reuse_papers_with_pathway_sentences": int(d["pmid"].nunique()),
            "this_dataset": {
                "where_reusers_say_they_got_it": _source_table(this, top_n),
                "by_direction": {k: int(v) for k, v in this["direction"].value_counts().items()},
                "sentences_without_named_source": int((this["data_source_group"] == UNNAMED_SOURCE).sum()),
            },
            "other_data_combined_with_it": _source_table(other, top_n),
            "examples": [
                {"pmid": e["pmid"], "year": e["year"], "source": e["data_source_group"],
                 "direction": e["direction"], "section": e["section"], "quote": _short(e["quote"])}
                for e in ex.to_dict("records")
            ],
        })
    return {
        "question": "Where do people get the data they reuse?",
        "resolved": r,
        "as_of": as_of(),
        "results": results,
        "how_to_read": (
            "'this_dataset' = sentences in reuse papers about THIS study's data and the repository or "
            "portal they name (e.g. dbGaP, GDC). 'other_data_combined_with_it' = other sources the same "
            "papers obtained or analysed (e.g. TCGA, GEO). papers = distinct PMIDs; mentions = sentences. "
            "Based on Tool 1 reuse papers only (full text from Europe PMC / NCBI)."
        ),
    }


# --------------------------------------------------------------------------
# 3. Who funds the reuse
# --------------------------------------------------------------------------
def who_funds_reuse(identifier: str, include_personnel: bool = False, top_n: int = 20) -> dict:
    r = resolve(identifier)
    if not r["accessions"]:
        return r
    g = tables()["grants"]
    results = []
    for phs in r["accessions"]:
        d = g[(g["accession"] == phs) & (g["positive_group"] == "Reuse")]
        counted = d[d["counted"] == "True"]
        f = (counted.groupby("funder_normalised")
             .agg(papers=("pmid", "nunique"),
                  grants=("grant_key", lambda s: s[s != ""].nunique()))
             .sort_values(["papers", "grants"], ascending=False)
             .head(top_n).reset_index())
        funders = []
        for name, papers, grants in f.itertuples(index=False):
            ids = counted.loc[(counted["funder_normalised"] == name) & (counted["grant_id"] != ""), "grant_id"]
            funders.append({
                "funder": name,
                "reuse_papers": int(papers),
                "distinct_grants": int(grants),
                "example_grant_ids": list(dict.fromkeys(ids))[:5],
            })
        out = {
            "study": _study_info(phs),
            "summary": {
                "reuse_papers_with_funding_text": int(d["pmid"].nunique()),
                "reuse_papers_with_counted_funder": int(counted["pmid"].nunique()),
                "distinct_counted_funders": int(counted["funder_normalised"].nunique()),
                "papers_with_nih_funder": int(counted.loc[counted["funder_normalised"].str.contains("NIH"), "pmid"].nunique()),
                "rows_by_role": {k: int(v) for k, v in d["role"].value_counts().items()},
            },
            "top_funders": funders,
        }
        if include_personnel:
            per = d[d["role"] == "personnel"]
            pc = per.groupby("funder_normalised")["pmid"].nunique().sort_values(ascending=False).head(top_n)
            out["personnel_support_not_counted"] = [{"funder": k, "reuse_papers": int(v)} for k, v in pc.items()]
        results.append(out)
    return {
        "question": "Who funds the reuse of this dataset?",
        "resolved": r,
        "as_of": as_of(),
        "results": results,
        "how_to_read": (
            "Counted funders = research funding + infrastructure (e.g. P30, UL1) named in the reuse "
            "papers' acknowledgements, funding section or Europe PMC metadata. Personnel support "
            "(F, T, K awards, fellowships) is NOT counted; set include_personnel=true to list it. "
            "NIH funders appear as 'NIH/<IC>'. Based on Tool 1 reuse papers."
        ),
    }
