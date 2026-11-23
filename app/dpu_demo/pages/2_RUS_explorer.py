"""RUS explorer: what approved requesters plan to do with NCI / Kids First dbGaP data.

Reads pre-computed results (data/rus/, see rus_data.py). No LLM calls on this page.
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rus_data as rd  # noqa: E402

st.set_page_config(page_title="RUS explorer", layout="wide")

S, R, META = rd.load()
GROUP_ORDER = list(rd.GROUP_LABELS.values())
STAGE_ORDER = list(rd.STAGE_LABELS.values())
TOPIC_ORDER = list(rd.TOPIC_LABELS.values())
AI_OPTIONS = ["Uses AI", "Build AI", "Apply AI", "No AI", "AI flag differs"]
YEARS = R["approval_year"].dropna().astype(int)
YMIN, YMAX = int(YEARS.min()), int(YEARS.max())

st.title("What do approved requesters plan to do with the data?")
st.caption(
    f"dbGaP Public Research Use Statements, NCI DAC and Kids First DAC. Data as of "
    f"{META['as_of']}: {META['requests']:,} requests (approved, closed, expired; "
    f"rejected removed), "
    f"{META['unique_statements']:,} unique statements. Classified by two AI models; "
    "'models differ' = the two models disagreed."
)

# ---------------------------------------------------------------- filters
with st.sidebar:
    st.header("Filters")
    dac = st.selectbox("DAC", ["All", "NCI DAC", "Kids First DAC"])
    phs = st.text_input("Study (phs number)", placeholder="e.g. phs002371")
    statuses = st.multiselect("Request status", rd.STATUSES, default=rd.DEFAULT_STATUSES,
                              help="Rejected requests are not included (removed before "
                                   "classification).")
    yr = st.slider("Approval year", YMIN, YMAX, (YMIN, YMAX))
    groups = st.multiselect("Main group", GROUP_ORDER)
    ai = st.multiselect("AI use", AI_OPTIONS)
    stages = st.multiselect("Biology stage", STAGE_ORDER)
    topics = st.multiselect("Clinical topic", TOPIC_ORDER)
    text = st.text_input("Words in the statement", placeholder="e.g. single cell")
    st.caption("DAC, study, status and year filter on the requests that use a statement.")

Y0 = yr[0] if yr[0] > YMIN else None
Y1 = yr[1] if yr[1] < YMAX else None
STATUS_SEL = statuses or rd.STATUSES
RR = rd.filter_requests(dac, phs or None, Y0, Y1, STATUS_SEL)
df = rd.filter_statements(
    dac=dac, phs=phs or None, year_from=Y0, year_to=Y1, statuses=STATUS_SEL,
    groups=groups or None, ai=ai or None, stages=stages or None,
    topics=topics or None, text=text or None,
)
if phs and rd._norm_phs(phs) is None:
    st.warning("Study filter ignored: type a phs number such as phs002371.")
if df.empty:
    st.info("No statements match these filters.")
    st.stop()

sm = rd.summary(df)
req = rd.requests_for(df, RR)
bio_n = sum(sm["biology_by_stage"].values())
clin_n = sm["biology_by_stage"].get("Clinical", 0)

c = st.columns(5)
c[0].metric("Unique statements", f"{sm['statements']:,}")
c[1].metric("Requests", f"{len(req):,}")
c[2].metric("Studies", f"{req['phs'].nunique():,}")
c[3].metric("Use AI", f"{sm['uses_ai_share']:.0%}", help=f"{sm['uses_ai']:,} statements")
c[4].metric("Clinical share of biology", f"{clin_n / bio_n:.0%}" if bio_n else "-")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Trends", "Statements", "Requests",
                                        "Request status"])

# ---------------------------------------------------------------- overview
with tab1:
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Grouping")
        st.caption("How to read: inner ring = main group; biology splits into stage, "
                   "clinical splits into topic. Click a slice to zoom in.")
        nd = rd.sunburst_nodes(df)
        fig = go.Figure(go.Sunburst(ids=nd["id"], labels=nd["label"], parents=nd["parent"],
                                    values=nd["value"], branchvalues="total",
                                    textinfo="label+value+percent root"))
        fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Main group")
        g = pd.DataFrame(sm["by_group"].items(), columns=["group", "statements"])
        g["order"] = g["group"].map({k: i for i, k in enumerate(GROUP_ORDER)})
        st.dataframe(g.sort_values("order").drop(columns="order"), hide_index=True,
                     use_container_width=True)
        st.subheader("AI use")
        a = pd.DataFrame(sm["ai_role"].items(), columns=["AI role", "statements"])
        st.dataframe(a, hide_index=True, use_container_width=True)
        st.caption(f"Data platform built or hosted for others: {sm['data_platform_built']} statements.")

# ---------------------------------------------------------------- trends
with tab2:
    st.caption("How to read: each statement is counted once, in the earliest approval "
               f"year of the requests that use it. {META['as_of'][:4]} is a partial year.")
    t = rd.by_year(df)
    if t.empty:
        st.info("No dated statements.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            f1 = px.bar(t, x="year", y=["build_ai", "apply_ai"], barmode="group",
                        labels={"value": "statements", "variable": ""},
                        title="AI statements per year: build vs apply")
            st.plotly_chart(f1, use_container_width=True)
        with c2:
            tl = t.melt(id_vars="year", value_vars=["ai_share", "tool_share",
                                                    "clinical_share_of_biology"],
                        var_name="measure", value_name="share")
            tl["measure"] = tl["measure"].map({"ai_share": "Use AI", "tool_share": "Tool",
                                               "clinical_share_of_biology": "Clinical share of biology"})
            f2 = px.line(tl, x="year", y="share", color="measure", markers=True,
                         title="Shares per year")
            f2.update_yaxes(tickformat=".0%")
            st.plotly_chart(f2, use_container_width=True)
        st.plotly_chart(px.bar(t, x="year", y="statements", title="New statements per year"),
                        use_container_width=True)

# ---------------------------------------------------------------- statements
with tab3:
    st.caption("One row per unique statement. Evidence quote and reason are from the first model.")
    cols = ["key_id", "group", "ai", "ai_role", "stage", "topic", "first_year", "n_requests",
            "studies", "statement", "group_quote", "group_why"]
    show = df[cols].sort_values(["first_year", "key_id"], ascending=[False, True])
    st.dataframe(show, hide_index=True, use_container_width=True, height=480)
    st.download_button("Download statements (CSV)", show.to_csv(index=False),
                       "rus_statements_filtered.csv", "text/csv")
    pick = st.selectbox("Read one statement", show["key_id"].head(200).tolist())
    if pick:
        rowp = df[df["key_id"] == pick].iloc[0]
        st.markdown(f"**{rowp['group']}** | {rowp['ai']} {rowp['ai_role']} | "
                    f"{rowp['stage']} {rowp['topic']}")
        st.write(rowp["statement"])
        st.caption(f"Evidence: \"{rowp['group_quote']}\"  Reason: {rowp['group_why']}")

# ---------------------------------------------------------------- requests
with tab4:
    st.caption("One row per request that uses a matching statement.")
    rc = ["wlid", "phs", "study_name", "DAC", "requestor", "affiliation", "project",
          "approval_year", "status", "group", "ai", "ai_role", "stage", "topic", "key_id"]
    st.dataframe(req[rc], hide_index=True, use_container_width=True, height=480)
    st.download_button("Download requests (CSV)", req[rc].to_csv(index=False),
                       "rus_requests_filtered.csv", "text/csv")
    top = req.groupby(["phs", "study_name"]).size().sort_values(ascending=False).head(15)
    st.subheader("Top studies in this selection")
    st.dataframe(top.reset_index(name="requests"), hide_index=True, use_container_width=True)

# ---------------------------------------------------------------- request status
with tab5:
    st.caption("How to read: requests matching the DAC, study, year and status filters "
               "(group / AI / stage / topic / word filters are not applied here), split "
               "by main group. Rejected requests are not included.")
    sc = rd.status_counts(RR)
    if sc.empty:
        st.info("No requests match.")
    else:
        f3 = px.bar(sc, x="status", y="requests", color="group", text_auto=False,
                    category_orders={"status": rd.STATUSES,
                                     "group": GROUP_ORDER + [rd.NOT_CLASSIFIED]},
                    title="Requests by status and main group")
        st.plotly_chart(f3, use_container_width=True)
        pv = sc.pivot_table(index="group", columns="status", values="requests",
                            aggfunc="sum", fill_value=0)
        pv = pv.reindex(columns=[c for c in rd.STATUSES if c in pv.columns])
        pv["total"] = pv.sum(axis=1)
        st.dataframe(pv, use_container_width=True)
        sy = RR.dropna(subset=["approval_year"]).groupby(
            [RR["approval_year"].dropna().astype(int), "status"]).size().reset_index(name="requests")
        sy.columns = ["year", "status", "requests"]
        st.plotly_chart(px.bar(sy, x="year", y="requests", color="status",
                               category_orders={"status": rd.STATUSES},
                               title="Requests by approval year and status"),
                        use_container_width=True)

with st.expander("Method and how to read"):
    st.write(META["method"])
    for line in META["how_to_read"]:
        st.markdown(f"- {line}")
