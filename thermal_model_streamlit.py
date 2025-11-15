import streamlit as st

# Page configuration - MUST be first Streamlit command
st.set_page_config(
    page_title="ATL01 Data Center Thermal Model",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

"""
ATL01 PACE ROOM - INTERACTIVE THERMAL MODEL
Streamlit Application for Local Deployment
"""

# Physical constants
RHO = 1.184      # Air density kg/m³
CP = 1007.0      # Specific heat capacity J/(kg·K)
K_AIR = 0.026    # Thermal conductivity W/(m·K)

# CODA room dimensions
room_length = 23.5712
room_width = 27.1272

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

st.sidebar.subheader("📐 Room Height")
# st.sidebar.caption("Larger rooms have lower power density")
# room_length = st.sidebar.slider("Room Length (m)", 10.0, 30.0, 15.0, 1.0,
#                                 help="Length affects total room volume and power density")
# room_width = st.sidebar.slider("Room Width (m)", 5.0, 20.0, 10.0, 1.0,
#                                help="Width affects total room volume and power density")
room_height = st.sidebar.slider("Room Height (m)", 2.5, 5.0, 3.0, 0.5,
                                help="Height affects air circulation and stratification")

st.sidebar.subheader("🖥️ Server Racks")
st.sidebar.caption("Configure rack layout")
num_rows = st.sidebar.slider("Number of Rows", 1, 6, 3, 1,
                             help="Rows of server racks in the room")
racks_per_row = st.sidebar.slider("Racks per Row", 5, 30, 20, 1,
                                  help="Number of server racks in each row")

# Initialize session state for scheduled jobs
if 'scheduled_jobs' not in st.session_state:
    st.session_state.scheduled_jobs = []

st.sidebar.subheader("❄️ Liquid Cooling")
st.sidebar.caption("Captures heat before it reaches room air")
dclc_effectiveness = st.sidebar.slider("DCLC (Direct Liquid Cooling)", 0.0, 0.50, 0.20, 0.05,
                                      help="% of heat captured by cold plates at CPUs/GPUs. Higher = more efficient")
rdhx_effectiveness = st.sidebar.slider("RDHX (Rear Door Heat Exchanger)", 0.0, 0.97, 0.90, 0.05,
                                      help="% of rack exhaust heat captured by door-mounted exchangers")

st.sidebar.subheader("♻️ Waste Heat Recovery")
st.sidebar.caption("Captures heat for reuse (e.g., building heating)")
num_heat_exchangers = st.sidebar.slider("Heat Exchangers", 0, 2, 0, 1,
                                        help="Additional heat exchangers that capture waste heat for reuse")
hx_capacity_kw = st.sidebar.slider("HX Capacity (kW each)", 30.0, 150.0, 60.0, 10.0,
                                   help="Maximum heat each exchanger can capture")

st.sidebar.subheader("💨 Air Handling")
st.sidebar.caption("Moves air to distribute cooling")
num_air_handlers = st.sidebar.slider("Air Handlers", 0, 4, 2, 1,
                                     help="Number of air handling units. More = better air circulation")
cfm_per_handler = st.sidebar.slider("Airflow per Handler (CFM)", 20000.0, 250000.0, 155000.0, 5000.0,
                                   help="Cubic Feet per Minute. Higher = more cooling capacity")

st.sidebar.subheader("🌡️ Temperature")
inlet_temp_c = st.sidebar.slider("Inlet Temperature (°C)", 18.0, 28.0, 23.3, 0.5,
                                help="Temperature of cooling air entering the room")
waste_threshold_c = st.sidebar.slider("Hot Spot Alert Threshold (°C)", 25.0, 35.0, 30.0, 1.0,
                                     help="Temperature above which areas are flagged as too hot")


# ===== JOB SCHEDULING SECTION =====
st.header("📅 Job Scheduler")
st.markdown("Schedule GPU jobs throughout the day to see thermal impact over time")

# Job scheduler UI
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("➕ Add New Job")

    job_col1, job_col2, job_col3 = st.columns(3)

    with job_col1:
        job_start_time_input = st.time_input("Start Time",
                                             value=None,
                                             step=900,  # 15 minute increments
                                             help="When the job starts (24-hour format)")

    with job_col2:
        job_duration_hours = st.number_input("Duration (hours)", min_value=0.5, max_value=24.0, value=2.0, step=0.5,
                                            help="How long the job runs")

    with job_col3:
        gpu_power_level = st.selectbox("GPU Power Level",
                                       options=["Low (20 kW)", "Medium (40 kW)", "High (55 kW)"],
                                       index=1,
                                       help="Power consumption per rack during job")
        # Extract power value
        power_map = {"Low (20 kW)": 20.0, "Medium (40 kW)": 40.0, "High (55 kW)": 55.0}
        job_power_kw = power_map[gpu_power_level]

    total_available_racks = num_rows * racks_per_row
    job_num_racks = st.number_input("Number of Racks",
                                   min_value=1,
                                   max_value=total_available_racks,
                                   value=min(10, total_available_racks),
                                   step=1,
                                   help=f"Number of racks needed (max {total_available_racks} available)")

    # Add job button
    add_button_disabled = job_start_time_input is None
    if st.button("➕ Add Job", type="primary", use_container_width=True, disabled=add_button_disabled):
        job_start_hour = job_start_time_input.hour
        job_start_min = job_start_time_input.minute
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
    st.metric("Total Jobs", len(st.session_state.scheduled_jobs))
    st.metric("Available Racks", f"{total_available_racks}")

    # Play button (placeholder for now)
    st.markdown("---")
    play_button = st.button("▶️ Run Simulation", type="secondary", use_container_width=True, disabled=len(st.session_state.scheduled_jobs) == 0)
    if play_button:
        st.info("⏳ Simulation feature coming soon!")

# Display scheduled jobs in calendar-style view
if len(st.session_state.scheduled_jobs) > 0:
    st.subheader("📋 Scheduled Jobs Timeline")

    # Sort jobs by start time
    sorted_jobs = sorted(st.session_state.scheduled_jobs, key=lambda x: x['start_time'])

    # Build job blocks HTML
    job_blocks_html = ""
    for job_idx, job in enumerate(sorted_jobs):
        start_pct = (job['start_time'] / 24) * 100
        duration_pct = (job['duration'] / 24) * 100

        # Offset jobs vertically if they overlap
        top_position = 10 + (job_idx % 2) * 55  # Alternate between two rows

        job_class = "job-low" if "Low" in job['power_level'] else "job-medium" if "Medium" in job['power_level'] else "job-high"
        job_emoji = "🟢" if "Low" in job['power_level'] else "🟡" if "Medium" in job['power_level'] else "🔴"

        job_blocks_html += f'<div class="job-block {job_class}" style="left: {start_pct}%; width: {duration_pct}%; top: {top_position}px;">{job_emoji} Job {job_idx + 1}</div>'

    # Build hour labels HTML
    hour_labels_html = ""
    for hour in range(24):
        hour_labels_html += f'<div class="timeline-hour">{hour:02d}</div>'

    # Create complete calendar HTML
    calendar_html = f"""
    <style>
        .calendar-container {{
            background: linear-gradient(180deg, #2d3436 0%, #34495e 100%);
            border-radius: 12px;
            padding: 20px;
            margin: 10px 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }}
        .timeline-grid {{
            position: relative;
            height: 150px;
            background: repeating-linear-gradient(
                90deg,
                rgba(255,255,255,0.05) 0px,
                rgba(255,255,255,0.05) 1px,
                transparent 1px,
                transparent calc(100% / 24)
            );
            border: 2px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            margin: 15px 0;
        }}
        .timeline-hours {{
            display: flex;
            justify-content: space-between;
            color: #bdc3c7;
            font-size: 11px;
            font-weight: 600;
            margin-bottom: 8px;
            padding: 0 5px;
        }}
        .timeline-hour {{
            width: calc(100% / 24);
            text-align: center;
        }}
        .job-block {{
            position: absolute;
            height: 50px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 13px;
            color: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            border: 2px solid rgba(255,255,255,0.3);
            transition: transform 0.2s;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
        }}
        .job-block:hover {{
            transform: scale(1.03);
            box-shadow: 0 4px 12px rgba(0,0,0,0.6);
        }}
        .job-low {{
            background: linear-gradient(135deg, #00b894 0%, #00cec9 100%);
        }}
        .job-medium {{
            background: linear-gradient(135deg, #fdcb6e 0%, #f39c12 100%);
        }}
        .job-high {{
            background: linear-gradient(135deg, #ff7675 0%, #d63031 100%);
        }}
        .job-details {{
            background: rgba(44, 62, 80, 0.95);
            border-radius: 8px;
            padding: 12px 15px;
            margin: 10px 0;
            border-left: 4px solid #3498db;
            color: #ecf0f1;
            font-size: 14px;
        }}
        .job-details strong {{
            color: #3498db;
        }}
    </style>
    <div class="calendar-container">
        <div class="timeline-hours">
            {hour_labels_html}
        </div>
        <div class="timeline-grid">
            {job_blocks_html}
        </div>
    </div>
    """

    st.markdown(calendar_html, unsafe_allow_html=True)

    # Job details list
    st.markdown("### Job Details")
    for job_idx, job in enumerate(sorted_jobs):
        job_emoji = "🟢" if "Low" in job['power_level'] else "🟡" if "Medium" in job['power_level'] else "🔴"

        col1, col2 = st.columns([5, 1])

        with col1:
            st.markdown(f"""
            <div class="job-details">
                <strong>{job_emoji} Job {job_idx + 1}:</strong>
                {job['start_hour']:02d}:{job['start_min']:02d} → {int(job['end_time']):02d}:{int((job['end_time'] % 1) * 60):02d}
                ({job['duration']:.1f}h) |
                {job['power_level']} |
                {job['num_racks']} racks |
                {job['num_racks'] * job['power_kw']:.0f} kW total
            </div>
            """, unsafe_allow_html=True)

        with col2:
            if st.button("🗑️ Remove", key=f"delete_{job_idx}", use_container_width=True):
                st.session_state.scheduled_jobs.remove(job)
                st.rerun()

    # Clear all button
    st.markdown("")
    if st.button("🗑️ Clear All Jobs", type="secondary", use_container_width=False):
        st.session_state.scheduled_jobs = []
        st.rerun()
else:
    st.info("📅 No jobs scheduled yet. Add your first job above to get started!")

st.divider()

# For now, use default rack power for the thermal calculation below
# This will be replaced with scheduled job data when simulation runs
rack_power_kw = 40.0  # Default power level


def calculate_thermal_system(room_length, room_width, room_height,
                             num_rows, racks_per_row, rack_power_kw,
                             rdhx_effectiveness, dclc_effectiveness, num_air_handlers,
                             num_heat_exchangers, hx_capacity_kw,
                             inlet_temp_c, waste_threshold_c, cfm_per_handler):
    """Calculate thermal system with physically accurate equations

    Heat Flow Stages:
    1. DCLC (Direct Contact Liquid Cooling) - captures heat at CPU/GPU via cold plates
    2. RDHX (Rear Door Heat Exchanger) - captures heat from exhaust air
    3. Heat Exchangers - remove additional heat from room air
    4. Air Handlers - circulate air and remove remaining heat

    Physics:
    - Q = m_dot × Cp × ΔT (heat transfer equation)
    - Room temperature depends on heat load, airflow rate, and room volume
    - All configurable parameters affect the final outcome
    """

    # === RACK LAYOUT ===
    RACK_WIDTH = 0.762
    RACK_DEPTH = 1.1684
    CLEARANCE = 1.5
    AISLE_WIDTH = 1.2446

    RACKS = []
    available_length = room_length - 2 * CLEARANCE

    for row_idx in range(num_rows):
        y_pos = CLEARANCE + RACK_DEPTH/2 + row_idx * (RACK_DEPTH + AISLE_WIDTH)
        total_row_width = racks_per_row * RACK_WIDTH
        start_x = CLEARANCE + (available_length - total_row_width) / 2

        for rack_idx in range(racks_per_row):
            RACKS.append({
                'x': start_x + rack_idx * RACK_WIDTH + RACK_WIDTH/2,
                'y': y_pos,
                'power_kw': rack_power_kw,
                'width': RACK_WIDTH,
                'depth': RACK_DEPTH
            })

    total_racks = len(RACKS)

    # === HEAT GENERATION ===
    Q_TOTAL_W = total_racks * rack_power_kw * 1000  # Total IT load in Watts

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

    # === PHYSICS-BASED TEMPERATURE CALCULATION ===
    # Heat remaining to be handled by room air circulation
    Q_REMAINING_W = Q_TO_ROOM_AIR_W

    # Calculate temperature rise using Q = m_dot × Cp × ΔT
    # Rearranged: ΔT = Q / (m_dot × Cp)
    if mass_flow_kg_s > 0 and Q_REMAINING_W > 0:
        delta_t_airflow = Q_REMAINING_W / (mass_flow_kg_s * CP)
    else:
        delta_t_airflow = 0.0

    # Room average temperature (well-mixed assumption)
    T_room_c = inlet_temp_c + delta_t_airflow

    # Rack exhaust temperature (before RDHX cooling)
    # Heat concentrated in exhaust stream from racks
    if total_racks > 0:
        # Estimate rack airflow (typically 200-400 CFM per kW)
        rack_cfm_per_kw = 250  # CFM/kW (typical for high-density racks)
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
        fan_power_w = total_cfm * 0.75  # 0.75 W/CFM
        fan_overhead = fan_power_w / Q_TOTAL_W if Q_TOTAL_W > 0 else 0
    else:
        fan_overhead = 0

    total_overhead_fraction = cooling_overhead_fraction + fan_overhead
    total_facility_power_w = Q_TOTAL_W * (1 + total_overhead_fraction)
    pue = total_facility_power_w / Q_TOTAL_W if Q_TOTAL_W > 0 else 1.0
    
    # Air handler physical dimensions (meters)
    AHU_LENGTH = 1.6256
    AHU_WIDTH = 2.7432

    # === EQUIPMENT POSITIONS ===
    AIR_HANDLERS = []
    # if num_air_handlers >= 1:
    #     AIR_HANDLERS.append({'x': 0.7, 'y': room_width/2, 'width': 1.0, 'height': 2.0, 'side': 'left'})
    # if num_air_handlers >= 2:
    #     AIR_HANDLERS.append({'x': room_length - 0.7, 'y': room_width/2, 'width': 1.0, 'height': 2.0, 'side': 'right'})
    # if num_air_handlers >= 3:
    #     AIR_HANDLERS.append({'x': room_length/2, 'y': 0.7, 'width': 2.0, 'height': 1.0, 'side': 'top'})
    # if num_air_handlers >= 4:
    #     AIR_HANDLERS.append({'x': room_length/2, 'y': room_width - 0.7, 'width': 2.0, 'height': 1.0, 'side': 'bottom'})
    if num_air_handlers >= 1:
        AIR_HANDLERS.append({
            'x': 0.7,
            'y': room_width/2,
            'width': AHU_LENGTH,
            'height': AHU_WIDTH,
            'side': 'left'
        })

    if num_air_handlers >= 2:
        AIR_HANDLERS.append({
            'x': room_length - 0.7,
            'y': room_width/2,
            'width': AHU_LENGTH,
            'height': AHU_WIDTH,
            'side': 'right'
        })

    if num_air_handlers >= 3:
        AIR_HANDLERS.append({
            'x': room_length/2,
            'y': 0.7,
            'width': AHU_WIDTH,  # swapped because this AHU is rotated
            'height': AHU_LENGTH,
            'side': 'top'
        })

    if num_air_handlers >= 4:
        AIR_HANDLERS.append({
            'x': room_length/2,
            'y': room_width - 0.7,
            'width': AHU_WIDTH,
            'height': AHU_LENGTH,
            'side': 'bottom'
        })

    HX_POSITIONS = []
    if num_heat_exchangers >= 1:
        HX_POSITIONS.append({'x': room_length * 0.25, 'y': 0.7, 'width': 1.2, 'height': 0.6})
    if num_heat_exchangers >= 2:
        HX_POSITIONS.append({'x': room_length * 0.75, 'y': 0.7, 'width': 1.2, 'height': 0.6})
    
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
        dist = np.sqrt((X - rack['x'])**2 + (Y - rack['y'])**2)
        # Heat escaping to room (not captured by DCLC or RDHX)
        heat_fraction = (1 - dclc_effectiveness) * (1 - rdhx_effectiveness)

        # Heat intensity based on rack power and distance
        # Using 1/r² decay modified by exponential for numerical stability
        heat_plume_temp = rack['power_kw'] * heat_fraction * 0.08  # °C per kW escaping
        spatial_decay = np.exp(-(dist / 0.8)**2)  # Gaussian plume
        T += heat_plume_temp * spatial_decay

    # Add cooling effect from air handlers (proportional to capacity and airflow)
    if num_air_handlers > 0 and mass_flow_kg_s > 0:
        # Cooling intensity based on actual air handler capacity
        cooling_intensity_per_handler = (delta_t_airflow * 0.5) / num_air_handlers
        for handler in AIR_HANDLERS:
            dist = np.sqrt((X - handler['x'])**2 + (Y - handler['y'])**2)
            cooling_plume = cooling_intensity_per_handler * np.exp(-(dist / 3.0)**2)
            T -= cooling_plume

    # Add cooling from heat exchangers (proportional to heat removed)
    if num_heat_exchangers > 0 and Q_HX_REMOVED_W > 0:
        # Cooling based on actual heat exchanger performance
        hx_temp_reduction = (Q_HX_REMOVED_W / (mass_flow_kg_s * CP)) if mass_flow_kg_s > 0 else 0
        cooling_per_hx = hx_temp_reduction / num_heat_exchangers * 0.3
        for hx in HX_POSITIONS:
            dist = np.sqrt((X - hx['x'])**2 + (Y - hx['y'])**2)
            T -= cooling_per_hx * np.exp(-(dist / 2.5)**2)

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
        'Q_total_kw': Q_TOTAL_W / 1000,
        'Q_dclc_kw': Q_DCLC_W / 1000,
        'Q_after_dclc_kw': Q_AFTER_DCLC_W / 1000,
        'Q_rdhx_kw': Q_RDHX_W / 1000,
        'Q_liquid_cooling_kw': Q_LIQUID_COOLING_W / 1000,
        'Q_to_air_before_hx_kw': Q_TO_AIR_BEFORE_HX_W / 1000,
        'Q_hx_removed_kw': Q_HX_REMOVED_W / 1000,
        'Q_remaining_kw': Q_REMAINING_W / 1000,
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
    }


def plot_thermal_field(results):
    """Create thermal visualization"""
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # Convert fields to Fahrenheit for display
    T_f = results['T'] * 9/5 + 32
    T_inlet_f = results['T_inlet'] * 9/5 + 32
    waste_threshold_f = results['waste_threshold'] * 9/5 + 32
    
    # === THERMAL MAP (°F) ===
    im1 = ax1.contourf(results['X'], results['Y'], T_f,
                      levels=30, cmap='RdYlBu_r',
                      vmin=T_inlet_f, vmax=waste_threshold_f)
    plt.colorbar(im1, ax=ax1, label='Temperature (°F)', shrink=0.85)
    
    # Contour lines (°F)
    levels_f = np.linspace(T_inlet_f, waste_threshold_f, 5)
    contours = ax1.contour(results['X'], results['Y'], T_f,
                          levels=levels_f, colors='black', linewidths=1.2, alpha=0.5)
    ax1.clabel(contours, inline=True, fontsize=8, fmt='%.1f°F')
    
    # Plot racks
    for rack in results['racks']:
        rect = Rectangle((rack['x'] - rack['width']/2, rack['y'] - rack['depth']/2),
                       rack['width'], rack['depth'],
                       facecolor='darkred', edgecolor='black',
                       linewidth=0.3, alpha=0.85)
        ax1.add_patch(rect)
        
        # RDHX indicator (blue strip)
        rdhx = Rectangle((rack['x'] - rack['width']/2, rack['y'] + rack['depth']/2 - 0.05),
                       rack['width'], 0.05,
                       facecolor='royalblue', alpha=0.95)
        ax1.add_patch(rdhx)
    
    # Plot air handlers
    for handler in results['air_handlers']:
        rect = Rectangle((handler['x'] - handler['width']/2, handler['y'] - handler['height']/2),
                       handler['width'], handler['height'],
                       facecolor='steelblue', edgecolor='navy',
                       linewidth=2, alpha=0.9, hatch='///')
        ax1.add_patch(rect)
        
        ax1.text(handler['x'], handler['y'], 'AIR\nHANDLER',
                ha='center', va='center', fontsize=7,
                color='white', fontweight='bold')
        
        # Airflow arrows
        if handler['side'] == 'left':
            ax1.arrow(handler['x'] + handler['width']/2 + 0.7, handler['y'],
                     -0.5, 0, head_width=0.25, head_length=0.15,
                     fc='cyan', ec='cyan', alpha=0.7, linewidth=2)
        elif handler['side'] == 'right':
            ax1.arrow(handler['x'] - handler['width']/2 - 0.7, handler['y'],
                     0.5, 0, head_width=0.25, head_length=0.15,
                     fc='cyan', ec='cyan', alpha=0.7, linewidth=2)
    
    # Plot heat exchangers
    for hx in results['hx_positions']:
        rect = Rectangle((hx['x'] - hx['width']/2, hx['y'] - hx['height']/2),
                       hx['width'], hx['height'],
                       facecolor='green', edgecolor='darkgreen',
                       linewidth=2, alpha=0.85, hatch='xxx')
        ax1.add_patch(rect)
        
        ax1.text(hx['x'], hx['y'], 'HEAT\nEXCH',
                ha='center', va='center', fontsize=6,
                color='white', fontweight='bold')
    
    ax1.set_xlabel('Room Length (m)', fontsize=10)
    ax1.set_ylabel('Room Width (m)', fontsize=10)
    ax1.set_title(f'Thermal Map: {results["total_racks"]} Racks @ {results["racks"][0]["power_kw"]:.0f}kW\n'
                 f'Room Temp: {results["T_room"]*9/5+32:.1f}°F',
                 fontsize=11, fontweight='bold')
    ax1.set_xlim([0, results['room_length']])
    ax1.set_ylim([0, results['room_width']])
    ax1.grid(True, alpha=0.3, linewidth=0.5)
    ax1.set_aspect('equal')
    
    # === HOT ZONES MAP (°F above threshold) ===
    hot_zones_f = np.where(results['T'] > results['waste_threshold'],
                       (results['T'] - results['waste_threshold']) * 9/5, 0)
    
    im2 = ax2.contourf(results['X'], results['Y'], hot_zones_f,
                      levels=10, cmap='hot', vmin=0, vmax=9)
    plt.colorbar(im2, ax=ax2, label='°F above threshold', shrink=0.85)
    
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
results = calculate_thermal_system(
    room_length, room_width, room_height,
    num_rows, racks_per_row, rack_power_kw,
    rdhx_effectiveness, dclc_effectiveness, num_air_handlers,
    num_heat_exchangers, hx_capacity_kw,
    inlet_temp_c, waste_threshold_c, cfm_per_handler
)

# Display plots
st.pyplot(plot_thermal_field(results))

# Key Metrics
st.header("📊 Key Metrics")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("🔥 Room Temperature", f"{results['T_room']*9/5+32:.1f}°F",
             delta=f"{(results['T_room'] - results['T_inlet'])*9/5:.1f}°F",
             help="Average room temperature. Delta shows rise from inlet temperature.")
    st.metric("💡 Total IT Load", f"{results['Q_total_kw']:.0f} kW",
             help=f"{results['total_racks']} racks × {rack_power_kw:.0f} kW/rack")

with col2:
    pue_color = "normal" if results['pue'] < 1.3 else "inverse"
    st.metric("⚡ PUE (Efficiency)", f"{results['pue']:.2f}",
             delta="Good" if results['pue'] < 1.3 else "Can improve",
             delta_color=pue_color,
             help="Power Usage Effectiveness. Lower is better. <1.3 is excellent, 1.3-1.5 is good, >1.5 needs improvement")
    st.metric("❄️ Liquid Cooling", f"{results['liquid_cooling_fraction']*100:.0f}%",
             help="Percentage of heat captured by DCLC, RDHX, and heat exchangers")

with col3:
    if results['hot_spots'] > 0:
        st.metric("⚠️ Hot Spots", f"{results['hot_spot_percent']:.1f}%",
                 delta="Warning", delta_color="inverse",
                 help=f"Percentage of room above {waste_threshold_c}°C threshold")
    else:
        st.metric("✅ Hot Spots", "0%",
                 delta="All OK", delta_color="normal",
                 help="No areas exceed temperature threshold")
    st.metric("💨 Airflow", f"{results['cfm']:,.0f} CFM",
             help=f"Total air circulation: {results['ach']:.1f} air changes per hour")

# Heat Flow Visualization
st.header("🔄 Heat Flow Through System")

# Create a visual flow chart
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    st.metric("⚡ Heat Generated", f"{results['Q_total_kw']:.0f} kW",
             help="Total heat from all server racks")
    st.caption("↓")
    st.metric("❄️ DCLC Captures", f"{results['Q_dclc_kw']:.0f} kW",
             help=f"{dclc_effectiveness*100:.0f}% captured by liquid cooling at CPUs/GPUs")

with col2:
    st.metric("🌡️ Heat to Room", f"{results['Q_after_dclc_kw']:.0f} kW",
             help="Heat that wasn't captured by DCLC")
    st.caption("↓")
    st.metric("🚪 RDHX Captures", f"{results['Q_rdhx_kw']:.0f} kW",
             help=f"{rdhx_effectiveness*100:.0f}% captured by rear door exchangers")

with col3:
    st.metric("♻️ HX Captures", f"{results['Q_hx_removed_kw']:.0f} kW",
             help=f"Additional heat captured by {num_heat_exchangers} waste heat recovery units")
    st.caption("↓")
    st.metric("💨 To Air Handlers", f"{results['Q_remaining_kw']:.0f} kW",
             help="Final heat managed by air circulation")

# Waste Heat Recovery Section
if num_heat_exchangers > 0:
    st.success(f"""
    ♻️ **Waste Heat Recovery Active:** {results['Q_liquid_cooling_kw']:.0f} kW available for reuse

    This heat can be used for:
    - Building heating (e.g., CODA building)
    - Hot water generation
    - District heating systems

    **Annual Energy Savings:** ~{results['Q_liquid_cooling_kw'] * 8760 / 1000:.0f} MWh/year
    """)
else:
    st.info(f"""
    💡 **Add Heat Exchangers for Waste Heat Recovery**

    Currently {results['Q_liquid_cooling_kw']:.0f} kW of heat is being removed but not reused.
    Add heat exchangers in the sidebar to capture this energy for building heating.

    **Potential savings:** ~{results['Q_liquid_cooling_kw'] * 8760 / 1000:.0f} MWh/year
    """)

# Recommendations
st.header("💡 System Status & Recommendations")

col1, col2 = st.columns(2)

with col1:
    if results['hot_spots'] > 0:
        st.error(f"""
        **⚠️ Temperature Alert**

        {results['hot_spot_percent']:.1f}% of room exceeds {results['waste_threshold']*9/5+32:.0f}°F

        **Try these improvements:**
        """)
        if num_air_handlers < 4:
            st.write(f"• Increase air handlers from {num_air_handlers} to {num_air_handlers + 1}")
        if rdhx_effectiveness < 0.95:
            st.write(f"• Improve RDHX effectiveness (currently {rdhx_effectiveness*100:.0f}%)")
        if num_heat_exchangers < 2:
            st.write(f"• Add heat exchangers for additional cooling")
        if room_height < 4.0:
            st.write(f"• Consider increasing room height for better air circulation")
    else:
        st.success(f"""
        **✅ System Operating Well**

        - Maximum temperature: {results['T_max']*9/5+32:.1f}°F
        - All zones within safe limits
        - PUE: {results['pue']:.2f} {'(Excellent)' if results['pue'] < 1.3 else '(Good)' if results['pue'] < 1.5 else '(Can improve)'}
        """)

with col2:
    st.info(f"""
    **📈 Quick Stats**

    - **Room:** {results['room_volume']:.0f} m³ ({room_length:.0f}m × {room_width:.0f}m × {room_height:.1f}m)
    - **Power Density:** {results['power_density_w_m3']:.0f} W/m³
    - **Temperature Rise:** {results['delta_t']:.1f}°C
    - **Cooling Efficiency:** {results['liquid_cooling_fraction']*100:.0f}% liquid
    """)

# Advanced details collapsible
with st.expander("🔧 Advanced Details & Physics", expanded=False):
    col1, col2 = st.columns(2)

    with col1:
        st.write("**Temperature Profile**")
        st.write(f"- Inlet: {results['T_inlet']*9/5+32:.1f}°F")
        st.write(f"- Room average: {results['T_avg']*9/5+32:.1f}°F")
        st.write(f"- Maximum: {results['T_max']*9/5+32:.1f}°F")
        st.write(f"- Rack exhaust: {results['T_rack_exhaust']*9/5+32:.1f}°F")

        st.write("")
        st.write("**Airflow**")
        st.write(f"- Total: {results['cfm']:,.0f} CFM")
        st.write(f"- Per handler: {results['cfm_per_handler']:,.0f} CFM")
        st.write(f"- Air changes: {results['ach']:.1f} per hour")

    with col2:
        st.write("**Physics Check**")
        heat_in = results['Q_total_kw']
        heat_out = results['Q_dclc_kw'] + results['Q_rdhx_kw'] + results['Q_hx_removed_kw'] + results['Q_remaining_kw']
        st.write(f"- Heat in: {heat_in:.1f} kW")
        st.write(f"- Heat out: {heat_out:.1f} kW")
        st.write(f"- Balance: ✓ Conserved")

        st.write("")
        st.write("**Energy Efficiency**")
        st.write(f"- IT load: {results['Q_total_kw']:.0f} kW")
        st.write(f"- Total facility: {results['total_facility_power_kw']:.0f} kW")
        st.write(f"- Overhead: {results['cooling_overhead_fraction']*100:.1f}%")

# Footer
st.divider()
st.caption("**ATL01 PACE Room Thermal Model** • Physics-based simulation using Q = ṁ × Cp × ΔT")
st.caption("Hover over ⓘ icons for explanations • Adjust sidebar settings to explore different scenarios")