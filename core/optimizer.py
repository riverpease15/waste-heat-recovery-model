"""
Greedy job scheduler that minimizes a weighted combination of
TOU electricity cost and peak thermal load.

Pure logic — no Streamlit dependency.
"""

from __future__ import annotations

import numpy as np
from core.constants import (
    TOU_ON_PEAK_RATE, TOU_OFF_PEAK_RATE,
    TOU_ON_PEAK_START, TOU_ON_PEAK_END,
    IDLE_RACK_KW, POWER_LEVELS, is_on_peak, tou_rate,
)


def _slot_hours(n_slots: int) -> np.ndarray:
    """Return the starting hour for each slot (0-based, fractional)."""
    return np.linspace(0, 24, n_slots, endpoint=False)


def _rate_vector(slot_hours: np.ndarray) -> np.ndarray:
    """TOU rate ($/kWh) for each slot."""
    return np.array([tou_rate(h) for h in slot_hours])


def _power_level_label(power_kw: float) -> str:
    """Reverse-lookup the POWER_LEVELS label for a kW value."""
    for label, kw in POWER_LEVELS.items():
        if abs(kw - power_kw) < 0.01:
            return label
    return f"Custom ({power_kw:.0f} kW)"


def optimize_schedule(
    job_specs: list[dict],
    total_racks: int,
    cost_weight: float = 0.5,
    heat_weight: float = 0.5,
    time_resolution_min: int = 30,
) -> dict:
    """
    Schedule jobs to minimise  cost_weight * TOU_cost  +  heat_weight * peak_load.

    Parameters
    ----------
    job_specs : list of dict
        Each entry: {"power_kw": float, "count": int,
                     "duration_hours": float, "racks_per_job": int}
    total_racks : int
        Maximum racks available at any time slot.
    cost_weight, heat_weight : float  (0-1)
        Relative importance of electricity cost vs thermal smoothing.
    time_resolution_min : int
        Slot width in minutes (default 30 → 48 slots per day).

    Returns
    -------
    dict with keys:
        scheduled_jobs  – list[dict] matching session_state format
        summary         – dict with total_cost, peak_load_kw, off_peak_pct,
                          load_profile_kw (per-slot total kW),
                          load_profile_by_tier (dict of tier→per-slot kW)
    """
    slot_min = time_resolution_min
    n_slots = int(24 * 60 / slot_min)
    slot_hours = _slot_hours(n_slots)
    slot_dur_h = slot_min / 60.0
    rates = _rate_vector(slot_hours)

    rack_used = np.zeros(n_slots, dtype=np.int32)
    load_kw = np.zeros(n_slots, dtype=np.float64)

    # Per-tier load tracking for stacked chart
    tier_labels = sorted(
        {spec["power_kw"] for spec in job_specs},
    )
    tier_load = {kw: np.zeros(n_slots, dtype=np.float64) for kw in tier_labels}

    # Expand specs into individual jobs and sort high-power first
    jobs: list[dict] = []
    for spec in job_specs:
        dur_slots = max(1, round(spec["duration_hours"] / slot_dur_h))
        for _ in range(spec["count"]):
            jobs.append({
                "power_kw": spec["power_kw"],
                "racks": spec["racks_per_job"],
                "dur_slots": dur_slots,
                "duration_hours": dur_slots * slot_dur_h,
            })
    jobs.sort(key=lambda j: -j["power_kw"] * j["racks"])

    # Pre-compute normalisation helpers
    max_possible_cost = max(TOU_ON_PEAK_RATE, TOU_OFF_PEAK_RATE) * 24.0
    max_possible_load = total_racks * max(POWER_LEVELS.values())

    scheduled: list[dict] = []
    unscheduled_count = 0

    for job in jobs:
        pw = job["power_kw"]
        racks = job["racks"]
        dur = job["dur_slots"]
        best_score = float("inf")
        best_start = -1

        for s in range(n_slots - dur + 1):
            span = slice(s, s + dur)
            if np.any(rack_used[span] + racks > total_racks):
                continue

            cost_term = float(np.sum(rates[span])) * pw * racks * slot_dur_h
            heat_term = float(np.max(load_kw[span] + pw * racks))

            cost_norm = cost_term / max_possible_cost if max_possible_cost > 0 else 0
            heat_norm = heat_term / max_possible_load if max_possible_load > 0 else 0

            score = cost_weight * cost_norm + heat_weight * heat_norm
            if score < best_score:
                best_score = score
                best_start = s

        if best_start < 0:
            unscheduled_count += 1
            continue

        span = slice(best_start, best_start + dur)
        rack_used[span] += racks
        load_kw[span] += pw * racks
        tier_load[pw][span] += pw * racks

        start_h = float(slot_hours[best_start])
        start_hour = int(start_h)
        start_min = int(round((start_h - start_hour) * 60))
        end_h = start_h + job["duration_hours"]

        scheduled.append({
            "id": len(scheduled),
            "start_hour": start_hour,
            "start_min": start_min,
            "start_time": start_h,
            "duration": job["duration_hours"],
            "end_time": end_h,
            "power_kw": pw,
            "num_racks": racks,
            "power_level": _power_level_label(pw),
        })

    # Summary statistics
    total_cost = 0.0
    on_peak_kwh = 0.0
    off_peak_kwh = 0.0
    for s in range(n_slots):
        h = float(slot_hours[s])
        above_idle = max(0.0, float(load_kw[s]))
        energy = above_idle * slot_dur_h
        cost = energy * float(rates[s])
        total_cost += cost
        if is_on_peak(h):
            on_peak_kwh += energy
        else:
            off_peak_kwh += energy

    total_kwh = on_peak_kwh + off_peak_kwh
    off_peak_pct = (off_peak_kwh / total_kwh * 100) if total_kwh > 0 else 0.0

    load_profile_by_tier = {}
    for kw, arr in tier_load.items():
        load_profile_by_tier[_power_level_label(kw)] = arr.tolist()

    summary = {
        "total_cost": total_cost,
        "on_peak_cost": sum(
            max(0.0, float(load_kw[s])) * slot_dur_h * float(rates[s])
            for s in range(n_slots)
            if is_on_peak(float(slot_hours[s]))
        ),
        "off_peak_cost": sum(
            max(0.0, float(load_kw[s])) * slot_dur_h * float(rates[s])
            for s in range(n_slots)
            if not is_on_peak(float(slot_hours[s]))
        ),
        "total_kwh": total_kwh,
        "on_peak_kwh": on_peak_kwh,
        "off_peak_kwh": off_peak_kwh,
        "off_peak_pct": off_peak_pct,
        "peak_load_kw": float(np.max(load_kw)),
        "load_profile_kw": load_kw.tolist(),
        "load_profile_by_tier": load_profile_by_tier,
        "slot_hours": slot_hours.tolist(),
        "slot_dur_h": slot_dur_h,
        "n_slots": n_slots,
        "unscheduled": unscheduled_count,
    }

    return {"scheduled_jobs": scheduled, "summary": summary}
