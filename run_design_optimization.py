#!/usr/bin/env python3
"""
Monte Carlo optimization for data center design parameters.

This script mirrors the core physics and power equations from app/Data_Center_Model.py
and searches for strong parameter sets across energy and TOU electricity cost.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from dataclasses import asdict, dataclass
from typing import Dict, List

import numpy as np

from core.constants import TOU_ON_PEAK_RATE, TOU_OFF_PEAK_RATE, is_on_peak


RHO = 1.184
CP = 1007.0
CP_WATER = 4180.0
T_SUPPLY_C = 22.8
CODA_TOTAL_CAPACITY_KW = 7100.0


@dataclass
class Candidate:
    room_length: float
    room_width: float
    room_height: float
    num_rows: int
    racks_per_row: int
    rack_power_kw: float
    dclc_effectiveness: float
    rdhx_effectiveness: float
    num_heat_exchangers: int
    hx_capacity_kw: float
    num_air_handlers: int
    cfm_per_handler: float
    inlet_temp_c: float
    cdu_flow_gpm: float
    num_cdus: int
    delta_p_kpa: float
    pump_eta: float
    cop: float
    wall_u: float
    floor_u: float


def sample_candidate(rng: random.Random) -> Candidate:
    return Candidate(
        room_length=rng.uniform(20.0, 35.0),
        room_width=rng.uniform(15.0, 28.0),
        room_height=rng.uniform(4.0, 7.0),
        num_rows=rng.randint(2, 6),
        racks_per_row=rng.randint(10, 28),
        rack_power_kw=rng.choice([20.0, 50.0, 60.0]),
        dclc_effectiveness=rng.uniform(0.1, 0.6),
        rdhx_effectiveness=rng.uniform(0.75, 0.98),
        num_heat_exchangers=rng.randint(0, 2),
        hx_capacity_kw=rng.uniform(30.0, 150.0),
        num_air_handlers=rng.randint(1, 4),
        cfm_per_handler=rng.uniform(60000.0, 250000.0),
        inlet_temp_c=rng.uniform(18.0, 25.0),
        cdu_flow_gpm=rng.uniform(100.0, 200.0),
        num_cdus=rng.randint(1, 6),
        delta_p_kpa=rng.uniform(100.0, 350.0),
        pump_eta=rng.uniform(0.6, 0.85),
        cop=rng.uniform(3.0, 6.0),
        wall_u=rng.uniform(0.10, 0.45),
        floor_u=rng.uniform(0.20, 0.90),
    )


def simulate_day(c: Candidate, dt_minutes: int = 15) -> Dict[str, float]:
    total_racks = c.num_rows * c.racks_per_row
    q_total_kw = total_racks * c.rack_power_kw
    q_total_w = q_total_kw * 1000.0

    room_volume = c.room_length * c.room_width * c.room_height
    wall_area = 2.0 * c.room_length * c.room_height
    floor_area = c.room_length * c.room_width
    ua_walls = c.wall_u * wall_area
    ua_floor = c.floor_u * floor_area
    t_ground = 17.0

    c_air = RHO * room_volume * CP
    c_equipment = total_racks * 500.0 * 500.0
    c_slab = floor_area * 0.05 * 2300.0 * 880.0
    c_eff = c_air + c_equipment + c_slab

    frac_to_air = (1.0 - c.dclc_effectiveness) * (1.0 - c.rdhx_effectiveness)
    q_to_air_w = q_total_w * frac_to_air
    q_hx_cap_w = c.num_heat_exchangers * c.hx_capacity_kw * 1000.0
    q_hx_removed_w = min(q_to_air_w, q_hx_cap_w)
    q_remaining_w = max(q_to_air_w - q_hx_cap_w, 0.0)

    total_cfm = c.num_air_handlers * c.cfm_per_handler
    m_dot_air = (total_cfm / 2119.0) * RHO if c.num_air_handlers > 0 else 0.0
    m_cp = max(m_dot_air * CP, 1.0)
    denom = m_cp + ua_walls + ua_floor
    tau = c_eff / max(denom, 1.0)

    m_dot_liquid_kgs = (c.cdu_flow_gpm * c.num_cdus) / 15.85
    q_vol_liquid_m3s = m_dot_liquid_kgs / 1000.0
    p_pump_kw = (c.delta_p_kpa * 1000.0 * q_vol_liquid_m3s) / max(c.pump_eta, 0.01) / 1000.0

    hours = np.arange(0.0, 24.0, dt_minutes / 60.0)
    dt_h = dt_minutes / 60.0
    dt_s = dt_h * 3600.0

    t_room = c.inlet_temp_c
    t_max = t_room
    energy_kwh = 0.0
    cost_usd = 0.0
    pue_samples: List[float] = []

    for hour in hours:
        t_outdoor = 26.5 + 5.5 * math.sin(2.0 * math.pi * (hour - 9.0) / 24.0)
        t_ss = (
            c.inlet_temp_c * m_cp + q_remaining_w + ua_walls * t_outdoor + ua_floor * t_ground
        ) / max(denom, 1.0)
        decay = math.exp(-dt_s / max(tau, 1.0))
        t_room = t_ss + (t_room - t_ss) * decay
        t_max = max(t_max, t_room)

        q_dclc_w = q_total_w * c.dclc_effectiveness
        q_after_dclc_w = q_total_w - q_dclc_w
        q_rdhx_w = q_after_dclc_w * c.rdhx_effectiveness
        q_liquid_cooling_w = q_dclc_w + q_rdhx_w + q_hx_removed_w
        q_rejected_kw = max((q_liquid_cooling_w - q_hx_removed_w) / 1000.0, 0.0)
        p_mech_kw = q_rejected_kw / max(c.cop, 0.1)
        fan_power_kw = total_cfm * 0.55 / 1000.0
        p_cooling_total_kw = p_pump_kw + p_mech_kw + fan_power_kw
        total_facility_power_kw = q_total_kw + p_cooling_total_kw

        pue_samples.append(total_facility_power_kw / q_total_kw if q_total_kw > 0 else 1.0)
        energy_kwh += total_facility_power_kw * dt_h
        rate = TOU_ON_PEAK_RATE if is_on_peak(hour) else TOU_OFF_PEAK_RATE
        cost_usd += total_facility_power_kw * dt_h * rate

    it_energy_kwh = q_total_kw * 24.0
    energy_per_it_kwh = energy_kwh / max(it_energy_kwh, 1.0)
    cost_per_it_kwh = cost_usd / max(it_energy_kwh, 1.0)
    feasible = (q_total_kw <= CODA_TOTAL_CAPACITY_KW) and (t_max <= 40.0)
    return {
        "total_racks": float(total_racks),
        "it_load_kw": q_total_kw,
        "it_energy_kwh": it_energy_kwh,
        "daily_energy_kwh": energy_kwh,
        "daily_cost_usd": cost_usd,
        "energy_per_it_kwh": energy_per_it_kwh,
        "cost_per_it_kwh": cost_per_it_kwh,
        "avg_pue": float(np.mean(pue_samples)),
        "max_room_temp_c": t_max,
        "feasible": 1.0 if feasible else 0.0,
    }


def write_csv(path: str, rows: List[Dict[str, float]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(path, "w", encoding="utf-8") as f:
        f.write(",".join(keys) + "\n")
        for row in rows:
            f.write(",".join(str(row[k]) for k in keys) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize data center design parameters.")
    parser.add_argument("--samples", type=int, default=4000, help="Number of random candidates.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--dt-minutes", type=int, default=15, help="Simulation timestep in minutes.")
    parser.add_argument(
        "--target-it-kw",
        type=float,
        default=4000.0,
        help="Target IT design load in kW for apples-to-apples optimization.",
    )
    parser.add_argument(
        "--it-tolerance",
        type=float,
        default=0.20,
        help="Allowed +/- fraction around target IT load.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="reports",
        help="Output directory for report and csv files.",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    os.makedirs(args.out_dir, exist_ok=True)

    rows: List[Dict[str, float]] = []
    for _ in range(args.samples):
        c = sample_candidate(rng)
        result = simulate_day(c, dt_minutes=args.dt_minutes)
        row: Dict[str, float] = asdict(c)
        row.update(result)
        rows.append(row)

    low_it = args.target_it_kw * (1.0 - args.it_tolerance)
    high_it = args.target_it_kw * (1.0 + args.it_tolerance)
    feasible_rows = [
        r for r in rows if r["feasible"] > 0.5 and low_it <= r["it_load_kw"] <= high_it
    ]
    if not feasible_rows:
        raise RuntimeError("No feasible candidates found. Increase samples or relax constraints.")

    e_min = min(r["energy_per_it_kwh"] for r in feasible_rows)
    e_max = max(r["energy_per_it_kwh"] for r in feasible_rows)
    c_min = min(r["cost_per_it_kwh"] for r in feasible_rows)
    c_max = max(r["cost_per_it_kwh"] for r in feasible_rows)

    def norm(v: float, lo: float, hi: float) -> float:
        return (v - lo) / (hi - lo) if hi > lo else 0.0

    for r in feasible_rows:
        r["objective_score"] = 0.5 * norm(r["energy_per_it_kwh"], e_min, e_max) + 0.5 * norm(
            r["cost_per_it_kwh"], c_min, c_max
        )

    best_energy = min(feasible_rows, key=lambda r: r["energy_per_it_kwh"])
    best_cost = min(feasible_rows, key=lambda r: r["cost_per_it_kwh"])
    best_overall = min(feasible_rows, key=lambda r: r["objective_score"])
    top10 = sorted(feasible_rows, key=lambda r: r["objective_score"])[:10]

    csv_path = os.path.join(args.out_dir, "optimization_results.csv")
    top_csv_path = os.path.join(args.out_dir, "optimization_top10.csv")
    json_path = os.path.join(args.out_dir, "optimization_summary.json")
    report_path = os.path.join(args.out_dir, "optimization_report.md")

    write_csv(csv_path, feasible_rows)
    write_csv(top_csv_path, top10)

    summary = {
        "samples_total": args.samples,
        "samples_feasible": len(feasible_rows),
        "best_energy": best_energy,
        "best_cost": best_cost,
        "best_overall": best_overall,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    def fmt_block(label: str, r: Dict[str, float]) -> str:
        keys_of_interest = [
            "it_load_kw",
            "it_energy_kwh",
            "daily_energy_kwh",
            "daily_cost_usd",
            "energy_per_it_kwh",
            "cost_per_it_kwh",
            "avg_pue",
            "max_room_temp_c",
            "room_length",
            "room_width",
            "room_height",
            "num_rows",
            "racks_per_row",
            "rack_power_kw",
            "wall_u",
            "floor_u",
            "dclc_effectiveness",
            "rdhx_effectiveness",
            "num_air_handlers",
            "cfm_per_handler",
            "num_heat_exchangers",
            "hx_capacity_kw",
            "num_cdus",
            "cdu_flow_gpm",
            "delta_p_kpa",
            "pump_eta",
            "cop",
            "objective_score",
        ]
        lines = [f"### {label}"]
        for k in keys_of_interest:
            if k in r:
                lines.append(f"- `{k}`: {r[k]}")
        return "\n".join(lines)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Data Center Design Optimization Report\n\n")
        f.write(f"- Samples evaluated: `{args.samples}`\n")
        f.write(f"- Feasible samples: `{len(feasible_rows)}`\n")
        f.write(f"- IT load target: `{args.target_it_kw}` kW\n")
        f.write(f"- IT load window: `{low_it}` to `{high_it}` kW\n")
        f.write(f"- Time step: `{args.dt_minutes}` minutes\n\n")
        f.write(
            "Feasible means IT load <= 7.1 MW and max room temperature <= 40 C for the 24-hour run.\n\n"
        )
        f.write(fmt_block("Best by Energy", best_energy))
        f.write("\n\n")
        f.write(fmt_block("Best by Cost", best_cost))
        f.write("\n\n")
        f.write(fmt_block("Best Overall (50/50 Energy + Cost)", best_overall))
        f.write("\n")

    print(f"Wrote: {report_path}")
    print(f"Wrote: {csv_path}")
    print(f"Wrote: {top_csv_path}")
    print(f"Wrote: {json_path}")


if __name__ == "__main__":
    main()
