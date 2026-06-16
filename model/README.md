# EnergyPlus IDF Generator for ATL01 Data Center

This directory contains the full pipeline for generating, running, and analyzing EnergyPlus simulations of the ATL01 data center under five different scenarios.

## Prerequisites

| Requirement | Details |
|---|---|
| **EnergyPlus** | Version 25.1.0 - grants `pyenrgyplus` library|
| **eppy** | `pip install eppy` — used by `EPlusIDF.py` for IDF construction |
| **Weather file** | Included in `model/` — `USA_GA_Atlanta-Hartsfield-Jackson.Intl.AP.722190_TMY3.epw` |

---

## Quick Start

### 1. Generate IDF Files

```bash
# Simplified only (default)
python model/EPlusIDF.py

# Detailed only
python model/EPlusIDF.py --mode detailed

# Both simplified and detailed
python model/EPlusIDF.py --mode both

# Single scenario
python model/EPlusIDF.py --mode both --scenario 1
```

This produces 10 IDF files in `model/scenarios/`:

| File | Mode |
|---|---|
| `scenario_N_<Name>_simplified.idf` | Ideal-loads air system |
| `scenario_N_<Name>_detailed.idf`   | PTAC with DX cooling coil |

### 2. Run a Simulation

```bash
python model/run.py <idf_filename>
```

Examples:
```bash
python model/run.py scenario_1_Baseline_Validated_simplified.idf
python model/run.py scenario_1_Baseline_Validated_detailed.idf
```

### 3. Analyze Results

```bash
# List available outputs
python model/parse_eso.py

# Analyze by name or number
python model/parse_eso.py scenario_1_Baseline_Validated_detailed
python model/parse_eso.py 1
```

`parse_eso.py` extracts time-series data from `.eso` files and reports:
- **Zone conditions** — mean air temperature, cooling setpoint
- **ITE equipment** — CPU power, fan power, UPS losses, total heat to zone
- **HVAC performance** — cooling coil capacity, fan power, COP
- **Energy summary** — total ITE heat, cooling delivered, fan energy

---

## Scenarios

### Scenario 1: Baseline (Validated)

Baseline configuration validated against actual ATL01 PACE Room measurements.

| Parameter | Value |
|---|---|
| Room | 15 m × 10 m × 3 m (450 m³) |
| Racks | 60 × 40 kW = **2,400 kW** |
| DCLC effectiveness | 20% |
| RDHX effectiveness | 90% |
| Air handlers | 2 × 155,000 CFM |
| Target temperature | 24.4 °C |

### Scenario 2: Waste Heat Recovery

Same as Scenario 1 with the addition of heat exchangers.

| Parameter | Value |
|---|---|
| Heat exchangers | 2 × 80 kW = **160 kW recoverable** |
| Target temperature | 24.0 °C |

### Scenario 3: Scheduled Mixed Workloads

Time-varying GPU workloads throughout the day.

| Period | Hours | Racks | Power/rack | Total |
|---|---|---|---|---|
| Morning (High) | 08:00–12:00 | 20 | 55 kW | 1,100 kW |
| Afternoon (Medium) | 13:00–16:00 | 15 | 40 kW | 600 kW |
| Overnight (Low) | 22:00–06:00 | 30 | 20 kW | 600 kW |

### Scenario 4: High-Density Upgrade

Increased rack density with enhanced cooling.

| Parameter | Value |
|---|---|
| Racks | 100 × 40 kW = **4,000 kW** |
| DCLC effectiveness | 30% |
| RDHX effectiveness | 95% |
| Air handlers | 3 × 155,000 CFM |
| Target temperature | 25.0 °C |

### Scenario 5: Room Expansion

Doubled room footprint with the same IT load.

| Parameter | Value |
|---|---|
| Room | 20 m × 15 m × 3 m (900 m³) |
| Racks | 60 × 40 kW = 2,400 kW |
| Target temperature | 23.5 °C |

---

## Modeling Approach

### Simplified Mode (Ideal Loads)

- Uses `ZoneHVAC:IdealLoadsAirSystem`
- Automatically sizes to meet the cooling setpoint
- Represents the **combined effect** of liquid cooling and air handlers
- Faster simulation, easier to validate
- Best for thermal load analysis and quick comparisons

### Detailed Mode (PTAC with DX Coil)

- Uses `ZoneHVAC:PackagedTerminalAirConditioner` with a single-speed DX cooling coil
- Models compressor electricity, fan power draw, and COP
- Includes `Sizing:Zone` and `Sizing:System` for auto-sizing
- Models UPS losses as additional zone heat gain (calculated as `1/η − 1` of total IT power, where η = 0.9)
- Uses `ZoneHVAC:EquipmentList` and `ZoneHVAC:EquipmentConnections` for proper node-based airflow
- Thermostat setpoint = `target_temp + 5.0 °C` to model return-air / hot-aisle temperature

> [IMPORTANT]
> The 5 °C offset in the detailed model is intentional. It represents the temperature rise
> through the server racks (supply-air → return-air). The simplified model controls directly
> at the target temperature since it abstracts the airflow path.

### Liquid Cooling Representation

Both modes pre-calculate how much IT heat reaches the zone air:

```
Total IT Power               2,400 kW  (Scenario 1)
 └─ DCLC captures 20%          480 kW   → removed at source
 └─ Remaining                 1,920 kW
     └─ RDHX captures 90%    1,728 kW   → removed via rear-door heat exchangers
     └─ Heat to zone air        192 kW   → what the air-side HVAC must handle
```

---

## Output Files

After a simulation, `model/outputs/<scenario_name>/` contains:

| File | Description |
|---|---|
| `eplusout.err` | Errors, warnings, and completion status |
| `eplusout.eso` | Time-series data (parsed by `parse_eso.py`) |
| `eplusout.mtr` | Meter output |
| `eplustbl.htm` | Summary tables (HTML) |
| `eplustbl.csv` | Summary tables (CSV) |
| `eplusout.end` | Simulation end status |

---

## Customization

### Modifying Scenarios

Edit `config.py` to adjust parameters:

```python
SCENARIO_1 = {
    "name": "Baseline_Validated",
    "room": {
        "length": 15.0,  # meters
        "width": 10.0,
        "height": 3.0,
    },
    "racks": {
        "total_power": 2400000,  # Watts
    },
    "cooling": {
        "dclc_effectiveness": 0.20,
        "rdhx_effectiveness": 0.90,
    },
    "target_temp": 24.4,  # °C
}
```

Then regenerate:
```bash
python model/EPlusIDF.py --mode both
```

### Adding New Scenarios

1. Add a new `SCENARIO_N` dictionary to `config.py`
2. Add the entry to the `SCENARIOS` dict
3. Run the generator

---

## Troubleshooting

| Error | Solution |
|---|---|
| `Could not set IDD file` | Verify EnergyPlus install path in `config.py` |
| `Weather file not found` | Ensure `.epw` file is in `model/` |
| `No "Sizing:Zone" objects` | Use the detailed generator — it includes `Sizing:Zone` |
| `BadEPFieldError` | Field names may differ across EnergyPlus versions — check the I/O Reference |
| `ExpandObjects` warnings | Typically harmless; check `eplusout.err` for fatal errors |

> [!TIP]
> Always check `model/outputs/<scenario>/eplusout.err` after a run.
> A successful simulation ends with `EnergyPlus Completed Successfully`.