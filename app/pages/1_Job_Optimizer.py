import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

st.set_page_config(
    page_title="Job Optimizer — ATL01",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from core.constants import (
    TOU_ON_PEAK_START, TOU_ON_PEAK_END,
    TOU_ON_PEAK_RATE, TOU_OFF_PEAK_RATE,
    IDLE_RACK_KW, POWER_LEVELS, is_on_peak,
)
from core.optimizer import optimize_schedule

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "opt_results" not in st.session_state:
    st.session_state.opt_results = None
if "scheduled_jobs" not in st.session_state:
    st.session_state.scheduled_jobs = []

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.title("⚡ Job Optimizer")
st.markdown(
    "Define your workload by power tier, then let the optimizer find the "
    "cheapest and coolest schedule across a 24-hour window."
)

# ---------------------------------------------------------------------------
# Sidebar — room / rack configuration (mirrors main page defaults)
# ---------------------------------------------------------------------------
num_rows = st.session_state.get("num_rows", 3)
racks_per_row = st.session_state.get("racks_per_row", 20)
total_racks = num_rows * racks_per_row
st.sidebar.header("⚙️ Room Configuration")
st.sidebar.metric("Total Racks", total_racks)
st.sidebar.caption("Configure rows and racks per row on the Data Center Model page.")

# ---------------------------------------------------------------------------
# Workload definition
# ---------------------------------------------------------------------------
st.header("1. Define Your Workload")

tier_colors = {
    "Low (20 kW)": "#00b894",
    "Medium (50 kW)": "#fdcb6e",
    "High (60 kW)": "#ff7675",
}

tier_order = ["Low (20 kW)", "Medium (50 kW)", "High (60 kW)"]

cols = st.columns([2, 1.2, 1.2, 1.2])
cols[0].markdown("**Tier**")
cols[1].markdown("**Job count**")
cols[2].markdown("**Duration (h)**")
cols[3].markdown("**Racks / job**")

specs: list[dict] = []
for tier in tier_order:
    kw = POWER_LEVELS[tier]
    c0, c1, c2, c3 = st.columns([2, 1.2, 1.2, 1.2])
    dot = "🟢" if "Low" in tier else ("🟡" if "Medium" in tier else "🔴")
    c0.markdown(f"{dot} **{tier}**")
    count = c1.number_input(
        "count", min_value=0, max_value=5000, value=0,
        label_visibility="collapsed", key=f"opt_count_{tier}",
    )
    dur = c2.number_input(
        "duration", min_value=0.5, max_value=24.0, value=1.0, step=0.5,
        label_visibility="collapsed", key=f"opt_dur_{tier}",
    )
    rpj = c3.number_input(
        "racks", min_value=1, max_value=total_racks, value=1,
        label_visibility="collapsed", key=f"opt_rpj_{tier}",
    )
    if count > 0:
        specs.append({
            "power_kw": kw,
            "count": int(count),
            "duration_hours": float(dur),
            "racks_per_job": int(rpj),
        })

total_jobs = sum(s["count"] for s in specs)
total_rack_hours = sum(s["count"] * s["duration_hours"] * s["racks_per_job"] for s in specs)

if specs:
    m1, m2 = st.columns(2)
    m1.metric("Total jobs", total_jobs)
    m2.metric("Rack-hours required", f"{total_rack_hours:,.0f}")

st.divider()

# ---------------------------------------------------------------------------
# Priority slider
# ---------------------------------------------------------------------------
st.header("2. Optimization Priority")

priority = st.slider(
    "Slide toward what matters most",
    min_value=0.0, max_value=1.0, value=0.5, step=0.05,
    format="%.2f",
    help="0 = pure cost optimisation (cluster jobs off-peak), "
         "1 = pure thermal optimisation (spread load evenly).",
)
st.markdown(
    '<div style="display:flex;justify-content:space-between;margin-top:-1rem;">'
    '<span style="font-size:0.85rem;color:#aaa;">💰 <b>Lowest Cost</b></span>'
    '<span style="font-size:0.85rem;color:#aaa;">❄️ <b>Lowest Heat</b></span>'
    '</div>',
    unsafe_allow_html=True,
)

cost_w = 1.0 - priority
heat_w = priority

st.divider()

# ---------------------------------------------------------------------------
# Run optimiser
# ---------------------------------------------------------------------------
st.header("3. Results")

run_disabled = len(specs) == 0
if st.button("🔍 Optimize Schedule", type="primary", use_container_width=True, disabled=run_disabled):
    with st.spinner("Scheduling jobs…"):
        result = optimize_schedule(
            job_specs=specs,
            total_racks=total_racks,
            cost_weight=cost_w,
            heat_weight=heat_w,
        )
    st.session_state.opt_results = result
elif run_disabled:
    st.info("Add at least one job tier above to get started.")

results = st.session_state.opt_results

if results is not None:
    summary = results["summary"]
    sched = results["scheduled_jobs"]

    if summary["unscheduled"] > 0:
        st.warning(
            f"**{summary['unscheduled']}** jobs could not be scheduled — "
            "not enough rack capacity. Try reducing job count or racks per job."
        )

    # ── Metrics row ──────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Cost", f"${summary['total_cost']:,.2f}", border=True)
    k2.metric("Peak Load", f"{summary['peak_load_kw']:,.0f} kW", border=True)
    k3.metric("Off-Peak Energy", f"{summary['off_peak_pct']:.0f}%", border=True)
    k4.metric("Total Energy", f"{summary['total_kwh']:,.0f} kWh", border=True)

    # ── Explanation ────────────────────────────────────────────────────
    def _build_explanation(sched, summary, cost_w, heat_w, specs, total_racks):
        total_jobs = len(sched)
        on_pct = 100 - summary["off_peak_pct"]
        off_pct = summary["off_peak_pct"]
        peak = summary["peak_load_kw"]
        cost = summary["total_cost"]
        blended = cost / summary["total_kwh"] if summary["total_kwh"] > 0 else 0

        if cost_w > 0.7:
            strategy = "heavily toward **minimizing electricity cost**"
        elif cost_w > 0.55:
            strategy = "slightly toward **minimizing cost** while still considering heat"
        elif heat_w > 0.7:
            strategy = "heavily toward **minimizing thermal load**"
        elif heat_w > 0.55:
            strategy = "slightly toward **reducing thermal peaks** while still considering cost"
        else:
            strategy = "to **balance cost and thermal load equally**"

        lines = [f"The optimizer placed **{total_jobs} jobs** across 24 hours "
                 f"with the priority slider set {strategy}.\n"]

        if off_pct >= 95:
            lines.append(
                f"Nearly all energy ({off_pct:.0f}%) was scheduled during **off-peak hours** "
                f"(outside {TOU_ON_PEAK_START}:00–{TOU_ON_PEAK_END}:00), "
                f"taking advantage of the cheaper \\${TOU_OFF_PEAK_RATE:.4f}/kWh rate. "
                f"This keeps the blended rate low at **\\${blended:.4f}/kWh**."
            )
        elif off_pct >= 70:
            lines.append(
                f"Most energy ({off_pct:.0f}%) runs off-peak, but some jobs were pushed into "
                f"on-peak hours to **spread the load** and reduce the thermal peak. "
                f"The blended rate is \\${blended:.4f}/kWh — higher than pure off-peak "
                f"but the peak load is held to **{peak:,.0f} kW**."
            )
        else:
            lines.append(
                f"Jobs are spread broadly across all hours to **minimize thermal peaks**, "
                f"with {on_pct:.0f}% of energy running during on-peak hours. "
                f"This raises the blended rate to \\${blended:.4f}/kWh but keeps "
                f"the peak load at only **{peak:,.0f} kW**."
            )

        tier_counts = {}
        for j in sched:
            tier_counts[j["power_level"]] = tier_counts.get(j["power_level"], 0) + 1
        high_count = tier_counts.get("High (60 kW)", 0)
        if high_count > 0 and cost_w >= 0.3:
            lines.append(
                f"\nHigh-power jobs ({high_count} at 60 kW) were prioritized for off-peak "
                f"placement first since they benefit the most from cheaper rates — "
                f"each hour of a 60 kW job costs "
                f"\\${60 * TOU_ON_PEAK_RATE:.2f} on-peak vs \\${60 * TOU_OFF_PEAK_RATE:.2f} off-peak."
            )

        capacity_pct = peak / (total_racks * 60) * 100 if total_racks > 0 else 0
        if capacity_pct > 80:
            lines.append(
                f"\nPeak utilization reaches **{capacity_pct:.0f}%** of rack capacity — "
                f"the schedule is tightly packed. Adding more jobs may require "
                f"more racks or longer scheduling windows."
            )
        elif capacity_pct > 50:
            lines.append(
                f"\nPeak utilization is **{capacity_pct:.0f}%** of rack capacity, "
                f"leaving headroom for additional workloads."
            )

        if summary["unscheduled"] > 0:
            lines.append(
                f"\n**{summary['unscheduled']} jobs could not fit** within the "
                f"available {total_racks} racks. Consider reducing racks per job "
                f"or splitting into shorter durations."
            )

        return "\n".join(lines)

    with st.container(border=True):
        st.markdown("##### Why this schedule?")
        st.markdown(_build_explanation(sched, summary, cost_w, heat_w, specs, total_racks))

    # ── Load profile chart ───────────────────────────────────────────────
    st.subheader("24-Hour Load Profile")

    slot_hours = np.array(summary["slot_hours"])
    fig, ax = plt.subplots(figsize=(14, 4.5))

    # On-peak shading
    ax.axvspan(TOU_ON_PEAK_START, TOU_ON_PEAK_END,
               color="red", alpha=0.08, label="On-peak window")

    # Stacked area by tier
    bottom = np.zeros(len(slot_hours))
    for tier in tier_order:
        if tier in summary["load_profile_by_tier"]:
            vals = np.array(summary["load_profile_by_tier"][tier])
            ax.fill_between(
                slot_hours, bottom, bottom + vals,
                color=tier_colors[tier], alpha=0.75, label=tier,
                step="post",
            )
            bottom += vals

    ax.set_xlim(0, 24)
    ax.set_ylim(0, None)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Load (kW)")
    ax.xaxis.set_major_locator(mticker.MultipleLocator(2))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):02d}:00"))
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    # ── Cost breakdown ───────────────────────────────────────────────────
    with st.expander("Cost Breakdown", expanded=False):
        cb1, cb2, cb3 = st.columns(3)
        cb1.metric("Off-Peak Cost",
                    f"${summary['off_peak_cost']:,.2f}",
                    help=f"{summary['off_peak_kwh']:,.0f} kWh × "
                         f"${TOU_OFF_PEAK_RATE:.4f}/kWh")
        cb2.metric("On-Peak Cost",
                    f"${summary['on_peak_cost']:,.2f}",
                    help=f"{summary['on_peak_kwh']:,.0f} kWh × "
                         f"${TOU_ON_PEAK_RATE:.4f}/kWh")
        cb3.metric("Blended Rate",
                    f"${summary['total_cost'] / summary['total_kwh']:.4f}/kWh"
                    if summary["total_kwh"] > 0 else "—")

    # ── Timeline visualisation (Gantt) ───────────────────────────────────
    st.subheader("Optimized Timeline")

    sorted_jobs = sorted(sched, key=lambda j: (j["start_time"], j["power_kw"]))

    def jobs_overlap(j1, j2):
        if j1["end_time"] <= 24.0:
            int1 = [(j1["start_time"], j1["end_time"])]
        else:
            int1 = [(j1["start_time"], 24.0), (0.0, j1["end_time"] - 24.0)]
            
        if j2["end_time"] <= 24.0:
            int2 = [(j2["start_time"], j2["end_time"])]
        else:
            int2 = [(j2["start_time"], 24.0), (0.0, j2["end_time"] - 24.0)]
            
        for s1, e1 in int1:
            for s2, e2 in int2:
                if max(s1, s2) < min(e1, e2) - 1e-5:
                    return True
        return False

    # Build rows: bin jobs by overlapping time so they stack vertically
    rows: list[list[dict]] = []
    for job in sorted_jobs:
        placed = False
        for row in rows:
            if not any(jobs_overlap(job, rj) for rj in row):
                row.append(job)
                placed = True
                break
        if not placed:
            rows.append([job])

    n_rows_vis = min(len(rows), 12)

    job_blocks_html = ""
    row_height_px = 32
    gap_px = 4
    for row_idx in range(n_rows_vis):
        for job in rows[row_idx]:
            blocks = []
            start_h = job["start_time"]
            end_h = job["end_time"]
            
            sh_h = int(start_h)
            sh_m = int(round((start_h - sh_h) * 60)) % 60
            eh_h = int(end_h) % 24
            eh_m = int(round((end_h - int(end_h)) * 60)) % 60
            time_str = f"{sh_h:02d}:{sh_m:02d}–{eh_h:02d}:{eh_m:02d}"
            
            if end_h > 24.0:
                blocks.append((start_h, 24.0))
                blocks.append((0.0, end_h - 24.0))
            else:
                blocks.append((start_h, end_h))
                
            for b_start, b_end in blocks:
                left_pct = (b_start / 24.0) * 100
                width_pct = max(0.4, ((b_end - b_start) / 24.0) * 100)
                top_px = row_idx * (row_height_px + gap_px)
                tier_class = (
                    "job-low" if "Low" in job["power_level"]
                    else "job-medium" if "Medium" in job["power_level"]
                    else "job-high"
                )
                dot = "🟢" if "Low" in job["power_level"] else ("🟡" if "Medium" in job["power_level"] else "🔴")
                job_blocks_html += (
                    f'<div class="job-block {tier_class}" '
                    f'style="left:{left_pct:.2f}%;width:{width_pct:.2f}%;'
                    f'top:{top_px}px;height:{row_height_px}px;" '
                    f'title="{job["power_level"]} | {time_str}'
                    f' | {job["num_racks"]}R">'
                    f'{dot}</div>'
                )

    hour_labels_html = "".join(f'<div class="tl-hour">{h:02d}</div>' for h in range(24))
    grid_height = n_rows_vis * (row_height_px + gap_px) + 10
    overflow_note = ""
    if len(rows) > n_rows_vis:
        overflow_note = (
            f'<div style="color:#bdc3c7;font-size:12px;margin-top:6px;">'
            f'Showing {n_rows_vis} of {len(rows)} visual rows '
            f'({len(sched)} total jobs)</div>'
        )

    timeline_html = f"""
    <style>
        .opt-cal {{
            background: linear-gradient(180deg,#2d3436 0%,#34495e 100%);
            border-radius: 12px; padding: 16px 20px; margin: 10px 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }}
        .tl-hours {{
            display:flex; justify-content:space-between;
            color:#bdc3c7; font-size:11px; font-weight:600;
            margin-bottom:6px; padding:0 2px;
        }}
        .tl-hour {{ width:calc(100%/24); text-align:center; }}
        .tl-grid {{
            position:relative; height:{grid_height}px; overflow:hidden;
            background: repeating-linear-gradient(90deg,
                rgba(255,255,255,0.05) 0px, rgba(255,255,255,0.05) 1px,
                transparent 1px, transparent calc(100%/24));
            border:2px solid rgba(255,255,255,0.2); border-radius:8px;
        }}
        .job-block {{
            position:absolute; border-radius:4px;
            display:flex; align-items:center; justify-content:center;
            font-size:11px; color:white;
            box-shadow:0 1px 4px rgba(0,0,0,0.4);
            border:1px solid rgba(255,255,255,0.25);
            cursor:default;
        }}
        .job-low    {{ background:linear-gradient(135deg,#00b894,#00cec9); }}
        .job-medium {{ background:linear-gradient(135deg,#fdcb6e,#f39c12); }}
        .job-high   {{ background:linear-gradient(135deg,#ff7675,#d63031); }}
    </style>
    <div class="opt-cal">
        <div class="tl-hours">{hour_labels_html}</div>
        <div class="tl-grid">{job_blocks_html}</div>
        {overflow_note}
    </div>
    """
    st.markdown(timeline_html, unsafe_allow_html=True)

    # ── Accept button ────────────────────────────────────────────────────
    st.divider()
    st.header("4. Accept & Simulate")
    st.markdown(
        "Push this optimized schedule to the **Thermal Model** page and "
        "run the full simulation."
    )
    if st.button("✅ Accept & Simulate", type="primary", use_container_width=True):
        st.session_state.scheduled_jobs = list(sched)
        st.session_state.sim_data = None
        st.session_state.sim_frame = 0
        st.session_state.sim_fingerprint = None
        st.session_state.sim_stale = False
        st.session_state.sim_playing = False
        st.session_state.tou_costs = None
        st.session_state.auto_run_sim = True
        st.switch_page("Data_Center_Model.py")
