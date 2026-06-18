import sys
import os
from pathlib import Path

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_APP_DIR)
sys.path.insert(0, _PROJECT_ROOT)

from components.scheduler_inputs import (
    clock_time_input,
    duration_time_input,
    gpu_power_input,
    rack_count_input,
    rack_count_valid,
    duration_to_hours
)

import streamlit as st

st.set_page_config(
    page_title="ATL01 Data Center Model",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
import streamlit.components.v1 as components

_timeline_component = components.declare_component(
    "job_timeline",
    path=os.path.join(_PROJECT_ROOT, "components", "timeline"),
)

try:
    from model.config import ENERGYPLUS_PATH
    import os
    eplus_available = ENERGYPLUS_PATH and os.path.exists(ENERGYPLUS_PATH)
except ImportError:
    ENERGYPLUS_PATH = None
    eplus_available = False


def slider_with_input(label, min_val, max_val, default_val, step=0.1, help_text=None, key_prefix="", container=st):
    key_val = f"param_{key_prefix}_val"
    key_slider = f"param_{key_prefix}_slider"
    key_num = f"param_{key_prefix}_num"
    
    if key_val not in st.session_state:
        st.session_state[key_val] = default_val
        
    if help_text:
        container.markdown(f"**{label}**", help=help_text)
    else:
        container.markdown(f"**{label}**")
        
    col_l, col_r = container.columns([3, 2])
    
    def update_from_slider():
        st.session_state[key_val] = st.session_state[key_slider]
        
    def update_from_num():
        val = st.session_state[key_num]
        if val is not None:
            st.session_state[key_val] = min(max(val, min_val), max_val)
        
    with col_l:
        container.slider(
            label, min_val, max_val,
            value=st.session_state[key_val],
            step=step,
            key=key_slider,
            label_visibility="collapsed",
            on_change=update_from_slider
        )
    with col_r:
        val_type = type(default_val)
        container.number_input(
            label, val_type(min_val), val_type(max_val),
            value=val_type(st.session_state[key_val]),
            step=val_type(step),
            key=key_num,
            label_visibility="collapsed",
            on_change=update_from_num
        )
        
    return st.session_state[key_val]


# Physical constants
RHO = 1.184  # Air density kg/m³
CP = 1007.0  # Specific heat capacity J/(kg·K)
K_AIR = 0.026  # Thermal conductivity W/(m·K)
CP_WATER = 4180.0  # J/(kg·K) specific heat of water
T_SUPPLY_C = 22.8  # °C this is from ColdLogik ATL1 spec
T_RECOVERY_TARGET_C = 40.0  # °C, waste heat recovery design target (known)

from core.constants import (
    TOU_ON_PEAK_RATE, TOU_OFF_PEAK_RATE,
    TOU_ON_PEAK_START, TOU_ON_PEAK_END,
    IDLE_RACK_KW, POWER_LEVELS, is_on_peak,
)

st.title("🌡️ ATL01 PACE Room - Thermal Model")
st.markdown("**Interactive thermal analysis for high-density data center cooling**")

status_cols = st.columns([3, 3, 6])
with status_cols[0]:
    if eplus_available:
        st.success("EnergyPlus 25.1: Connected")
    else:
        st.warning("EnergyPlus 25.1: Not Connected", help="EnergyPlus executable not found in system paths. Check sidebar configuration.")
with status_cols[1]:
    if st.session_state.get('sim_data') is not None:
        engine_label = "Advanced (EnergyPlus)" if st.session_state.get('eplus_raw') is not None else "Simplified (Python)"
        st.info(f"Active Simulation: **{engine_label}**")
    else:
        st.info("Active Simulation: **No simulation run yet**")
with status_cols[2]:
    if st.session_state.get('last_run_status') is not None:
        engine = st.session_state.last_run_engine
        status = st.session_state.last_run_status
        timestamp = st.session_state.last_run_timestamp
        if status == "success":
            st.success(f"⚡ Last Run: **{engine}** at {timestamp} (Success)")
        else:
            st.error(f"Last Run: **{engine}** at {timestamp} (Failed)")
    else:
        st.info("⚡ Last Run: **No simulation run yet**")
with st.expander("ℹ️ How to use this model", expanded=False):
    st.markdown("""
    This model simulates heat flow through a data center using real physics equations.

    **Quick Start:**
    1. Adjust sliders in the sidebar to change room size, equipment, and cooling
    2. Watch how room temperature and energy efficiency respond in real-time
    3. Green metrics = good, Red metrics = need attention

    **Waste Heat Recovery:** Heat exchangers capture heat for reuse (e.g., building heating)
    """)

st.sidebar.header("⚙️ Configuration")

if eplus_available:
    st.sidebar.markdown("**Simulation Engine**", help="Select between the fast Python physics solver or the detailed EnergyPlus model.")
    btn_cols = st.sidebar.columns(2)
    
    if 'sim_engine' not in st.session_state:
        st.session_state.sim_engine = "Simplified (Python Physics)"
        
    with btn_cols[0]:
        is_simplified = st.session_state.sim_engine == "Simplified (Python Physics)"
        if st.button(
            "Simplified", 
            type="primary" if is_simplified else "secondary", 
            use_container_width=True,
            help="Fast Python physics solver."
        ):
            st.session_state.sim_engine = "Simplified (Python Physics)"
            st.toast("Switched to Simplified (Python Physics) engine.")
            st.rerun()
            
    with btn_cols[1]:
        is_advanced = st.session_state.sim_engine == "Advanced (EnergyPlus)"
        if st.button(
            "Advanced", 
            type="primary" if is_advanced else "secondary", 
            use_container_width=True,
            help="Detailed EnergyPlus model."
        ):
            st.session_state.sim_engine = "Advanced (EnergyPlus)"
            st.toast("Switched to Advanced (EnergyPlus) engine.")
            st.rerun()
            
    sim_engine = st.session_state.sim_engine
else:
    st.sidebar.warning("⚠️ EnergyPlus installation not found. Using Simplified solver only.")
    sim_engine = "Simplified (Python Physics)"

st.sidebar.subheader("📐 Room & Racks")
room_length = slider_with_input("Room Length (m)", 10.0, 40.0, 27.1, 0.1,
                                help_text="Length affects total room volume and power density",
                                key_prefix="room_length", container=st.sidebar)
room_width = slider_with_input("Room Width (m)", 5.0, 30.0, 23.6, 0.1,
                               help_text="Width affects total room volume and power density",
                               key_prefix="room_width", container=st.sidebar)
room_height = slider_with_input("Room Height (m)", 2.5, 8.0, 6.4, 0.1,
                                help_text="Height affects air circulation and stratification",
                                key_prefix="room_height", container=st.sidebar)
num_rows = slider_with_input("Number of Rows", 1, 6, 3, 1,
                             help_text="Rows of server racks in the room",
                             key_prefix="num_rows", container=st.sidebar)
racks_per_row = slider_with_input("Racks per Row", 5, 30, 20, 1,
                                  help_text="Number of server racks in each row",
                                  key_prefix="racks_per_row", container=st.sidebar)

if 'scheduled_jobs' not in st.session_state:
    st.session_state.scheduled_jobs = []
if 'sim_data' not in st.session_state:
    st.session_state.sim_data = None
if 'sim_frame' not in st.session_state:
    st.session_state.sim_frame = 0
if 'sim_fingerprint' not in st.session_state:
    st.session_state.sim_fingerprint = None
if 'sim_stale' not in st.session_state:
    st.session_state.sim_stale = False
if 'sim_playing' not in st.session_state:
    st.session_state.sim_playing = False
if 'scroll_to_viz' not in st.session_state:
    st.session_state.scroll_to_viz = False
if 'tou_costs' not in st.session_state:
    st.session_state.tou_costs = None
if 'auto_run_sim' not in st.session_state:
    st.session_state.auto_run_sim = False
if 'timeline_version' not in st.session_state:
    st.session_state.timeline_version = 0
if 'show_adv_plots' not in st.session_state:
    st.session_state.show_adv_plots = False
if 'comp_data' not in st.session_state:
    st.session_state.comp_data = None
if 'fig_comp' not in st.session_state:
    st.session_state.fig_comp = None
if 'fig_adv' not in st.session_state:
    st.session_state.fig_adv = None

st.sidebar.subheader("❄️ Cooling System")
dclc_effectiveness = slider_with_input("DCLC Effectiveness", 0.0, 0.60, 0.35, 0.05,
                                       help_text="% of heat captured by cold plates at CPUs/GPUs",
                                       key_prefix="dclc_eff", container=st.sidebar)
rdhx_effectiveness = slider_with_input("RDHX Effectiveness", 0.0, 0.98, 0.92, 0.02,
                                       help_text="% of rack exhaust heat captured by rear door exchangers",
                                       key_prefix="rdhx_eff", container=st.sidebar)
num_heat_exchangers = slider_with_input("Waste Heat Exchangers", 0, 2, 0, 1,
                                        help_text="Heat exchangers that capture waste heat for reuse",
                                        key_prefix="num_hx", container=st.sidebar)
hx_capacity_kw = slider_with_input("HX Capacity (kW each)", 30.0, 150.0, 60.0, 10.0,
                                   help_text="Maximum heat each exchanger can capture",
                                   key_prefix="hx_cap", container=st.sidebar)

with st.sidebar.expander("CDU & Pump Details") as cdu_exp:
    cdu_flow_gpm = slider_with_input("Flow Rate per CDU (GPM)", 100.0, 200.0, 150.0, 5.0,
                                     help_text="Water flow rate per CDU",
                                     key_prefix="cdu_flow", container=cdu_exp)
    num_cdus = slider_with_input("Number of CDUs", 1, 6, 3, 1,
                                 help_text="Cooling Distribution Units",
                                 key_prefix="num_cdus", container=cdu_exp)
    delta_p_kpa = slider_with_input("Loop Pressure Drop (kPa)", 100.0, 350.0, 200.0, 10.0,
                                    help_text="Pressure the pump must overcome",
                                    key_prefix="delta_p", container=cdu_exp)
    pump_eta = slider_with_input("Pump Efficiency", 0.60, 0.85, 0.75, 0.05,
                                 help_text="Pump mechanical efficiency",
                                 key_prefix="pump_eta", container=cdu_exp)
    cop = slider_with_input("Chiller COP", 3.0, 6.0, 4.0, 0.5,
                            help_text="Chiller Coefficient of Performance",
                            key_prefix="cop", container=cdu_exp)

st.sidebar.subheader("💨 Air Handling")
num_air_handlers = slider_with_input("Air Handlers", 0, 4, 2, 1,
                                     help_text="Number of air handling units",
                                     key_prefix="num_ahu", container=st.sidebar)
cfm_per_handler = slider_with_input("Airflow per Handler (CFM)", 20000.0, 250000.0, 155000.0, 5000.0,
                                    help_text="Cubic Feet per Minute per handler",
                                    key_prefix="cfm_ahu", container=st.sidebar)
inlet_temp_c = slider_with_input("Inlet Temperature (°C)", 18.0, 28.0, 23.3, 0.5,
                                 help_text="Temperature of cooling air entering the room",
                                 key_prefix="inlet_temp", container=st.sidebar)
waste_threshold_c = slider_with_input("Hot Spot Threshold (°C)", 25.0, 35.0, 30.0, 1.0,
                                      help_text="Temperature above which areas are flagged as too hot",
                                      key_prefix="waste_temp", container=st.sidebar)

#24-hour outdoor temperature profile for typical Atlanta July day
#T_outdoor(t) = 26.5 + 5.5 × sin(2π(t - 9)/24)
#Low ~21°C at 5AM, high ~32°C at 3PM
outdoor_temp_profile = {
    hour: 26.5 + 5.5 * np.sin(2 * np.pi * (hour - 9) / 24)
    for hour in np.arange(0, 24, 0.5)
}
time_of_day = 15.0

_current_fingerprint = (
    room_length, room_width, room_height,
    num_rows, racks_per_row,
    dclc_effectiveness, rdhx_effectiveness,
    num_heat_exchangers, hx_capacity_kw,
    num_air_handlers, cfm_per_handler,
    inlet_temp_c,
    tuple((j['start_time'], j['end_time'], j['power_kw'], j['num_racks'])
          for j in sorted(st.session_state.scheduled_jobs, key=lambda j: j['id'])),
)
if st.session_state.sim_fingerprint is not None and _current_fingerprint != st.session_state.sim_fingerprint:
    st.session_state.sim_data = None
    st.session_state.sim_frame = 0
    st.session_state.sim_fingerprint = None
    st.session_state.sim_stale = True
    st.session_state.sim_playing = False
    st.session_state.tou_costs = None
    st.session_state.show_adv_plots = False
    st.session_state.comp_data = None
    st.session_state.fig_comp = None
    st.session_state.fig_adv = None



# ===== JOB SCHEDULING SECTION =====
st.header("📅 Job Scheduler")
st.markdown("Schedule GPU jobs throughout the day to see thermal impact over time")

# Job scheduler UI
col1, col2 = st.columns([2, 1])

# Estimated calculations based on tour info and other similar data centers:
# CODA Rack Density Model:
CHASSIS_POWER_KW = 9.0  # 8–10 kW average range
CHASSIS_PER_RACK = 7  # 42U / 6U
FULL_GPU_RACK_KW = CHASSIS_POWER_KW * CHASSIS_PER_RACK  # ~63 kW

CPU_DOMINANT_RACK_KW = 15.0  # mixed CPU racks (your estimate)
MIXED_GPU_RACK_KW = 40.0  # conservative GPU racks

# rack_power_kw = FULL_GPU_RACK_KW
total_racks = num_rows * racks_per_row
rack_power_kw = FULL_GPU_RACK_KW

def calculate_tou_cost(sim_data):
    """
    Iterates every simulation timestep.
    Job load = total IT load minus idle baseline (total_racks × IDLE_RACK_KW).
    No PUE — incremental job load only.
    """
    if sim_data is None:
        return None

    times_h       = sim_data['times_h']
    Q_total_kw    = sim_data['Q_total_kw']
    total_racks   = int(sim_data.get('total_racks', 0))
    idle_kw_total = total_racks * IDLE_RACK_KW

    n_steps  = len(times_h)
    dt_hours = (times_h[1] - times_h[0]) if n_steps > 1 else (1.0 / 60.0)

    job_on_peak_kwh  = 0.0;  job_off_peak_kwh  = 0.0
    job_on_peak_cost = 0.0;  job_off_peak_cost = 0.0

    for step in range(n_steps):
        t_h     = float(times_h[step]) % 24
        it_kw   = float(Q_total_kw[step])
        job_kw  = max(0.0, it_kw - idle_kw_total)
        on_peak = is_on_peak(t_h)
        rate    = TOU_ON_PEAK_RATE if on_peak else TOU_OFF_PEAK_RATE
        energy  = job_kw * dt_hours
        cost    = energy * rate

        if on_peak:
            job_on_peak_kwh  += energy
            job_on_peak_cost += cost
        else:
            job_off_peak_kwh += energy
            job_off_peak_cost += cost

    job_total_kwh  = job_on_peak_kwh  + job_off_peak_kwh
    job_total_cost = job_on_peak_cost + job_off_peak_cost
    off_peak_pct   = (job_off_peak_kwh / job_total_kwh * 100) if job_total_kwh > 0 else 0.0

    return {
        'job_total_kwh':      job_total_kwh,
        'job_on_peak_kwh':    job_on_peak_kwh,
        'job_off_peak_kwh':   job_off_peak_kwh,
        'job_total_cost':     job_total_cost,
        'job_on_peak_cost':   job_on_peak_cost,
        'job_off_peak_cost':  job_off_peak_cost,
        'off_peak_pct':       off_peak_pct,
    }



def calculate_thermal_system(room_length, room_width, room_height,
                             num_rows, racks_per_row, rack_power_kw,
                             rdhx_effectiveness, dclc_effectiveness, num_air_handlers,
                             num_heat_exchangers, hx_capacity_kw,
                             inlet_temp_c, waste_threshold_c, cfm_per_handler,
                             time_of_day, cdu_flow_gpm=150.0, num_cdus=3,
                             delta_p_kpa=200.0, pump_eta=0.75, cop=4.0,
                             rack_powers_kw=None, T_room_transient=None):
    """Calculate thermal system with physically accurate equations

    Heat Flow Stages:
    1. DCLC (Direct Contact Liquid Cooling) - captures heat at CPU/GPU via cold plates
    2. RDHX (Rear Door Heat Exchanger) - captures heat from exhaust air
    3. Heat Exchangers - remove additional heat from room air
    4. Air Handlers - circulate air and remove remaining heat

    Building Envelope:
    - Exterior wall heat gain/loss: Q_walls = U x A x (T_outdoor - T_room)
    - Floor heat loss to ground: Q_floor = U x A x (T_room - T_ground)
    - Outdoor temperature follows sinusoidal 24h profile for Atlanta July

    Physics:
    - Q = m_dot x Cp x ΔT (heat transfer equation)
    - Room temperature depends on heat load, airflow rate, envelope, and room volume
    - All configurable parameters affect the final outcome
    """

    # === RACK LAYOUT ===
    RACK_WIDTH = 0.6
    RACK_DEPTH = 1.4
    CLEARANCE = 1.5
    AISLE_WIDTH = 1.0

    RACKS = []
    available_length = room_length - 2 * CLEARANCE
    Y_CLEARANCE = 4.0

    for row_idx in range(num_rows):
        y_pos = Y_CLEARANCE + RACK_DEPTH / 2 + row_idx * (RACK_DEPTH + AISLE_WIDTH)
        total_row_width = racks_per_row * RACK_WIDTH
        start_x = CLEARANCE + (available_length - total_row_width) / 2

        for rack_idx in range(racks_per_row):
            RACKS.append({
                'x': start_x + rack_idx * RACK_WIDTH + RACK_WIDTH / 2,
                'y': y_pos,
                'power_kw': rack_power_kw,
                'width': RACK_WIDTH,
                'depth': RACK_DEPTH
            })

    total_racks = len(RACKS)

    # === HEAT GENERATION ===
    CODA_TOTAL_CAPACITY_KW = 7100  # 7.1 MW
    Q_TOTAL_W = total_racks * rack_power_kw * 1000  # Total IT load in Watts

    if rack_powers_kw is not None:
        p = np.asarray(rack_powers_kw, dtype=float).ravel()
        for i, rack in enumerate(RACKS):
            rack['power_kw'] = float(p[i]) if i < len(p) else rack['power_kw']
        Q_TOTAL_W = sum(rack['power_kw'] for rack in RACKS) * 1000.0

    if Q_TOTAL_W / 1000 > CODA_TOTAL_CAPACITY_KW:
        st.warning("⚠️ IT load exceeds CODA 7.1 MW design capacity!")

    # === HEAT DISTRIBUTION (Multi-Stage Cooling) ===
    # Stage 1: DCLC captures heat directly at CPU/GPU via cold plates
    Q_DCLC_W = Q_TOTAL_W * dclc_effectiveness
    Q_AFTER_DCLC_W = Q_TOTAL_W - Q_DCLC_W

    # Stage 2: RDHX captures heat from rack exhaust air
    Q_RDHX_W = Q_AFTER_DCLC_W * rdhx_effectiveness
    Q_TO_AIR_BEFORE_HX_W = Q_AFTER_DCLC_W * (1 - rdhx_effectiveness)

    # Stage 3: Heat exchangers remove additional heat from room air
    Q_HX_CAPACITY_W = num_heat_exchangers * hx_capacity_kw * 1000
    Q_HX_REMOVED_W = min(Q_TO_AIR_BEFORE_HX_W, Q_HX_CAPACITY_W)
    Q_TO_ROOM_AIR_W = Q_TO_AIR_BEFORE_HX_W - Q_HX_REMOVED_W

    # Total liquid cooling (for waste heat recovery)
    Q_LIQUID_COOLING_W = Q_DCLC_W + Q_RDHX_W + Q_HX_REMOVED_W

    # === ROOM VOLUME AND AIRFLOW CALCULATION ===
    room_volume = room_length * room_width * room_height  # m³

    # Power density affects required ventilation
    power_density_w_m3 = Q_TOTAL_W / room_volume if room_volume > 0 else 0

    if num_air_handlers > 0:
        # User-specified airflow from air handlers
        total_cfm = num_air_handlers * cfm_per_handler
        volumetric_flow_m3s = total_cfm / 2119.0  # CFM to m³/s conversion
        mass_flow_kg_s = volumetric_flow_m3s * RHO
        ach = (volumetric_flow_m3s * 3600.0) / room_volume if room_volume > 0 else 0
    else:
        # Natural convection - scales with room volume and power density
        # Higher power density or larger rooms need more air changes
        ach = max(5, min(20, 5 + power_density_w_m3 / 1000))
        volumetric_flow_m3s = (room_volume * ach) / 3600
        mass_flow_kg_s = volumetric_flow_m3s * RHO
        total_cfm = volumetric_flow_m3s * 2119

    # === BUILDING ENVELOPE ===
    # Outdoor temperature: sinusoidal 24h profile for typical Atlanta July day
    T_outdoor_c = 26.5 + 5.5 * np.sin(2 * np.pi * (time_of_day - 9) / 24)

    # Envelope U-values and areas
    UA_WALLS = 0.19 * (2.0 * room_length * room_height)  #W/K — two exterior walls
    UA_FLOOR = 0.5 * (room_length * room_width)  #W/K — floor slab
    T_GROUND = 17.0  # °C — constant ground temperature

    # Effective thermal capacitance: air + equipment + shallow concrete slab
    C_air_J = RHO * room_length * room_width * room_height * CP
    C_equip_J = total_racks * 500.0 * 500.0
    C_slab_J = (room_length * room_width) * 0.05 * 2300.0 * 880.0
    THERMAL_CAPACITANCE_MJK = (C_air_J + C_equip_J + C_slab_J) / 1e6

    # === PHYSICS-BASED TEMPERATURE CALCULATION ===
    Q_REMAINING_IT_W = Q_TO_ROOM_AIR_W

    m_dot_Cp = mass_flow_kg_s * CP if mass_flow_kg_s > 0 else 1.0

    # Steady-state equilibrium temperature (used as fallback)
    T_room_ss = (inlet_temp_c * m_dot_Cp + Q_REMAINING_IT_W
                 + UA_WALLS * T_outdoor_c + UA_FLOOR * T_GROUND) / (m_dot_Cp + UA_WALLS + UA_FLOOR)

    # When running the time-domain simulation, use the ODE-integrated
    # temperature which accounts for thermal mass — the room heats up
    # gradually under load and cools down gradually after jobs end.
    T_room_c = T_room_transient if T_room_transient is not None else T_room_ss

    # Now compute actual envelope heat flows at the solved T_room
    Q_WALLS_W = UA_WALLS * (T_outdoor_c - T_room_c)  # positive = heat entering room
    Q_FLOOR_W = UA_FLOOR * (T_room_c - T_GROUND)  # positive = heat leaving room

    # Effective delta-T seen by air handlers (includes envelope effects)
    delta_t_airflow = T_room_c - inlet_temp_c

    # Rack exhaust temperature (before RDHX cooling)
    # Heat concentrated in exhaust stream from racks
    if total_racks > 0:
        # Estimate rack airflow (typically 200-400 CFM per kW)
        # high-density GPU rack airflow updated for params (300–400 CFM per kW is typical)
        rack_cfm_per_kw = 325  # CFM/kW (typical for high-density racks)
        total_rack_cfm = Q_TOTAL_W / 1000 * rack_cfm_per_kw
        rack_volumetric_flow_m3s = total_rack_cfm / 2119.0
        rack_mass_flow_kg_s = rack_volumetric_flow_m3s * RHO

        # Temperature rise across racks (before any cooling)
        if rack_mass_flow_kg_s > 0:
            delta_t_rack = Q_AFTER_DCLC_W / (rack_mass_flow_kg_s * CP)
        else:
            delta_t_rack = 0.0

        T_rack_exhaust_c = inlet_temp_c + delta_t_rack

        # After RDHX cooling
        T_rack_exhaust_after_rdhx_c = inlet_temp_c + delta_t_rack * (1 - rdhx_effectiveness)
    else:
        T_rack_exhaust_c = inlet_temp_c
        T_rack_exhaust_after_rdhx_c = inlet_temp_c
        rack_mass_flow_kg_s = 0

    # === PUE (Power Usage Effectiveness) Calculation ===
    # PUE = Total Facility Power / IT Equipment Power
    # Cooling overhead depends on cooling efficiency
    # Liquid cooling is more efficient, reducing mechanical cooling needs
    liquid_cooling_fraction = Q_LIQUID_COOLING_W / Q_TOTAL_W if Q_TOTAL_W > 0 else 0

    # Base cooling overhead (air-cooled system ≈ 40-60% overhead, PUE 1.4-1.6)
    # High-efficiency liquid cooling ≈ 10-20% overhead (PUE 1.1-1.2)
    base_overhead = 0.50  # 50% for pure air cooling
    liquid_cooling_benefit = 0.35 * liquid_cooling_fraction  # Up to 35% reduction
    cooling_overhead_fraction = base_overhead - liquid_cooling_benefit

    # Additional overhead from air handler power
    if num_air_handlers > 0:
        # Fan power ≈ 0.5-1.0 W per CFM for large air handlers
        fan_power_w = total_cfm * 0.55  # 0.75 W/CFM (updated to 0.55 for params)
        fan_overhead = fan_power_w / Q_TOTAL_W if Q_TOTAL_W > 0 else 0
    else:
        fan_overhead = 0

    total_overhead_fraction = cooling_overhead_fraction + fan_overhead
    total_facility_power_w = Q_TOTAL_W * (1 + total_overhead_fraction)
    pue = total_facility_power_w / Q_TOTAL_W if Q_TOTAL_W > 0 else 1.0

    # Cooling Power Calculations
    # T_SUPPLY_C and T_RECOVERY_TARGET_C are global constants defined at top of file

    # Total loop flow rate from CDU count × per-CDU flow
    m_dot_liquid_kgs = (cdu_flow_gpm * num_cdus) / 15.85  # GPM → kg/s
    m_dot_liquid_gpm_total = cdu_flow_gpm * num_cdus

    # T_return actually comes from Q = m_dot × cp × ΔT
    # T_return = T_supply + Q_liquid / (m_dot × cp)
    t_return_c = (T_SUPPLY_C + (Q_DCLC_W + Q_RDHX_W) / (m_dot_liquid_kgs * CP_WATER)
                  if m_dot_liquid_kgs > 0 else T_SUPPLY_C)
    delta_t_water = t_return_c - T_SUPPLY_C

    # Flag whether return is hot enough for waste heat recovery
    heat_recovery_viable = t_return_c >= T_RECOVERY_TARGET_C

    # P_pump = (ΔP · Q_vol) / η
    q_vol_liquid_m3s = m_dot_liquid_kgs / 1000.0
    p_pump_kw = (delta_p_kpa * 1000.0 * q_vol_liquid_m3s) / pump_eta / 1000.0

    # P_mech = Q_rejected / COP
    # Q_rejected = liquid heat NOT recovered by waste-HX — still needs chiller
    q_rejected_kw = (Q_LIQUID_COOLING_W - Q_HX_REMOVED_W) / 1000.0
    p_mech_kw = q_rejected_kw / cop if cop > 0 else 0.0

    # Fan power
    _fan_power_kw = (total_cfm * 0.55 / 1000.0) if num_air_handlers > 0 else 0.0

    # Total cooling electrical demand
    p_cooling_total_kw = p_pump_kw + p_mech_kw + _fan_power_kw

    # === EQUIPMENT POSITIONS ===
    AIR_HANDLERS = []
    if num_air_handlers >= 1:
        AIR_HANDLERS.append({'x': 1.0, 'y': room_width / 2, 'width': 1.7, 'height': 4.5, 'side': 'left'})
    if num_air_handlers >= 2:
        AIR_HANDLERS.append({'x': room_length - 1.0, 'y': room_width / 2, 'width': 1.7, 'height': 4.5, 'side': 'right'})
    if num_air_handlers >= 3:
        AIR_HANDLERS.append({'x': room_length / 2, 'y': 1.2, 'width': 4.5, 'height': 2.0, 'side': 'top'})
    if num_air_handlers >= 4:
        AIR_HANDLERS.append(
            {'x': room_length / 2, 'y': room_width - 1.2, 'width': 4.5, 'height': 2.0, 'side': 'bottom'})

    HX_POSITIONS = []
    if num_heat_exchangers >= 1:
        HX_POSITIONS.append({'x': room_length * 0.25, 'y': room_width - 1.0, 'width': 2.0, 'height': 1.2})
    if num_heat_exchangers >= 2:
        HX_POSITIONS.append({'x': room_length * 0.75, 'y': room_width - 1.0, 'width': 2.0, 'height': 1.2})

    # === TEMPERATURE FIELD VISUALIZATION ===
    # Create physics-based temperature distribution
    DX = 0.2
    NX = max(int(room_length / DX), 30)
    NY = max(int(room_width / DX), 30)

    x = np.linspace(0, room_length, NX)
    y = np.linspace(0, room_width, NY)
    X, Y = np.meshgrid(x, y)

    # Base temperature = room average temperature
    T = np.ones_like(X) * T_room_c

    # Add localized heat from racks (scales with actual physics)
    # Heat remaining after liquid cooling creates hot zones near racks
    for rack in RACKS:
        dist = np.sqrt((X - rack['x']) ** 2 + (Y - rack['y']) ** 2)
        # Heat escaping to room (not captured by DCLC or RDHX)
        heat_fraction = (1 - dclc_effectiveness) * (1 - rdhx_effectiveness)

        # Heat intensity based on rack power and distance
        # Using 1/r² decay modified by exponential for numerical stability
        # Updated to work for newer params
        heat_plume_temp = rack['power_kw'] * heat_fraction * 0.04  # °C per kW escaping
        spatial_decay = np.exp(-(dist / 0.8) ** 2)  # Gaussian plume
        T += heat_plume_temp * spatial_decay

    # Add cooling effect from air handlers (proportional to capacity and airflow)
    if num_air_handlers > 0 and mass_flow_kg_s > 0:
        # Cooling intensity based on actual air handler capacity
        cooling_intensity_per_handler = (delta_t_airflow * 0.5) / num_air_handlers
        for handler in AIR_HANDLERS:
            dist = np.sqrt((X - handler['x']) ** 2 + (Y - handler['y']) ** 2)
            cooling_plume = cooling_intensity_per_handler * np.exp(-(dist / 3.0) ** 2)
            T -= cooling_plume

    # Add cooling from heat exchangers (proportional to heat removed)
    if num_heat_exchangers > 0 and Q_HX_REMOVED_W > 0:
        # Cooling based on actual heat exchanger performance
        hx_temp_reduction = (Q_HX_REMOVED_W / (mass_flow_kg_s * CP)) if mass_flow_kg_s > 0 else 0
        cooling_per_hx = hx_temp_reduction / num_heat_exchangers * 0.3
        for hx in HX_POSITIONS:
            dist = np.sqrt((X - hx['x']) ** 2 + (Y - hx['y']) ** 2)
            T -= cooling_per_hx * np.exp(-(dist / 2.5) ** 2)

    # Realistic temperature bounds
    T_min_physical = inlet_temp_c - 1.0  # Inlet air with slight mixing
    T_max_physical = max(T_room_c + 10, T_rack_exhaust_after_rdhx_c + 3)  # Hot zones near exhausts
    T = np.clip(T, T_min_physical, T_max_physical)

    # Statistics
    max_temp = np.max(T)
    min_temp = np.min(T)
    avg_temp = np.mean(T)
    hot_spots = np.sum(T > waste_threshold_c)
    hot_spot_percent = (hot_spots / T.size) * 100

    return {
        'X': X, 'Y': Y, 'T': T,
        'racks': RACKS,
        'air_handlers': AIR_HANDLERS,
        'hx_positions': HX_POSITIONS,
        'total_racks': total_racks,
        'active_racks': sum(1 for rack in RACKS if rack['power_kw'] > IDLE_RACK_KW + 1e-6),
        'Q_total_kw': Q_TOTAL_W / 1000,
        'Q_dclc_kw': Q_DCLC_W / 1000,
        'Q_after_dclc_kw': Q_AFTER_DCLC_W / 1000,
        'Q_rdhx_kw': Q_RDHX_W / 1000,
        'Q_liquid_cooling_kw': Q_LIQUID_COOLING_W / 1000,
        'Q_to_air_before_hx_kw': Q_TO_AIR_BEFORE_HX_W / 1000,
        'Q_hx_removed_kw': Q_HX_REMOVED_W / 1000,
        'Q_remaining_kw': Q_REMAINING_IT_W / 1000,
        'Q_walls_kw': Q_WALLS_W / 1000,
        'Q_floor_kw': Q_FLOOR_W / 1000,
        'T_outdoor': T_outdoor_c,
        'thermal_capacitance_MJK': THERMAL_CAPACITANCE_MJK,
        'mass_flow_kg_s': mass_flow_kg_s,
        'volumetric_flow_m3s': volumetric_flow_m3s,
        'cfm': total_cfm,
        'cfm_per_handler': (total_cfm / num_air_handlers) if num_air_handlers > 0 else 0,
        'ach': ach,
        'delta_t': delta_t_airflow,
        'T_inlet': inlet_temp_c,
        'T_room': T_room_c,
        'T_rack_exhaust': T_rack_exhaust_c,
        'T_rack_exhaust_after_rdhx': T_rack_exhaust_after_rdhx_c,
        'T_max': max_temp,
        'T_min': min_temp,
        'T_avg': avg_temp,
        'hot_spots': hot_spots,
        'hot_spot_percent': hot_spot_percent,
        'waste_threshold': waste_threshold_c,
        'room_length': room_length,
        'room_width': room_width,
        'room_height': room_height,
        'room_volume': room_volume,
        'power_density_w_m3': power_density_w_m3,
        'pue': pue,
        'total_facility_power_kw': total_facility_power_w / 1000,
        'cooling_overhead_fraction': total_overhead_fraction,
        'liquid_cooling_fraction': liquid_cooling_fraction,
        'time_of_day': time_of_day,
        't_supply_known': T_SUPPLY_C,
        't_return_c': t_return_c,  # calculated, not assumed
        't_recovery_target': T_RECOVERY_TARGET_C,
        'heat_recovery_viable': heat_recovery_viable,
        'delta_t_water': delta_t_water,
        'm_dot_liquid_kgs': m_dot_liquid_kgs,
        'm_dot_liquid_gpm': m_dot_liquid_gpm_total,
        'q_vol_liquid_lps': q_vol_liquid_m3s * 1000,
        'p_pump_kw': p_pump_kw,
        'q_rejected_kw': q_rejected_kw,
        'p_mech_kw': p_mech_kw,
        'fan_power_kw': _fan_power_kw,
        'p_cooling_total_kw': p_cooling_total_kw,
    }


def run_eplus_simulation(
    room_length, room_width, room_height,
    num_rows, racks_per_row,
    dclc_effectiveness, rdhx_effectiveness,
    num_heat_exchangers, hx_capacity_kw,
    num_air_handlers, cfm_per_handler,
    inlet_temp_c, scheduled_jobs,
    cdu_flow_gpm, num_cdus, delta_p_kpa, pump_eta, cop
):
    from model.EPlusIDF import DetailedIDFGenerator
    from model.run import run_energyplus
    from model.parse_eso import parse_eso_file
    from model.config import ENERGYPLUS_PATH
    from pathlib import Path
    
    total_racks = num_rows * racks_per_row
    
    scenario = {
        'name': 'streamlit_run',
        'room': {
            'length': room_length,
            'width': room_width,
            'height': room_height,
        },
        'racks': {
            'rows': num_rows,
            'racks_per_row': racks_per_row,
            'power_per_rack': 63000.0, # W
            'total_racks': total_racks,
            'total_power': total_racks * 63000.0, # W
        },
        'cooling': {
            'dclc_effectiveness': dclc_effectiveness,
            'rdhx_effectiveness': rdhx_effectiveness,
            'num_air_handlers': num_air_handlers,
            'cfm_per_handler': cfm_per_handler,
            'total_cfm': num_air_handlers * cfm_per_handler,
            'total_flow_gpm': cdu_flow_gpm * num_cdus,
        },
        'heat_exchangers': {
            'count': num_heat_exchangers,
            'capacity_each': hx_capacity_kw * 1000.0, # W
        },
        'target_temp': inlet_temp_c,
        'cdu_flow_gpm': cdu_flow_gpm,
        'num_cdus': num_cdus,
        'delta_p_kpa': delta_p_kpa,
        'pump_eta': pump_eta,
        'cop': cop
    }
    
    schedules = []
    for job in scheduled_jobs:
        schedules.append({
            'name': f"Job_{job['id']}",
            'start_hour': job['start_hour'],
            'duration_hours': job['duration'],
            'power_level': job['power_kw'] * 1000.0, # W
            'num_racks': job['num_racks'],
            'total_power': job['power_kw'] * job['num_racks'] * 1000.0, # W
        })
    scenario['schedules'] = schedules
    
    generator = DetailedIDFGenerator(ENERGYPLUS_PATH)
    idf_filename = 'streamlit_run_detailed.idf'
    idf_path = Path('model/scenarios') / idf_filename
    generator.generate_scenario_from_dict(scenario, idf_path)
    
    success = run_energyplus(idf_filename)
    if not success:
        return None
        
    eso_path = Path('model/outputs/streamlit_run_detailed/eplusout.eso')
    if not eso_path.exists():
        return None
        
    vars_map, data = parse_eso_file(eso_path)
    return data


def extract_eplus_time_series(data, times_h, total_racks, IDLE_RACK_KW):
    from model.parse_eso import find_var
    import numpy as np
    
    temp_key = find_var(data, "Zone Mean Air Temperature")
    if temp_key and data[temp_key]:
        ep_temp = data[temp_key]
    else:
        ep_temp = [23.3] * 96
        
    cpu_key = find_var(data, "Zone ITE CPU Electricity Rate")
    fan_key = find_var(data, "Zone ITE Fan Electricity Rate")
    ups_key = find_var(data, "Zone ITE UPS Electricity Rate")
    
    ep_cpu = np.array(data[cpu_key]) / 1000.0 if cpu_key and data[cpu_key] else np.zeros(96)
    ep_ite_fan = np.array(data[fan_key]) / 1000.0 if fan_key and data[fan_key] else np.zeros(96)
    ep_ups = np.array(data[ups_key]) / 1000.0 if ups_key and data[ups_key] else np.zeros(96)
    ep_ite_total_kw = ep_cpu + ep_ite_fan + ep_ups
    
    coil_elec_key = find_var(data, "Cooling Coil Electricity Rate")
    hvac_fan_key = find_var(data, "Fan Electricity Rate")
    
    ep_coil_elec = np.array(data[coil_elec_key]) / 1000.0 if coil_elec_key and data[coil_elec_key] else np.zeros(96)
    ep_hvac_fan = np.array(data[hvac_fan_key]) / 1000.0 if hvac_fan_key and data[hvac_fan_key] else np.zeros(96)
    
    coil_cool_key = find_var(data, "Cooling Coil Total Cooling Rate")
    ep_cooling_delivered = np.array(data[coil_cool_key]) / 1000.0 if coil_cool_key and data[coil_cool_key] else np.zeros(96)
    
    ep_len = len(ep_temp)
    ep_times = np.linspace(0.0, 24.0, ep_len)
    
    T_room_c = np.interp(times_h, ep_times, ep_temp)
    Q_total_kw = np.interp(times_h, ep_times, ep_ite_total_kw)
    cooling_coil_elec = np.interp(times_h, ep_times, ep_coil_elec)
    hvac_fan_elec = np.interp(times_h, ep_times, ep_hvac_fan)
    cooling_delivered_kw = np.interp(times_h, ep_times, ep_cooling_delivered)
    
    if np.max(Q_total_kw) < 1.0:
        Q_total_kw = np.full_like(times_h, total_racks * IDLE_RACK_KW)
        
    return {
        'T_room_c': T_room_c,
        'Q_total_kw': Q_total_kw,
        'cooling_coil_elec': cooling_coil_elec,
        'hvac_fan_elec': hvac_fan_elec,
        'cooling_delivered_kw': cooling_delivered_kw,
    }


def construct_sim_data_from_eplus(simplified_raw, eplus_raw, params):
    import numpy as np
    
    sim_data = simplified_raw.copy()
    times_h = sim_data['times_h']
    total_racks = sim_data['total_racks']
    
    ep_results = extract_eplus_time_series(eplus_raw, times_h, total_racks, IDLE_RACK_KW)
    
    sim_data['T_room_c'] = ep_results['T_room_c']
    sim_data['Q_total_kw'] = ep_results['Q_total_kw']
    sim_data['eplus_results'] = ep_results
    return sim_data


if st.session_state.get('simplified_raw') is not None:
    if sim_engine == "Simplified (Python Physics)" and st.session_state.sim_data != st.session_state.simplified_raw:
        st.session_state.sim_data = st.session_state.simplified_raw
        st.session_state.tou_costs = calculate_tou_cost(st.session_state.sim_data)
        st.rerun()
    elif sim_engine == "Advanced (EnergyPlus)" and st.session_state.get('eplus_raw') is not None and st.session_state.sim_data == st.session_state.simplified_raw:
        st.session_state.sim_data = construct_sim_data_from_eplus(st.session_state.simplified_raw, st.session_state.eplus_raw, {
            'room_length': room_length, 'room_width': room_width, 'room_height': room_height,
            'num_rows': num_rows, 'racks_per_row': racks_per_row,
            'dclc_effectiveness': dclc_effectiveness, 'rdhx_effectiveness': rdhx_effectiveness,
            'num_heat_exchangers': num_heat_exchangers, 'hx_capacity_kw': hx_capacity_kw,
            'num_air_handlers': num_air_handlers, 'cfm_per_handler': cfm_per_handler,
            'inlet_temp_c': inlet_temp_c
        })
        st.session_state.tou_costs = calculate_tou_cost(st.session_state.sim_data)
        st.rerun()


def compile_comparison_metrics(simplified_raw, eplus_raw, params):
    import numpy as np
    
    times_h = simplified_raw['times_h']
    dt_hours = float(times_h[1] - times_h[0]) if len(times_h) > 1 else (15.0 / 60.0)
    total_racks = simplified_raw['total_racks']
    
    sim_temp = simplified_raw['T_room_c']
    sim_it_kw = simplified_raw['Q_total_kw']
    
    sim_fac_power = []
    sim_cool_del = []
    sim_pue = []
    sim_hx_removed = []
    sim_pump_power = []
    sim_chiller_power = []
    sim_fan_power = []
    sim_outdoor_temp = []
    
    dclc_eff = params['dclc_effectiveness']
    rdhx_eff = params['rdhx_effectiveness']
    num_hx = params['num_heat_exchangers']
    hx_cap = params['hx_capacity_kw']
    
    for k in range(len(times_h)):
        step_res = calculate_thermal_system(
            params['room_length'], params['room_width'], params['room_height'],
            params['num_rows'], params['racks_per_row'], 63.0,
            rdhx_eff, dclc_eff, params['num_air_handlers'],
            num_hx, hx_cap, params['inlet_temp_c'], 30.0,
            params['cfm_per_handler'], times_h[k],
            cdu_flow_gpm=params['cdu_flow_gpm'], num_cdus=params['num_cdus'],
            delta_p_kpa=params['delta_p_kpa'], pump_eta=params['pump_eta'], cop=params['cop'],
            rack_powers_kw=simplified_raw['rack_powers_kw'][k],
            T_room_transient=sim_temp[k]
        )
        sim_fac_power.append(step_res['total_facility_power_kw'])
        cooling_del = step_res['Q_dclc_kw'] + step_res['Q_rdhx_kw'] + step_res['Q_hx_removed_kw']
        m_dot_cp = step_res['mass_flow_kg_s'] * 1007.0 / 1000.0
        air_handler_cooling = m_dot_cp * max(sim_temp[k] - params['inlet_temp_c'], 0.0)
        sim_cool_del.append(cooling_del + air_handler_cooling)
        sim_pue.append(step_res['pue'])
        sim_hx_removed.append(step_res['Q_hx_removed_kw'])
        sim_pump_power.append(step_res['p_pump_kw'])
        sim_chiller_power.append(step_res['p_mech_kw'])
        sim_fan_power.append(step_res['fan_power_kw'])
        sim_outdoor_temp.append(step_res['T_outdoor'])
        
    sim_it_energy = sum(sim_it_kw * dt_hours)
    sim_fac_energy = sum(np.array(sim_fac_power) * dt_hours)
    sim_cooling_delivered = sum(np.array(sim_cool_del) * dt_hours)
    sim_avg_temp = np.mean(sim_temp)
    sim_peak_temp = np.max(sim_temp)
    sim_avg_pue = np.mean(sim_pue)
    sim_peak_pue = np.max(sim_pue)
    sim_recovered_heat = sum(np.array(sim_hx_removed) * dt_hours)
    
    ep_results = extract_eplus_time_series(eplus_raw, times_h, total_racks, IDLE_RACK_KW)
    ep_temp = ep_results['T_room_c']
    
    #Reconstruct actual unscaled IT power for EnergyPlus
    ep_it_kw_actual = sim_it_kw
    
    #Calculate liquid cooling based on actual IT power
    ep_liquid_cooling_actual = ep_it_kw_actual * dclc_eff + ep_it_kw_actual * (1.0 - dclc_eff) * rdhx_eff
    
    #Heat exchanger recovery
    ep_hx_removed_actual = np.minimum(ep_liquid_cooling_actual, num_hx * hx_cap)
    ep_recovered_heat = sum(ep_hx_removed_actual * dt_hours)
    
    #Liquid loop heat rejected to chiller (which needs chiller electrical power)
    ep_q_rejected_kw = ep_liquid_cooling_actual - ep_hx_removed_actual
    ep_liquid_chiller_elec = ep_q_rejected_kw / params['cop']
    
    #Calculate total cooling delivered (air-side + liquid-side)
    ep_cooling_delivered_total_profile = ep_results['cooling_delivered_kw'] + ep_liquid_cooling_actual
    ep_cooling_delivered = sum(ep_cooling_delivered_total_profile * dt_hours)
    
    #Calculate total cooling electrical power
    ep_pump_kw = params['p_pump_kw']
    ep_cooling_power_total_profile = ep_results['cooling_coil_elec'] + ep_results['hvac_fan_elec'] + ep_pump_kw + ep_liquid_chiller_elec
    
    #Calculate total facility power and PUE
    ep_fac_power_actual = ep_it_kw_actual + ep_cooling_power_total_profile
    
    ep_it_energy = sum(ep_it_kw_actual * dt_hours)
    ep_fac_energy = sum(ep_fac_power_actual * dt_hours)
    ep_avg_temp = np.mean(ep_temp)
    ep_peak_temp = np.max(ep_temp)
    
    ep_pue = ep_fac_power_actual / np.maximum(ep_it_kw_actual, 1e-3)
    ep_pue = np.clip(ep_pue, 1.0, 5.0)
    ep_avg_pue = ep_fac_energy / ep_it_energy if ep_it_energy > 0 else 1.0
    ep_peak_pue = np.max(ep_pue)
    
    ep_outdoor_temp_profile = 26.5 + 5.5 * np.sin(2 * np.pi * (times_h - 9) / 24)
    
    return {
        'simplified': {
            'it_energy': sim_it_energy,
            'facility_energy': sim_fac_energy,
            'cooling_delivered': sim_cooling_delivered,
            'avg_temp': sim_avg_temp,
            'peak_temp': sim_peak_temp,
            'avg_pue': sim_avg_pue,
            'peak_pue': sim_peak_pue,
            'recovered_heat': sim_recovered_heat,
            'pue_profile': sim_pue,
            'temp_profile': sim_temp,
            'cooling_power_profile': np.array(sim_fac_power) - sim_it_kw,
            'it_power_profile': sim_it_kw,
            'facility_power_profile': np.array(sim_fac_power),
            'pump_power_profile': np.array(sim_pump_power),
            'chiller_power_profile': np.array(sim_chiller_power),
            'fan_power_profile': np.array(sim_fan_power),
            'recovered_heat_profile': np.array(sim_hx_removed),
            'outdoor_temp_profile': np.array(sim_outdoor_temp)
        },
        'eplus': {
            'it_energy': ep_it_energy,
            'facility_energy': ep_fac_energy,
            'cooling_delivered': ep_cooling_delivered,
            'avg_temp': ep_avg_temp,
            'peak_temp': ep_peak_temp,
            'avg_pue': ep_avg_pue,
            'peak_pue': ep_peak_pue,
            'recovered_heat': ep_recovered_heat,
            'pue_profile': ep_pue.tolist(),
            'temp_profile': ep_temp,
            'cooling_power_profile': ep_cooling_power_total_profile,
            'it_power_profile': ep_it_kw_actual,
            'facility_power_profile': ep_fac_power_actual,
            'pump_power_profile': np.full_like(times_h, ep_pump_kw),
            'chiller_power_profile': ep_results['cooling_coil_elec'] + ep_liquid_chiller_elec,
            'fan_power_profile': ep_results['hvac_fan_elec'],
            'recovered_heat_profile': ep_hx_removed_actual,
            'outdoor_temp_profile': ep_outdoor_temp_profile
        }
    }


def build_sim_data(scheduled_jobs,
                   room_length, room_width, room_height,
                   num_rows, racks_per_row,
                   dclc_effectiveness, rdhx_effectiveness,
                   num_heat_exchangers, hx_capacity_kw,
                   num_air_handlers, cfm_per_handler,
                   inlet_temp_c,
                   dt_sim_s=60,
                   dt_vis_s=900,
                   horizon_hours=24):
    total_racks = int(num_rows * racks_per_row)
    room_volume = room_length * room_width * room_height
    n_steps = int(horizon_hours * 3600 / dt_sim_s) + 1
    times_h = np.arange(n_steps, dtype=np.float64) * dt_sim_s / 3600.0

    # ── Vectorised outdoor temperature ────────────────────────────────────────
    T_outdoor_arr = 26.5 + 5.5 * np.sin(2.0 * np.pi * (times_h - 9.0) / 24.0)

    # ── Pre-extract job arrays for fast inner loop ────────────────────────────
    jobs_sorted = sorted(scheduled_jobs,
                         key=lambda j: (j.get('start_time', 0.0), j.get('id', 0)))
    n_jobs = len(jobs_sorted)
    j_starts = np.array([j.get('start_time', 0.0) for j in jobs_sorted], dtype=np.float64)
    j_ends   = np.array([j.get('end_time', -1.0)  for j in jobs_sorted], dtype=np.float64)
    j_powers = np.array([j.get('power_kw', 0.0)   for j in jobs_sorted], dtype=np.float32)
    j_nracks = np.array([j.get('num_racks', 0)     for j in jobs_sorted], dtype=np.int32)

    # ── Per-timestep rack power assignment ────────────────────────────────────
    # Broadcast active-job mask: shape (n_steps, n_jobs)
    active = np.zeros((n_steps, n_jobs), dtype=bool)
    for ji in range(n_jobs):
        start = j_starts[ji]
        end = j_ends[ji]
        if end > 24.0:
            active[:, ji] = (times_h >= start) | (times_h < end - 24.0)
        else:
            active[:, ji] = (times_h >= start) & (times_h < end)

    rack_powers_kw = np.full((n_steps, total_racks), IDLE_RACK_KW, dtype=np.float32)
    Q_total_kw = np.full(n_steps, total_racks * IDLE_RACK_KW, dtype=np.float32)

    for k in range(n_steps):
        idxs = np.where(active[k])[0]
        if len(idxs) == 0:
            continue
        taken = 0
        for ji in idxs:
            if taken >= total_racks:
                break
            nr = min(int(j_nracks[ji]), total_racks - taken)
            if nr > 0:
                rack_powers_kw[k, taken:taken + nr] = j_powers[ji]
                taken += nr
        Q_total_kw[k] = rack_powers_kw[k].sum()

    # ── Vectorised thermal integration ────────────────────────────────────────
    # Effective thermal capacitance includes air, server equipment, and the
    # shallow layer of concrete slab that participates in short-term transients.
    C_air = RHO * room_volume * CP
    C_equipment = total_racks * 500.0 * 500.0          # ~500 kg/rack, ~500 J/(kg·K) mixed metals
    C_slab = (room_length * room_width) * 0.05 * 2300.0 * 880.0  # top 5 cm of concrete floor
    C_eff = C_air + C_equipment + C_slab

    UA_WALLS = 0.19 * (2.0 * room_length * room_height)
    UA_FLOOR = 0.50 * (room_length * room_width)
    T_GROUND = 17.0

    Q_total_w = Q_total_kw.astype(np.float64) * 1000.0
    frac_to_air = (1.0 - dclc_effectiveness) * (1.0 - rdhx_effectiveness)
    Q_hx_cap_w = num_heat_exchangers * hx_capacity_kw * 1000.0
    Q_to_air_w = Q_total_w * frac_to_air
    Q_remaining_w = np.maximum(Q_to_air_w - Q_hx_cap_w, 0.0)

    if num_air_handlers > 0:
        total_cfm = num_air_handlers * cfm_per_handler
        m_dot = (total_cfm / 2119.0) * RHO
    else:
        power_density = Q_total_w / room_volume if room_volume > 0 else np.zeros_like(Q_total_w)
        ach = np.clip(5.0 + power_density / 1000.0, 5.0, 20.0)
        m_dot = (room_volume * ach / 3600.0) * RHO

    m_Cp = np.asarray(m_dot) * CP
    denom = m_Cp + UA_WALLS + UA_FLOOR
    T_ss_arr = (inlet_temp_c * m_Cp + Q_remaining_w
                + UA_WALLS * T_outdoor_arr + UA_FLOOR * T_GROUND) / denom

    # ODE: T[k+1] = T_ss + (T[k] - T_ss) * exp(-dt/tau)
    tau = C_eff / denom
    decay = np.exp(-dt_sim_s / tau)

    T_room_arr = np.empty(n_steps, dtype=np.float64)
    #Warmup loop to achieve periodic steady state (T(0) = T(24))
    t_init = float(inlet_temp_c)
    for warmup_iter in range(5):
        T_room_arr[0] = t_init
        for k in range(n_steps - 1):
            if np.isscalar(decay) is False:
                T_room_arr[k + 1] = T_ss_arr[k] + (T_room_arr[k] - T_ss_arr[k]) * decay[k]
            else:
                T_room_arr[k + 1] = T_ss_arr[k] + (T_room_arr[k] - T_ss_arr[k]) * decay
        # Carry over the final temperature to the next start
        t_final = T_room_arr[-1]
        if abs(t_final - t_init) < 0.05:
            break
        t_init = t_final
    np.clip(T_room_arr, inlet_temp_c - 5.0, inlet_temp_c + 80.0, out=T_room_arr)

    # ── Frame selection ───────────────────────────────────────────────────────
    frame_stride = max(1, int(dt_vis_s / dt_sim_s))
    frame_indices = np.arange(0, n_steps, frame_stride, dtype=int)

    def _fmt(h):
        hh = int(h) % 24
        mm = int(round((h - int(h)) * 60)) % 60
        return f"{hh:02d}:{mm:02d}"

    return {
        'times_h': times_h,
        'frame_indices': frame_indices,
        'frame_labels': [_fmt(times_h[i]) for i in frame_indices],
        'rack_powers_kw': rack_powers_kw,
        'Q_total_kw': Q_total_kw,
        'T_room_c': T_room_arr,
        'T_outdoor_arr': T_outdoor_arr,
        'total_racks': total_racks,
        'T_ss_arr': T_ss_arr,
    }


with col1:
    st.subheader("➕ Add New Job")

    job_col1, job_col2, job_col3 = st.columns(3)

    with job_col1:
        job_start_time_input = clock_time_input(
            label="Start Time",
            key="job_start_clock",
        )

    with job_col2:
        duration_raw = duration_time_input(
            label="Duration",
            key="job_duration",
        )
        job_duration_hours = duration_to_hours(duration_raw)

    with job_col3:
        gpu_power_level = gpu_power_input(
            label="GPU Power Level",
            options=list(POWER_LEVELS.keys()),
            default="Medium (50 kW)",
            key="job_gpu",
        )
        job_power_kw = POWER_LEVELS[gpu_power_level]

    total_available_racks = num_rows * racks_per_row
    job_num_racks = rack_count_input(
        label="Number of Racks",
        default=min(10, total_available_racks),
        min_racks=1,
        max_racks=total_available_racks,   # re-validated dynamically on every rerun
        key="job_rack_count",
    )

    # Add job button
    add_button_disabled = (
        job_start_time_input is None        # clock still showing hh:mm placeholder
        or duration_raw is None             # duration still showing hh:mm placeholder
        or job_duration_hours == 0.0        # duration of 00:00 is not valid
        or not rack_count_valid(job_num_racks, min_racks=1, max_racks=total_available_racks)
    )

    if st.button("➕ Add Job", type="primary", use_container_width=True, disabled=add_button_disabled):
        job_start_hour, job_start_min = map(int, job_start_time_input.split(":"))
        job_start_time = job_start_hour + job_start_min / 60.0
        job_end_time = job_start_time + job_duration_hours

        new_job = {
            'id': len(st.session_state.scheduled_jobs),
            'start_hour': job_start_hour,
            'start_min': job_start_min,
            'start_time': job_start_time,
            'duration': job_duration_hours,
            'end_time': job_end_time,
            'power_kw': job_power_kw,
            'num_racks': job_num_racks,
            'power_level': gpu_power_level
        }
        st.session_state.scheduled_jobs.append(new_job)
        st.rerun()

with col2:
    st.subheader("⚡ Current Status")

    status_left, status_right = st.columns(2)
    with status_left:
        st.metric("Total Jobs",      len(st.session_state.scheduled_jobs))
        st.metric("Available Racks", f"{total_available_racks}")
    with status_right:
        st.metric("Off-Peak Rate", "5.04¢/kWh",
                  help="Georgia Power TOU-HLF-16 — all hours outside 2PM–7PM")
        st.metric("On-Peak Rate",  "17.50¢/kWh",
                  delta="Active (14:00–19:00)",
                  delta_color="inverse",
                  help="June–Sep, Mon–Fri, 2PM–7PM under TOU-HLF-16")


# Display scheduled jobs in interactive timeline
if len(st.session_state.scheduled_jobs) > 0:
    st.subheader("📋 Scheduled Jobs Timeline")

    sorted_jobs = sorted(st.session_state.scheduled_jobs, key=lambda x: x['start_time'])

    timeline_action = _timeline_component(
        jobs=sorted_jobs,
        key=f"job_timeline_v{st.session_state.timeline_version}",
        default=None,
    )

    if isinstance(timeline_action, dict):
        action = timeline_action.get("action")
        if action == "delete":
            idx = timeline_action.get("idx")
            if idx is not None and 0 <= idx < len(sorted_jobs):
                st.session_state.scheduled_jobs.remove(sorted_jobs[idx])
                st.session_state.timeline_version += 1
                st.rerun()
        elif action == "clear":
            st.session_state.scheduled_jobs = []
            st.session_state.timeline_version += 1
            st.rerun()
else:
    st.info("📅 No jobs scheduled yet. Add your first job above to get started!")

# Run Simulation button — below the timeline
play_col1, play_col2 = st.columns(2)
with play_col1:
    play_button = st.button("▶️ Run Simulation", type="primary", use_container_width=True,
                            disabled=len(st.session_state.scheduled_jobs) == 0)
with play_col2:
    if eplus_available:
        compare_button = st.button("⚖️ Run Model Comparison", type="secondary", use_container_width=True,
                                   disabled=len(st.session_state.scheduled_jobs) == 0,
                                   help="Runs both the Simplified Physics and EnergyPlus Advanced solvers to compare their outputs.")
    else:
        st.button("⚖️ Run Model Comparison (Disabled)", type="secondary", use_container_width=True,
                  disabled=True,
                  help="Requires an EnergyPlus installation. Check the engine status at the top.")
        compare_button = False

should_run = play_button or compare_button or st.session_state.auto_run_sim
force_compare = compare_button

if should_run:
    st.session_state.auto_run_sim = False
    st.session_state.comp_data = None
    st.session_state.fig_comp = None
    st.session_state.fig_adv = None
    run_log = []
    run_log.append("**Step 1:** Starting simulation workflow...")
    start_time_perf = time.time()
    
    with st.spinner("Running Simplified solver..."):
        simplified_raw = build_sim_data(
            st.session_state.scheduled_jobs,
            room_length, room_width, room_height,
            num_rows, racks_per_row,
            dclc_effectiveness, rdhx_effectiveness,
            num_heat_exchangers, hx_capacity_kw,
            num_air_handlers, cfm_per_handler,
            inlet_temp_c,
        )
        st.session_state.simplified_raw = simplified_raw
        run_log.append("**Simplified Python Physics solver** completed (periodic steady state convergence achieved in 5 passes).")
        
    run_energyplus_engine = eplus_available and (sim_engine == "Advanced (EnergyPlus)" or force_compare)
    if run_energyplus_engine:
        run_log.append("**Step 2:** Triggering Advanced (EnergyPlus) solver...")
        with st.status("Running EnergyPlus Simulation...", expanded=True) as status:
            st.write("Generating detailed Input Data File (IDF)...")
            run_log.append("- Generated EnergyPlus IDF model file mapping geometry and schedule.")
            
            total_racks = num_rows * racks_per_row
            scenario = {
                'name': 'streamlit_run',
                'room': {
                    'length': room_length, 'width': room_width, 'height': room_height,
                },
                'racks': {
                    'rows': num_rows, 'racks_per_row': racks_per_row,
                    'power_per_rack': 63000.0, 'total_racks': total_racks, 'total_power': total_racks * 63000.0,
                },
                'cooling': {
                    'dclc_effectiveness': dclc_effectiveness,
                    'rdhx_effectiveness': rdhx_effectiveness,
                    'num_air_handlers': num_air_handlers,
                    'cfm_per_handler': cfm_per_handler,
                    'total_cfm': num_air_handlers * cfm_per_handler,
                    'total_flow_gpm': cdu_flow_gpm * num_cdus,
                },
                'heat_exchangers': {
                    'count': num_heat_exchangers,
                    'capacity_each': hx_capacity_kw * 1000.0,
                },
                'target_temp': inlet_temp_c,
                'cdu_flow_gpm': cdu_flow_gpm, 'num_cdus': num_cdus,
                'delta_p_kpa': delta_p_kpa, 'pump_eta': pump_eta, 'cop': cop
            }
            
            schedules = []
            for job in st.session_state.scheduled_jobs:
                schedules.append({
                    'name': f"Job_{job['id']}",
                    'start_hour': job['start_hour'],
                    'duration_hours': job['duration'],
                    'power_level': job['power_kw'] * 1000.0,
                    'num_racks': job['num_racks'],
                    'total_power': job['power_kw'] * job['num_racks'] * 1000.0,
                })
            scenario['schedules'] = schedules
            
            from model.EPlusIDF import DetailedIDFGenerator
            from model.run import run_energyplus
            from model.parse_eso import parse_eso_file
            
            generator = DetailedIDFGenerator(ENERGYPLUS_PATH)
            idf_filename = 'streamlit_run_detailed.idf'
            idf_path = Path('model/scenarios') / idf_filename
            generator.generate_scenario_from_dict(scenario, idf_path)
            
            st.write("🚀 Running EnergyPlus 25.1.0 engine (preprocessor & solver)...")
            run_log.append("- Invoking EnergyPlus 25.1.0 subprocess (solving heat equations).")
            success = run_energyplus(idf_filename)
            
            if success:
                st.write("Parsing simulation time-series output (.eso)...")
                run_log.append("- Reading and parsing eplusout.eso dataset.")
                eso_path = Path('model/outputs/streamlit_run_detailed/eplusout.eso')
                if eso_path.exists():
                    vars_map, eplus_raw = parse_eso_file(eso_path)
                    st.session_state.eplus_raw = eplus_raw
                    st.session_state.sim_data = construct_sim_data_from_eplus(simplified_raw, eplus_raw, {
                        'room_length': room_length, 'room_width': room_width, 'room_height': room_height,
                        'num_rows': num_rows, 'racks_per_row': racks_per_row,
                        'dclc_effectiveness': dclc_effectiveness, 'rdhx_effectiveness': rdhx_effectiveness,
                        'num_heat_exchangers': num_heat_exchangers, 'hx_capacity_kw': hx_capacity_kw,
                        'num_air_handlers': num_air_handlers, 'cfm_per_handler': cfm_per_handler,
                        'inlet_temp_c': inlet_temp_c
                    })
                    status.update(label="EnergyPlus simulation complete!", state="complete", expanded=False)
                    run_log.append("**EnergyPlus Advanced solver** completed successfully.")
                    st.session_state.last_run_status = "success"
                else:
                    st.session_state.eplus_raw = None
                    st.session_state.sim_data = simplified_raw
                    status.update(label="Failed to find eplusout.eso file", state="error")
                    run_log.append("**EnergyPlus failed**: eplusout.eso file was not found.")
                    st.session_state.last_run_status = "failed"
            else:
                st.session_state.eplus_raw = None
                st.session_state.sim_data = simplified_raw
                status.update(label="EnergyPlus simulation failed", state="error")
                run_log.append("**EnergyPlus failed**: Solver execution error.")
                st.session_state.last_run_status = "failed"
    else:
        st.session_state.eplus_raw = None
        st.session_state.sim_data = simplified_raw
        st.session_state.last_run_status = "success"
        
    st.session_state.tou_costs = calculate_tou_cost(st.session_state.sim_data)
    st.session_state.sim_frame = 0
    st.session_state.sim_fingerprint = _current_fingerprint
    st.session_state.sim_stale = False
    st.session_state.scroll_to_viz = True
    
    elapsed_time = time.time() - start_time_perf
    run_log.append(f"Total execution time: {elapsed_time:.2f} seconds.")
    
    st.session_state.last_run_engine = "Advanced (EnergyPlus)" if run_energyplus_engine else "Simplified (Python Physics)"
    st.session_state.last_run_timestamp = time.strftime("%I:%M:%S %p")
    st.session_state.last_run_log = run_log
    st.session_state.show_comparison_notice = force_compare

st.divider()

if st.session_state.get('last_run_log'):
    with st.expander("View Simulation Run Logs & Process Details", expanded=False):
        for log_line in st.session_state.last_run_log:
            st.markdown(log_line)
            
        if st.session_state.get('eplus_raw') is not None or "Advanced (EnergyPlus)" in st.session_state.get('last_run_engine', ''):
            idf_path = Path('model/scenarios/streamlit_run_detailed.idf')
            if idf_path.exists():
                st.markdown("---")
                try:
                    with open(idf_path, 'r') as f:
                        idf_text = f.read()
                    st.download_button(
                        "Download Generated EnergyPlus Input File (IDF)",
                        data=idf_text,
                        file_name="streamlit_run_detailed.idf",
                        mime="text/plain",
                        use_container_width=True
                    )
                except Exception as e:
                    st.caption(f"Could not load IDF file: {e}")

comparison_available = (
    st.session_state.get('simplified_raw') is not None 
    and st.session_state.get('eplus_raw') is not None
)
if st.session_state.get('show_comparison_notice') and comparison_available:
    st.info(
        "**Model Comparison Data Ready** \n\n"
        "Both the fast Simplified Physics solver and the detailed EnergyPlus Advanced solver have been run. "
        "Scroll down to the **Heat Flow & Cooling** section at the bottom of the page and select the "
        "**Model Comparison** tab to inspect the deviation metrics, validation status, and transient comparison charts.",
        icon="⚖️"
    )


def plot_thermal_field(results):
    """Create thermal visualization"""

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Convert fields to Fahrenheit for display
    T_f = results['T'] * 9 / 5 + 32
    T_inlet_f = results['T_inlet'] * 9 / 5 + 32
    waste_threshold_f = results['waste_threshold'] * 9 / 5 + 32

    # === THERMAL MAP (°F) ===
    levels_contourf = np.linspace(T_inlet_f, waste_threshold_f, 31)
    im1 = ax1.contourf(results['X'], results['Y'], T_f,
                       levels=levels_contourf, cmap='RdYlBu_r',
                       vmin=T_inlet_f, vmax=waste_threshold_f,
                       extend='both')
    fig.colorbar(im1, ax=ax1, label='Temperature (°F)', shrink=0.85)

    # Contour lines (°F)
    levels_f = np.linspace(T_inlet_f, waste_threshold_f, 5)
    contours = ax1.contour(results['X'], results['Y'], T_f,
                           levels=levels_f, colors='black', linewidths=1.2, alpha=0.5)
    ax1.clabel(contours, inline=True, fontsize=8, fmt='%.1f°F')

    # Plot racks — active (power > idle) in dark red, idle in grey
    for rack in results['racks']:
        is_active = rack['power_kw'] > IDLE_RACK_KW + 1e-6
        rect = Rectangle((rack['x'] - rack['width'] / 2, rack['y'] - rack['depth'] / 2),
                         rack['width'], rack['depth'],
                         facecolor='darkred' if is_active else 'dimgray',
                         edgecolor='black',
                         linewidth=0.3,
                         alpha=0.85 if is_active else 0.55)
        ax1.add_patch(rect)

        # RDHX indicator (blue strip)
        rdhx = Rectangle((rack['x'] - rack['width'] / 2, rack['y'] + rack['depth'] / 2 - 0.1),
                         rack['width'], 0.1,
                         facecolor='royalblue', alpha=0.95)
        ax1.add_patch(rdhx)

    legend_handles = [
        Patch(facecolor='darkred', edgecolor='black', alpha=0.85, label='Active rack'),
        Patch(facecolor='dimgray', edgecolor='black', alpha=0.55, label='Idle rack'),
    ]
    ax1.legend(handles=legend_handles, loc='upper right', fontsize=8, framealpha=0.9)

    # Plot air handlers
    for handler in results['air_handlers']:
        rect = Rectangle((handler['x'] - handler['width'] / 2, handler['y'] - handler['height'] / 2),
                         handler['width'], handler['height'],
                         facecolor='steelblue', edgecolor='navy',
                         linewidth=2, alpha=0.9, hatch='///')
        ax1.add_patch(rect)

        rotation = 90 if handler['side'] in ('left', 'right') else 0
        ax1.text(handler['x'], handler['y'], 'AIR\nHANDLER',
                 ha='center', va='center', fontsize=10,
                 color='white', fontweight='bold', rotation=rotation)

        # Airflow arrows
        if handler['side'] == 'left':
            ax1.arrow(handler['x'] + handler['width'] / 2 + 0.7, handler['y'],
                      -0.5, 0, head_width=0.25, head_length=0.15,
                      fc='cyan', ec='cyan', alpha=0.7, linewidth=2)
        elif handler['side'] == 'right':
            ax1.arrow(handler['x'] - handler['width'] / 2 - 0.7, handler['y'],
                      0.5, 0, head_width=0.25, head_length=0.15,
                      fc='cyan', ec='cyan', alpha=0.7, linewidth=2)

    # Plot heat exchangers
    for hx in results['hx_positions']:
        rect = Rectangle((hx['x'] - hx['width'] / 2, hx['y'] - hx['height'] / 2),
                         hx['width'], hx['height'],
                         facecolor='green', edgecolor='darkgreen',
                         linewidth=2, alpha=0.85, hatch='xxx')
        ax1.add_patch(rect)

        ax1.text(hx['x'], hx['y'], 'HEAT\nEXCH',
                 ha='center', va='center', fontsize=9,
                 color='white', fontweight='bold')

    ax1.set_xlabel('Room Length (m)', fontsize=10)
    ax1.set_ylabel('Room Width (m)', fontsize=10)

    _h = int(results["time_of_day"])
    _m = int(round((results["time_of_day"] - _h) * 60))
    ax1.set_title(
        f'Thermal Map: {results["active_racks"]}/{results["total_racks"]} Active Racks'
        f'  |  Current IT Load: {results["Q_total_kw"]:.0f} kW',
        fontsize=11, fontweight='bold')

    ax1.set_xlim([0, results['room_length']])
    ax1.set_ylim([0, results['room_width']])
    ax1.grid(True, alpha=0.3, linewidth=0.5)
    ax1.set_aspect('equal')

    # === HOT ZONES MAP (°F above threshold) ===
    hot_zones_f = np.where(results['T'] > results['waste_threshold'],
                           (results['T'] - results['waste_threshold']) * 9 / 5, 0)

    im2 = ax2.contourf(results['X'], results['Y'], hot_zones_f,
                       levels=10, cmap='hot', vmin=0, vmax=9)
    fig.colorbar(im2, ax=ax2, label='°F above threshold', shrink=0.85)

    if results['hot_spots'] > 0:
        ax2.contour(results['X'], results['Y'], T_f,
                    levels=[waste_threshold_f],
                    colors='cyan', linewidths=3)

    ax2.set_xlabel('Room Length (m)', fontsize=10)
    ax2.set_ylabel('Room Width (m)', fontsize=10)

    if results['hot_spots'] > 0:
        title = f'Hot Zones (>{waste_threshold_f:.0f}°F)\n⚠ {results["hot_spot_percent"]:.1f}% of room'
    else:
        title = f'Hot Zones (>{waste_threshold_f:.0f}°F)\n✓ All zones OK'

    ax2.set_title(title, fontsize=11, fontweight='bold')
    ax2.set_xlim([0, results['room_length']])
    ax2.set_ylim([0, results['room_width']])
    ax2.grid(True, alpha=0.3, linewidth=0.5)
    ax2.set_aspect('equal')

    plt.tight_layout()
    return fig


# Calculate thermal system
sim = st.session_state.sim_data

selected_T_room_transient = None
if sim is not None:
    frame_idx = st.session_state.sim_frame
    n_frames = len(sim['frame_indices'])
    step = sim['frame_indices'][frame_idx]
    selected_rack_powers_kw = sim['rack_powers_kw'][step]
    selected_time_of_day = float(sim['times_h'][step])
    selected_T_room_transient = float(sim['T_room_c'][step])
else:
    selected_rack_powers_kw = None
    selected_time_of_day = time_of_day

results = calculate_thermal_system(
    room_length, room_width, room_height,
    num_rows, racks_per_row, rack_power_kw,
    rdhx_effectiveness, dclc_effectiveness, num_air_handlers,
    num_heat_exchangers, hx_capacity_kw,
    inlet_temp_c, waste_threshold_c, cfm_per_handler,
    selected_time_of_day,
    cdu_flow_gpm=cdu_flow_gpm, num_cdus=num_cdus,
    delta_p_kpa=delta_p_kpa, pump_eta=pump_eta, cop=cop,
    rack_powers_kw=selected_rack_powers_kw,
    T_room_transient=selected_T_room_transient,
)

# Scroll anchor and auto-scroll on simulation run
st.markdown('<div id="thermal-viz"></div>', unsafe_allow_html=True)
st.header("Job Scheduler Simulation")
if st.session_state.scroll_to_viz:
    components.html(
        """
        <script>
            window.parent.document.getElementById('thermal-viz').scrollIntoView({behavior: 'smooth'});
        </script>
        """,
        height=0,
    )
    st.session_state.scroll_to_viz = False

# Playback controls rendered here — between title and plots
if sim is not None:
    frame_idx = st.session_state.sim_frame
    n_frames = len(sim['frame_indices'])

    btn_col1, btn_col2, btn_col3, _space = st.columns([1, 1, 1, 5])
    with btn_col1:
        if st.button("⏮ Prev", use_container_width=True, disabled=st.session_state.sim_playing):
            st.session_state.sim_frame = max(0, frame_idx - 1)
            st.rerun()
    with btn_col2:
        if st.session_state.sim_playing:
            if st.button("⏸ Pause", use_container_width=True):
                st.session_state.sim_playing = False
                st.rerun()
        else:
            if st.button("▶️ Play", use_container_width=True):
                st.session_state.sim_playing = True
                st.rerun()
    with btn_col3:
        if st.button("Next ⏭", use_container_width=True, disabled=st.session_state.sim_playing):
            st.session_state.sim_frame = min(n_frames - 1, frame_idx + 1)
            st.rerun()

    new_frame = st.select_slider(
        "Simulation Time",
        options=list(range(n_frames)),
        value=st.session_state.sim_frame,
        format_func=lambda i: sim['frame_labels'][i],
        disabled=st.session_state.sim_playing,
    )
    if not st.session_state.sim_playing:
        st.session_state.sim_frame = new_frame

# Display plots
if st.session_state.sim_stale:
    st.warning("Settings changed — simulation cleared. Press **▶️ Run Simulation** to update.")
st.pyplot(plot_thermal_field(results))

# ===== DASHBOARD =====
st.header("Dashboard")
dash1, dash2, dash3, dash4 = st.columns(4)

with dash1:
    st.metric("Room Temperature", f"{results['T_room'] * 9 / 5 + 32:.1f}°F",
              delta=f"{(results['T_room'] - results['T_inlet']) * 9 / 5:.1f}°F above inlet",
              help="Average room temperature", border=True)

with dash2:
    pue_color = "normal" if results['pue'] < 1.3 else "inverse"
    st.metric("PUE", f"{results['pue']:.2f}",
              delta="Good" if results['pue'] < 1.3 else "Can improve",
              delta_color=pue_color,
              help="Power Usage Effectiveness. Lower is better. <1.3 is excellent",
              border=True)

with dash3:
    if results['hot_spots'] > 0:
        st.metric("Hot Spots", f"{results['hot_spot_percent']:.1f}%",
                  delta="Warning", delta_color="inverse",
                  help=f"Room area above {waste_threshold_c}°C threshold",
                  border=True)
    else:
        st.metric("Hot Spots", "0%",
                  delta="All OK", delta_color="normal",
                  help="No areas exceed temperature threshold",
                  border=True)

with dash4:
    st.metric("Total Cooling Power", f"{results['p_cooling_total_kw']:.0f} kW",
              help="Pumps + Chiller + Fans combined electrical demand",
              border=True)

# ── TOU Scheduling Metrics — live, frame-accurate ────────────────────────
# All four metrics computed up to the current simulation frame.
# Job load = total IT − idle baseline (total_racks × IDLE_RACK_KW), floored at 0.
if sim is not None:
    _step          = sim['frame_indices'][st.session_state.sim_frame]
    _dt_h          = float(sim['times_h'][1] - sim['times_h'][0])
    _idle_kw_total = int(sim['total_racks']) * IDLE_RACK_KW

    _cum_cost      = 0.0   # Accumulated Job IT Cost
    _cum_kwh       = 0.0   # Running Total IT Job Load (kWh)
    _cum_offpk_kwh = 0.0   # Off-peak portion of the above

    for _s in range(_step + 1):
        _t_h    = float(sim['times_h'][_s]) % 24
        _job_kw = max(0.0, float(sim['Q_total_kw'][_s]) - _idle_kw_total)
        _rate   = TOU_ON_PEAK_RATE if is_on_peak(_t_h) else TOU_OFF_PEAK_RATE
        _e      = _job_kw * _dt_h
        _cum_cost += _e * _rate
        _cum_kwh  += _e
        if not is_on_peak(_t_h):
            _cum_offpk_kwh += _e

    _cur_job_kw  = max(0.0, float(sim['Q_total_kw'][_step]) - _idle_kw_total)
    _offpk_pct   = (_cum_offpk_kwh / _cum_kwh * 100) if _cum_kwh > 0 else 0.0
    _onpk_kwh    = _cum_kwh - _cum_offpk_kwh
    _eff_color   = "normal" if _offpk_pct >= 80 else "inverse" if _offpk_pct < 50 else "off"

    tou1, tou2, tou3, tou4 = st.columns(4)
    with tou1:
        st.metric(
            "Accumulated Job IT Cost",
            f"${_cum_cost:.2f}",
            help="Running IT energy cost for scheduled jobs up to current simulation time. "
                 "Idle baseline excluded. No PUE.",
            border=True,
        )
    with tou2:
        st.metric(
            "Current Job IT Load",
            f"{_cur_job_kw:.0f} kW",
            help="Incremental IT power from active jobs at this timestep. "
                 "Idle baseline excluded.",
            border=True,
        )
    with tou3:
        st.metric(
            "Running Job IT Load",
            f"{_cum_kwh:.1f} kWh",
            help="Cumulative incremental IT energy consumed by jobs up to current time. "
                 "Idle baseline excluded.",
            border=True,
        )
    with tou4:
        st.metric(
            "Job Load Off-Peak",
            f"{_offpk_pct:.0f}%",
            help="Percentage of cumulative job IT energy that ran during off-peak hours "
                 "(outside 14:00–19:00).",
            border=True,
        )

st.divider()

# ===== HEAT FLOW & COOLING =====
st.header("Heat Flow & Cooling")

ANNUAL_LOAD_FACTOR = 0.8
annual_mwh = results['Q_liquid_cooling_kw'] * 8760 * ANNUAL_LOAD_FACTOR / 1000

has_comparison = (
    st.session_state.get('simplified_raw') is not None 
    and st.session_state.get('eplus_raw') is not None
)

if has_comparison:
    tab_hf, tab_env, tab_ci, tab_comp = st.tabs([
        "Heat Flow", "Building Envelope", "Cooling Infrastructure", "⚖️ Model Comparison"
    ])
else:
    tab_hf, tab_env, tab_ci = st.tabs([
        "Heat Flow", "Building Envelope", "Cooling Infrastructure"
    ])

with tab_hf:
    hf1, hf2, hf3, hf4, hf5 = st.columns(5)
    with hf1:
        st.metric("IT Load", f"{results['Q_total_kw']:.0f} kW",
                  help=f"{results['total_racks']} racks", border=True)
    with hf2:
        st.metric("DCLC", f"-{results['Q_dclc_kw']:.0f} kW",
                  help=f"{dclc_effectiveness * 100:.0f}% captured at CPUs/GPUs", border=True)
    with hf3:
        st.metric("RDHX", f"-{results['Q_rdhx_kw']:.0f} kW",
                  help=f"{rdhx_effectiveness * 100:.0f}% of remaining captured at rear doors",
                  border=True)
    with hf4:
        st.metric("Waste HX", f"-{results['Q_hx_removed_kw']:.0f} kW",
                  help=f"{num_heat_exchangers} heat exchangers", border=True)
    with hf5:
        st.metric("To Room Air", f"{results['Q_remaining_kw']:.0f} kW",
                  help="Remaining heat handled by air circulation", border=True)

    if num_heat_exchangers > 0:
        st.success(
            f"**Waste Heat Recovery Active** — {results['Q_hx_removed_kw']:.0f} kW captured | "
            f"~{annual_mwh:.0f} MWh/year potential savings"
        )
    else:
        st.info(
            f"{results['Q_liquid_cooling_kw']:.0f} kW of heat available for recovery — "
            f"add heat exchangers in the sidebar (~{annual_mwh:.0f} MWh/year potential)"
        )

with tab_env:
    env1, env2, env3 = st.columns(3)
    walls_sign = "+" if results['Q_walls_kw'] >= 0 else ""
    with env1:
        st.metric("Exterior Walls", f"{walls_sign}{results['Q_walls_kw']:.1f} kW",
                  help="Heat through two exterior walls. Positive = heat entering from outdoors.",
                  border=True)
    with env2:
        st.metric("Floor to Ground", f"-{results['Q_floor_kw']:.1f} kW",
                  help="Passive cooling into 17°C ground slab. Always removes heat when room > 17°C.",
                  border=True)
    with env3:
        st.metric("Outdoor Temp",
                  f"{results['T_outdoor']:.1f}°C ({results['T_outdoor'] * 9 / 5 + 32:.1f}°F)",
                  help="Sinusoidal profile for Atlanta July day. Peak ~32°C at 3PM, low ~21°C at 5AM.",
                  border=True)
    env_net = results['Q_walls_kw'] - results['Q_floor_kw']
    st.caption(f"Net envelope effect: {env_net:+.1f} kW")

with tab_ci:
    ci1, ci2 = st.columns(2)
    with ci1:
        st.metric("CDU Return Temp", f"{results['t_return_c']:.1f}°C",
                  delta=f"{results['t_return_c'] - 40.0:+.1f}°C vs 40°C target",
                  delta_color="normal" if results['heat_recovery_viable'] else "inverse",
                  help="Must reach 40°C for waste heat recovery",
                  border=True)
        if results['heat_recovery_viable']:
            st.success("Hot enough for waste heat recovery (>= 40°C)")
        else:
            st.warning("Below 40°C — increase load or reduce flow rate")

    with ci2:
        with st.container(border=True):
            ci2a, ci2b, ci2c = st.columns(3)
            with ci2a:
                st.metric("Pump", f"{results['p_pump_kw']:.1f} kW", border=True,
                          help="Electrical power to circulate coolant through the liquid cooling loop")
            with ci2b:
                st.metric("Chiller", f"{results['p_mech_kw']:.0f} kW", border=True,
                          help="Mechanical cooling power to reject heat that isn't recovered")
            with ci2c:
                st.metric("Fans", f"{results['fan_power_kw']:.0f} kW", border=True,
                          help="Air handler fan power for room air circulation")
            st.caption(
                f"Total: {results['p_cooling_total_kw']:.0f} kW | "
                f"Flow: {results['m_dot_liquid_gpm']:.0f} GPM | "
                f"Heat to reject: {results['q_rejected_kw']:.0f} kW"
            )

if has_comparison:
    with tab_comp:
        st.markdown("### ⚖️ Simplified vs. EnergyPlus Advanced Model Validation")
        st.markdown(
            "This table compares the daily integrated metrics of the Simplified (Python Physics) model "
            "against the Advanced (EnergyPlus) model under the same zone conditions."
        )
        
        if st.session_state.get('comp_data') is None:
            st.session_state.comp_data = compile_comparison_metrics(
                st.session_state.simplified_raw,
                st.session_state.eplus_raw,
                {
                    'room_length': room_length, 'room_width': room_width, 'room_height': room_height,
                    'num_rows': num_rows, 'racks_per_row': racks_per_row,
                    'dclc_effectiveness': dclc_effectiveness, 'rdhx_effectiveness': rdhx_effectiveness,
                    'num_heat_exchangers': num_heat_exchangers, 'hx_capacity_kw': hx_capacity_kw,
                    'num_air_handlers': num_air_handlers, 'cfm_per_handler': cfm_per_handler,
                    'inlet_temp_c': inlet_temp_c, 'scheduled_jobs': st.session_state.scheduled_jobs,
                    'cdu_flow_gpm': cdu_flow_gpm, 'num_cdus': num_cdus,
                    'delta_p_kpa': delta_p_kpa, 'pump_eta': pump_eta, 'cop': cop,
                    'p_pump_kw': results['p_pump_kw']
                }
            )
        comp_data = st.session_state.comp_data
        
        sim_metrics = comp_data['simplified']
        ep_metrics = comp_data['eplus']
        
        def make_row(label, sim_val, ep_val, unit, is_percent=False):
            abs_dev = ep_val - sim_val
            if sim_val != 0:
                pct_dev = (abs_dev / sim_val) * 100.0
            else:
                pct_dev = 0.0
            
            if is_percent:
                sim_str = f"{sim_val:.2f}%"
                ep_str = f"{ep_val:.2f}%"
                abs_str = f"{abs_dev:+.2f}%"
            else:
                sim_str = f"{sim_val:,.1f} {unit}".strip()
                ep_str = f"{ep_val:,.1f} {unit}".strip()
                abs_str = f"{abs_dev:+,.1f} {unit}".strip()
                
            pct_str = f"{pct_dev:+.1f}%"
            
            return {
                "Metric": label,
                "Simplified (Expected)": sim_str,
                "Advanced (EnergyPlus)": ep_str,
                "Absolute Deviation": abs_str,
                "Percentage Deviation": pct_str
            }
            
        rows = [
            make_row("Total IT & Cooling Energy Consumed", sim_metrics['facility_energy'], ep_metrics['facility_energy'], "kWh"),
            make_row("Total Cooling Energy Delivered", sim_metrics['cooling_delivered'], ep_metrics['cooling_delivered'], "kWh"),
            make_row("Average Room Temperature", sim_metrics['avg_temp'], ep_metrics['avg_temp'], "°C"),
            make_row("Peak Room Temperature", sim_metrics['peak_temp'], ep_metrics['peak_temp'], "°C"),
            make_row("Average PUE", sim_metrics['avg_pue'], ep_metrics['avg_pue'], ""),
            make_row("Peak PUE", sim_metrics['peak_pue'], ep_metrics['peak_pue'], ""),
            make_row("Recovered Waste Heat", sim_metrics['recovered_heat'], ep_metrics['recovered_heat'], "kWh"),
        ]
        
        import pandas as pd
        df = pd.DataFrame(rows)
        st.table(df)
        
        st.markdown("#### Transient Profiles Comparison")
        if st.session_state.get('fig_comp') is None:
            fig_comp, (ax_temp, ax_cool, ax_pue) = plt.subplots(1, 3, figsize=(16, 4.5))
            times_h = st.session_state.simplified_raw['times_h']
            
            ax_temp.plot(times_h, sim_metrics['temp_profile'], label='Simplified (Python)', color='#0984e3', linewidth=2)
            ax_temp.plot(times_h, ep_metrics['temp_profile'], label='EnergyPlus', color='#d63031', linewidth=2, linestyle='--')
            ax_temp.set_title('Zone Temperature Comparison')
            ax_temp.set_xlabel('Hour of Day')
            ax_temp.set_ylabel('Temperature (°C)')
            ax_temp.grid(True, alpha=0.3)
            ax_temp.legend()
            
            ax_cool.plot(times_h, sim_metrics['cooling_power_profile'], label='Simplified (Python)', color='#0984e3', linewidth=2)
            ax_cool.plot(times_h, ep_metrics['cooling_power_profile'], label='EnergyPlus', color='#d63031', linewidth=2, linestyle='--')
            ax_cool.set_title('Cooling Power Comparison')
            ax_cool.set_xlabel('Hour of Day')
            ax_cool.set_ylabel('Power (kW)')
            ax_cool.grid(True, alpha=0.3)
            ax_cool.legend()
            
            ax_pue.plot(times_h, sim_metrics['pue_profile'], label='Simplified (Python)', color='#0984e3', linewidth=2)
            ax_pue.plot(times_h, ep_metrics['pue_profile'], label='EnergyPlus', color='#d63031', linewidth=2, linestyle='--')
            ax_pue.set_title('PUE Comparison')
            ax_pue.set_xlabel('Hour of Day')
            ax_pue.set_ylabel('PUE')
            ax_pue.grid(True, alpha=0.3)
            ax_pue.legend()
            
            fig_comp.tight_layout()
            st.session_state.fig_comp = fig_comp
            plt.close(fig_comp)
            
        st.pyplot(st.session_state.fig_comp)
        
        st.markdown("---")
        st.markdown("#### Advanced Model Analysis & Correlation Plots")
        st.markdown(
            "Click the button below to generate advanced visual comparisons, including cumulative facility electricity "
            "and PUE sensitivity as a function of server IT load."
        )
        
        gen_plots_button = st.button("Generate Advanced Comparison Plots", type="primary", use_container_width=True)
        if gen_plots_button:
            st.session_state.show_adv_plots = True
            st.session_state.fig_adv = None
            
        if st.session_state.show_adv_plots:
            if st.session_state.get('fig_adv') is None:
                with st.spinner("Generating advanced analytical plots..."):
                    import warnings
                    fig_adv, axs = plt.subplots(3, 2, figsize=(16, 13))
                    ax_cum = axs[0, 0]
                    ax_scatter = axs[0, 1]
                    ax_cool_sim = axs[1, 0]
                    ax_cool_ep = axs[1, 1]
                    ax_whr = axs[2, 0]
                    ax_temp_env = axs[2, 1]
                    
                    times_h = st.session_state.simplified_raw['times_h']
                    dt_hours = float(times_h[1] - times_h[0]) if len(times_h) > 1 else (1.0 / 60.0)
                    
                    sim_cum_energy = np.cumsum(sim_metrics['facility_power_profile']) * dt_hours
                    ep_cum_energy = np.cumsum(ep_metrics['facility_power_profile']) * dt_hours
                    
                    ax_cum.plot(times_h, sim_cum_energy, label='Simplified (Python)', color='#0984e3', linewidth=2.5)
                    ax_cum.plot(times_h, ep_cum_energy, label='EnergyPlus', color='#d63031', linewidth=2.5, linestyle='--')
                    ax_cum.set_title('Cumulative Facility Energy Consumption', fontsize=11, fontweight='bold')
                    ax_cum.set_xlabel('Hour of Day', fontsize=9)
                    ax_cum.set_ylabel('Total Electricity Consumed (kWh)', fontsize=9)
                    ax_cum.grid(True, alpha=0.3)
                    ax_cum.legend(fontsize=8)
                    
                    sim_it_p = sim_metrics['it_power_profile']
                    sim_pue_p = sim_metrics['pue_profile']
                    ep_it_p = ep_metrics['it_power_profile']
                    ep_pue_p = ep_metrics['pue_profile']
                    
                    ax_scatter.scatter(sim_it_p, sim_pue_p, label='Simplified (Python)', color='#0984e3', alpha=0.5, s=25)
                    ax_scatter.scatter(ep_it_p, ep_pue_p, label='EnergyPlus', color='#d63031', alpha=0.5, s=25, marker='x')
                    
                    try:
                        if len(sim_it_p) > 5 and np.max(sim_it_p) - np.min(sim_it_p) > 1.0 and len(np.unique(sim_it_p)) >= 3:
                            with warnings.catch_warnings():
                                warnings.simplefilter('ignore', np.RankWarning)
                                sim_fit = np.polyfit(sim_it_p, sim_pue_p, 2)
                                ep_fit = np.polyfit(ep_it_p, ep_pue_p, 2)
                                
                                fit_x = np.linspace(np.min(sim_it_p), np.max(sim_it_p), 100)
                                ax_scatter.plot(fit_x, np.polyval(sim_fit, fit_x), color='#0984e3', linestyle='-', linewidth=1.5, alpha=0.8)
                                ax_scatter.plot(fit_x, np.polyval(ep_fit, fit_x), color='#d63031', linestyle='--', linewidth=1.5, alpha=0.8)
                    except Exception:
                        pass
                    
                    ax_scatter.set_title('PUE Sensitivity to Server IT Load', fontsize=11, fontweight='bold')
                    ax_scatter.set_xlabel('Server IT Load (kW)', fontsize=9)
                    ax_scatter.set_ylabel('Power Usage Effectiveness (PUE)', fontsize=9)
                    ax_scatter.grid(True, alpha=0.3)
                    ax_scatter.legend(fontsize=8)
                    
                    sim_pump = sim_metrics['pump_power_profile']
                    sim_chiller = sim_metrics['chiller_power_profile']
                    sim_fan = sim_metrics['fan_power_profile']
                    
                    ax_cool_sim.stackplot(times_h, sim_pump, sim_chiller, sim_fan, 
                                          labels=['Pumps', 'Chillers', 'Fans'], 
                                          colors=['#00cec9', '#e17055', '#6c5ce7'], alpha=0.75)
                    ax_cool_sim.set_title('Simplified Cooling Power Breakdown', fontsize=11, fontweight='bold')
                    ax_cool_sim.set_xlabel('Hour of Day', fontsize=9)
                    ax_cool_sim.set_ylabel('Power demand (kW)', fontsize=9)
                    ax_cool_sim.grid(True, alpha=0.3)
                    ax_cool_sim.legend(loc='upper left', fontsize=8)
                    
                    ep_pump = ep_metrics['pump_power_profile']
                    ep_chiller = ep_metrics['chiller_power_profile']
                    ep_fan = ep_metrics['fan_power_profile']
                    
                    ax_cool_ep.stackplot(times_h, ep_pump, ep_chiller, ep_fan, 
                                         labels=['Pumps', 'Chillers/Coils', 'Fans'], 
                                         colors=['#00cec9', '#e17055', '#6c5ce7'], alpha=0.75)
                    ax_cool_ep.set_title('EnergyPlus Cooling Power Breakdown', fontsize=11, fontweight='bold')
                    ax_cool_ep.set_xlabel('Hour of Day', fontsize=9)
                    ax_cool_ep.set_ylabel('Power demand (kW)', fontsize=9)
                    ax_cool_ep.grid(True, alpha=0.3)
                    ax_cool_ep.legend(loc='upper left', fontsize=8)
                    
                    sim_whr = sim_metrics['recovered_heat_profile']
                    ep_whr = ep_metrics['recovered_heat_profile']
                    
                    ax_whr.plot(times_h, sim_whr, label='Simplified (Python)', color='#0984e3', linewidth=2.5)
                    ax_whr.plot(times_h, ep_whr, label='EnergyPlus', color='#d63031', linewidth=2.5, linestyle='--')
                    ax_whr.set_title('Waste Heat Recovery Rate', fontsize=11, fontweight='bold')
                    ax_whr.set_xlabel('Hour of Day', fontsize=9)
                    ax_whr.set_ylabel('Recovered Heat (kW)', fontsize=9)
                    ax_whr.grid(True, alpha=0.3)
                    ax_whr.legend(fontsize=8)
                    
                    sim_outdoor = sim_metrics['outdoor_temp_profile']
                    sim_zone = sim_metrics['temp_profile']
                    ep_zone = ep_metrics['temp_profile']
                    
                    ax_temp_env.plot(times_h, sim_outdoor, label='Outdoor Temperature', color='#fdcb6e', linewidth=2, linestyle=':')
                    ax_temp_env.plot(times_h, sim_zone, label='Simplified Zone Temp', color='#0984e3', linewidth=2)
                    ax_temp_env.plot(times_h, ep_zone, label='EnergyPlus Zone Temp', color='#d63031', linewidth=2, linestyle='--')
                    ax_temp_env.set_title('Zone vs. Outdoor Temperature Dynamics', fontsize=11, fontweight='bold')
                    ax_temp_env.set_xlabel('Hour of Day', fontsize=9)
                    ax_temp_env.set_ylabel('Temperature (°C)', fontsize=9)
                    ax_temp_env.grid(True, alpha=0.3)
                    ax_temp_env.legend(fontsize=8)
                    
                    fig_adv.tight_layout()
                    st.session_state.fig_adv = fig_adv
                    plt.close(fig_adv)
                    
            st.pyplot(st.session_state.fig_adv)

st.divider()

# ===== SYSTEM STATUS =====
st.header("System Status")

if results['hot_spots'] > 0:
    st.error(
        f"**Temperature Alert** — {results['hot_spot_percent']:.1f}% of room "
        f"exceeds {results['waste_threshold'] * 9 / 5 + 32:.0f}°F"
    )
    recommendations = []
    if num_air_handlers < 4:
        recommendations.append(f"Increase air handlers from {num_air_handlers} to {num_air_handlers + 1}")
    if rdhx_effectiveness < 0.95:
        recommendations.append(f"Improve RDHX effectiveness (currently {rdhx_effectiveness * 100:.0f}%)")
    if num_heat_exchangers < 2:
        recommendations.append("Add heat exchangers for additional cooling")
    if room_height < 4.0:
        recommendations.append("Increase room height for better air circulation")
    for rec in recommendations:
        st.write(f"- {rec}")
else:
    pue_label = '(Excellent)' if results['pue'] < 1.3 else '(Good)' if results['pue'] < 1.5 else '(Can improve)'
    st.success(
        f"**System Operating Well** — Max temp: {results['T_max'] * 9 / 5 + 32:.1f}°F | "
        f"PUE: {results['pue']:.2f} {pue_label}"
    )

# ===== ADVANCED DETAILS & PHYSICS =====
with st.expander("Advanced Details & Physics", expanded=False):
    adv1, adv2, adv3 = st.columns(3)

    with adv1:
        st.write("**Temperature Profile**")
        st.write(f"- Inlet: {results['T_inlet'] * 9 / 5 + 32:.1f}°F")
        st.write(f"- Room average: {results['T_avg'] * 9 / 5 + 32:.1f}°F")
        st.write(f"- Maximum: {results['T_max'] * 9 / 5 + 32:.1f}°F")
        st.write(f"- Rack exhaust: {results['T_rack_exhaust'] * 9 / 5 + 32:.1f}°F")
        st.write(f"- After RDHX: {results['T_rack_exhaust_after_rdhx'] * 9 / 5 + 32:.1f}°F")

        st.write("")
        st.write("**Airflow**")
        st.write(f"- Total: {results['cfm']:,.0f} CFM")
        st.write(f"- Per handler: {results['cfm_per_handler']:,.0f} CFM")
        st.write(f"- Air changes: {results['ach']:.1f}/hr")

    with adv2:
        st.write("**Building Envelope**")
        st.write(f"- Outdoor: {results['T_outdoor']:.1f}°C ({results['T_outdoor'] * 9 / 5 + 32:.1f}°F)")
        st.write(f"- Wall heat gain: {results['Q_walls_kw']:+.2f} kW")
        st.write(f"- Floor heat loss: -{results['Q_floor_kw']:.2f} kW")
        st.write(f"- Net envelope: {(results['Q_walls_kw'] - results['Q_floor_kw']):+.2f} kW")
        st.write(f"- Thermal capacitance: {results['thermal_capacitance_MJK']:.2f} MJ/K")

        st.write("")
        st.write("**Energy Balance**")
        heat_in = results['Q_total_kw'] + max(results['Q_walls_kw'], 0)
        heat_out = (results['Q_dclc_kw'] + results['Q_rdhx_kw'] + results['Q_hx_removed_kw']
                    + results['Q_remaining_kw'] + results['Q_floor_kw'] - min(results['Q_walls_kw'], 0))
        st.write(f"- Heat in: {heat_in:.1f} kW")
        st.write(f"- Heat out: {heat_out:.1f} kW")
        st.write(f"- IT load: {results['Q_total_kw']:.0f} kW")
        st.write(f"- Total facility: {results['total_facility_power_kw']:.0f} kW")
        st.write(f"- Overhead: {results['cooling_overhead_fraction'] * 100:.1f}%")

    with adv3:
        st.write("**Cooling Infrastructure**")
        st.write(f"- CDU supply: {results['t_supply_known']:.1f}°C")
        st.write(f"- CDU return: {results['t_return_c']:.1f}°C")
        st.write(f"- Water ΔT: {results['delta_t_water']:.1f}°C")
        st.write(f"- Flow: {results['m_dot_liquid_gpm']:.0f} GPM ({results['m_dot_liquid_kgs']:.1f} kg/s)")
        st.write(f"- Liquid heat: {results['Q_liquid_cooling_kw']:.0f} kW")
        st.write(f"- Pump: {results['p_pump_kw']:.1f} kW")
        st.write(f"- Chiller: {results['p_mech_kw']:.0f} kW")

        st.write("")
        st.write("**Physics Equations**")
        st.code(
            "Q = ṁ × Cₚ × ΔT\n"
            "T_return = T_supply + Q / (ṁ × cₚ)\n"
            "P_pump = (ΔP × Q_vol) / η\n"
            "P_mech = Q_rejected / COP\n"
            "T_room = (T_in·ṁCₚ + Q_IT + UA_w·T_out\n"
            "          + UA_f·T_gnd) / (ṁCₚ + UA_w + UA_f)",
            language=None,
        )

# Footer
st.divider()
st.caption("**ATL01 PACE Room Thermal Model** — Hover over info icons for explanations")

# Auto-advance playback — runs after the full page has rendered
if st.session_state.sim_playing and st.session_state.sim_data is not None:
    n_frames = len(st.session_state.sim_data['frame_indices'])
    if st.session_state.sim_frame < n_frames - 1:
        time.sleep(0.05)  # minimal delay for smoothness
        st.session_state.sim_frame += 1
        st.rerun()
    else:
        # Reached the end — stop automatically
        st.session_state.sim_playing = False