# Implementation Plan: Dynamic EnergyPlus Integration & Model Comparison

This plan outlines the code changes and additions required to integrate dynamic EnergyPlus simulations into the main Streamlit application and implement a side-by-side validation comparison between the Python-based simplified model and the EnergyPlus advanced model.

## User Review Required

> [!IMPORTANT]
> **EnergyPlus Local Dependency**: The advanced model requires an EnergyPlus installation (version 25.1.0) on the host machine. We will use the existing automated detection logic in `model/config.py`. If EnergyPlus is not found, the advanced and comparison modes will gracefully show a warning and fall back to the simplified model.

## Proposed Changes

We will modify two main files in the workspace: the IDF generator and the Streamlit dashboard app.

---

### Component 1: IDF Generator Refactoring

We will update the IDF generator to support generating models directly from dynamic inputs (session dictionaries) rather than hardcoded scenario numbers.

#### [MODIFY] [EPlusIDF.py](file:///Users/malvarez66/Documents/GitHub/waste-heat-recovery-model/model/EPlusIDF.py)
- Modify both `SimplifiedIDFGenerator` and `DetailedIDFGenerator` to add a generic method:
  `generate_scenario_from_dict(self, scenario_dict, filename)`
- Update the internal load and scheduling generation so that the detailed ITE server equipment model (`ELECTRICEQUIPMENT:ITE:AIRCOOLED`) supports time-varying jobs dynamically (similar to how the simplified generator maps schedules for Scenario 3). We will generate multiple `ELECTRICEQUIPMENT:ITE:AIRCOOLED` objects corresponding to each job, with its own start, duration, and CPU load schedule.

---

### Component 2: Streamlit Dashboard UI & Backend

We will integrate the simulation wrapper and build the value-to-value comparison layout.

#### [MODIFY] [Data_Center_Model.py](file:///Users/malvarez66/Documents/GitHub/waste-heat-recovery-model/app/Data_Center_Model.py)
- **Engine Selection**: Add sidebar controls allowing the user to select the Simulation Engine:
  - `Simplified (Python Physics)` — runs the current transient lumped solver.
  - `Advanced (EnergyPlus)` — generates and runs the detailed HVAC/ITE E+ model.
- **Dynamic Simulation Execution**:
  - Add a wrapper function `run_eplus_simulation(params)` that:
    1. Converts current Streamlit parameter settings (dimensions, cooling, schedules) into a scenario-like dictionary.
    2. Calls `DetailedIDFGenerator` to write a temporary IDF file (e.g., `model/scenarios/streamlit_run.idf`).
    3. Runs `run_energyplus('streamlit_run.idf')` using a subprocess call.
    4. Parses the generated `.eso` output file using `parse_eso.py` to extract time-series arrays for temperature, cooling rate, ITE power, fan energy, and chiller power.
- **Comparison Feature & Value-to-Value Metrics Table**:
  - Add a new tab/section **"⚖️ Model Comparison"** or a validation overlay button.
  - When clicked, the backend runs both models for the current setup and compiles a value-to-value comparison table.
  - In this comparison table, the **Expected Values** will be defined by the **Simplified (Python)** model, and the **Actual Values** will be defined by the **Advanced (EnergyPlus)** model.
  - We will display the following metrics:
    - **Total Electricity Consumed** (kWh)
    - **Total Cooling Energy Delivered** (kWh)
    - **Average Room Temperature** (°F)
    - **Peak Room Temperature** (°F)
    - **Average PUE**
    - **Peak PUE**
    - **Recovered Waste Heat** (kWh)
  - For each metric, we will display:
    - `Simplified (Expected)`
    - `Advanced (EnergyPlus)`
    - `Absolute Deviation` & `Percentage Deviation`
    - `Status` (e.g., `✅ Pass (<5% error)` or `⚠️ Calibrate (>5% error)`)
- **Overlay Validation Charts**:
  - Create Matplotlib charts overlaying the transient profiles:
    1. **Zone Temp Comparison**: $T_{room}$ (Python) vs. Zone Mean Temperature (EnergyPlus) over 24 hours.
    2. **Cooling Power Comparison**: Total Cooling demand in Python vs. Cooling Coil + Fan Power in EnergyPlus.
    3. **PUE Comparison**: Python PUE vs. EnergyPlus PUE.

---

## Verification Plan

### Automated Tests
We will verify the code changes by running:
- Syntax and import check: `python -m py_compile app/Data_Center_Model.py model/EPlusIDF.py`
- Test run of generator: `python model/EPlusIDF.py --mode detailed --scenario 1`

### Manual Verification
1. Open the updated Streamlit app and verify the new Simulation Engine sidebar selection.
2. Schedule a set of GPU jobs, run the **Simplified** model, and note the results.
3. Switch to **Advanced** mode, run the simulation, and verify that the spinner runs and details are populated from the parsed `.eso` file.
4. Click **Compare Models** and verify that:
   - The comparison table renders correctly, showing Python values as the "Expected" baseline and EnergyPlus values as the validation source.
   - The transient overlay charts (Temperature, Cooling Power, PUE) render side-by-side with clear legends.
