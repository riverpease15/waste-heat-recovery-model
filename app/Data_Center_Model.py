import sys
import os

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
with st.expander("ℹ️ How to use this model", expanded=False):
    st.markdown("""
    This model simulates heat flow through a data center using real physics equations.

    **Quick Start:**
    1. Adjust sliders in the sidebar to change room size, equipment, and cooling
    2. Watch how room temperature and energy efficiency respond in real-time
    3. Green metrics = good, Red metrics = need attention

    **Waste Heat Recovery:** Heat exchangers capture heat for reuse (e.g., building heating)
    """)

# Sidebar controls
st.sidebar.header("⚙️ Configuration")

st.sidebar.subheader("📐 Room & Racks")
room_length = st.sidebar.slider("Room Length (m)", 10.0, 40.0, 27.1, 0.1,
                                help="Length affects total room volume and power density")
room_width = st.sidebar.slider("Room Width (m)", 5.0, 30.0, 23.6, 0.1,
                               help="Width affects total room volume and power density")
room_height = st.sidebar.slider("Room Height (m)", 2.5, 8.0, 6.4, 0.1,
                                help="Height affects air circulation and stratification")
num_rows = st.sidebar.slider("Number of Rows", 1, 6, 3, 1,
                             help="Rows of server racks in the room",
                             key="num_rows")
racks_per_row = st.sidebar.slider("Racks per Row", 5, 30, 20, 1,
                                  help="Number of server racks in each row",
                                  key="racks_per_row")

# Initialize session state for scheduled jobs
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

st.sidebar.subheader("❄️ Cooling System")
dclc_effectiveness = st.sidebar.slider("DCLC Effectiveness", 0.0, 0.60, 0.35, 0.05,
                                       help="% of heat captured by cold plates at CPUs/GPUs")
rdhx_effectiveness = st.sidebar.slider("RDHX Effectiveness", 0.0, 0.98, 0.92, 0.02,
                                       help="% of rack exhaust heat captured by rear door exchangers")
num_heat_exchangers = st.sidebar.slider("Waste Heat Exchangers", 0, 2, 0, 1,
                                        help="Heat exchangers that capture waste heat for reuse")
hx_capacity_kw = st.sidebar.slider("HX Capacity (kW each)", 30.0, 150.0, 60.0, 10.0,
                                   help="Maximum heat each exchanger can capture")
with st.sidebar.expander("CDU & Pump Details"):
    cdu_flow_gpm = st.slider("Flow Rate per CDU (GPM)", 100.0, 200.0, 150.0, 5.0,
                             help="Water flow rate per CDU")
    num_cdus = st.slider("Number of CDUs", 1, 6, 3, 1,
                         help="Cooling Distribution Units")
    delta_p_kpa = st.slider("Loop Pressure Drop (kPa)", 100.0, 350.0, 200.0, 10.0,
                            help="Pressure the pump must overcome")
    pump_eta = st.slider("Pump Efficiency", 0.60, 0.85, 0.75, 0.05,
                         help="Pump mechanical efficiency")
    cop = st.slider("Chiller COP", 3.0, 6.0, 4.0, 0.5,
                    help="Chiller Coefficient of Performance")

st.sidebar.subheader("💨 Air Handling")
num_air_handlers = st.sidebar.slider("Air Handlers", 0, 4, 2, 1,
                                     help="Number of air handling units")
cfm_per_handler = st.sidebar.slider("Airflow per Handler (CFM)", 20000.0, 250000.0, 155000.0, 5000.0,
                                    help="Cubic Feet per Minute per handler")
inlet_temp_c = st.sidebar.slider("Inlet Temperature (°C)", 18.0, 28.0, 23.3, 0.5,
                                 help="Temperature of cooling air entering the room")
waste_threshold_c = st.sidebar.slider("Hot Spot Threshold (°C)", 25.0, 35.0, 30.0, 1.0,
                                      help="Temperature above which areas are flagged as too hot")

# 24-hour outdoor temperature profile for typical Atlanta July day
# T_outdoor(t) = 26.5 + 5.5 × sin(2π(t - 9)/24)
# Low ~21°C at 5AM, high ~32°C at 3PM
outdoor_temp_profile = {
    hour: 26.5 + 5.5 * np.sin(2 * np.pi * (hour - 9) / 24)
    for hour in np.arange(0, 24, 0.5)
}
# Default to peak hour (3PM) for steady-state calculation
time_of_day = 15.0

# Simulation state invalidation — clear sim_data if any input has changed
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

# # For now, use default rack power for the thermal calculation below
# # This will be replaced with scheduled job data when simulation runs
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
    - Exterior wall heat gain/loss: Q_walls = U × A × (T_outdoor - T_room)
    - Floor heat loss to ground: Q_floor = U × A × (T_room - T_ground)
    - Outdoor temperature follows sinusoidal 24h profile for Atlanta July

    Physics:
    - Q = m_dot × Cp × ΔT (heat transfer equation)
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
        # Dynamic mode: apply per-rack power from the simulation schedule.
        # Any rack index beyond the array length stays at IDLE_RACK_KW.
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
    UA_WALLS = 0.19 * 347  # W/K — two exterior walls, 2 × 27.1m × 6.4m = 347 m²
    UA_FLOOR = 0.5 * 640  # W/K — floor slab, 640 m²
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
    active = ((times_h[:, None] >= j_starts[None, :])
              & (times_h[:, None] < j_ends[None, :])
              & (times_h[:, None] < 24.0))

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

    UA_WALLS = 0.19 * 347
    UA_FLOOR = 0.50 * 640
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
    T_room_arr[0] = float(inlet_temp_c)
    for k in range(n_steps - 1):
        T_room_arr[k + 1] = T_ss_arr[k] + (T_room_arr[k] - T_ss_arr[k]) * decay[k] \
            if np.isscalar(decay) is False else \
            T_ss_arr[k] + (T_room_arr[k] - T_ss_arr[k]) * decay
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
play_button = st.button("▶️ Run Simulation", type="primary", use_container_width=True,
                        disabled=len(st.session_state.scheduled_jobs) == 0)
should_run = play_button or st.session_state.auto_run_sim
if should_run:
    st.session_state.auto_run_sim = False
    with st.spinner("Building simulation…"):
        st.session_state.sim_data = build_sim_data(
            st.session_state.scheduled_jobs,
            room_length, room_width, room_height,
            num_rows, racks_per_row,
            dclc_effectiveness, rdhx_effectiveness,
            num_heat_exchangers, hx_capacity_kw,
            num_air_handlers, cfm_per_handler,
            inlet_temp_c,
        )
    st.session_state.tou_costs = calculate_tou_cost(st.session_state.sim_data)
    st.session_state.sim_frame = 0
    st.session_state.sim_fingerprint = _current_fingerprint
    st.session_state.sim_stale = False
    st.session_state.scroll_to_viz = True

st.divider()


def plot_thermal_field(results):
    """Create thermal visualization"""

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Convert fields to Fahrenheit for display
    T_f = results['T'] * 9 / 5 + 32
    T_inlet_f = results['T_inlet'] * 9 / 5 + 32
    waste_threshold_f = results['waste_threshold'] * 9 / 5 + 32

    # === THERMAL MAP (°F) ===
    im1 = ax1.contourf(results['X'], results['Y'], T_f,
                       levels=30, cmap='RdYlBu_r',
                       vmin=T_inlet_f, vmax=waste_threshold_f)
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
    st.warning("⚠️ Settings changed — simulation cleared. Press **▶️ Run Simulation** to update.")
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

tab_hf, tab_env, tab_ci = st.tabs(["Heat Flow", "Building Envelope", "Cooling Infrastructure"])

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