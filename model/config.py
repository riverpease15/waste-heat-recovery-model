"""
Configuration parameters for EnergyPlus IDF generation
Based on README scenarios for ATL01 Data Center
"""

import os
import platform
from pathlib import Path

def get_energyplus_path():
    system = platform.system()
    
    if system == "Darwin":
        default_path = "/Applications/EnergyPlus-25-1-0"
        if os.path.exists(default_path):
            return default_path
        
        apps_dir = Path("/Applications")
        if apps_dir.exists():
            energyplus_dirs = sorted(apps_dir.glob("EnergyPlus-*"), reverse=True)
            if energyplus_dirs:
                return str(energyplus_dirs[0])
    
    elif system == "Windows":
        possible_paths = [
            r"C:\EnergyPlusV25-1-0",
            r"C:\EnergyPlus-25-1-0",
            r"C:\Program Files\EnergyPlus-25-1-0",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        c_drive = Path("C:\\")
        if c_drive.exists():
            energyplus_dirs = sorted(c_drive.glob("EnergyPlus*"), reverse=True)
            if energyplus_dirs:
                return str(energyplus_dirs[0])
            
            program_files = Path(r"C:\Program Files")
            if program_files.exists():
                energyplus_dirs = sorted(program_files.glob("EnergyPlus*"), reverse=True)
                if energyplus_dirs:
                    return str(energyplus_dirs[0])
    
    elif system == "Linux":
        possible_paths = [
            "/usr/local/EnergyPlus-25-1-0",
            "/opt/EnergyPlus-25-1-0",
            os.path.expanduser("~/EnergyPlus-25-1-0"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        for base_dir in ["/usr/local", "/opt"]:
            base_path = Path(base_dir)
            if base_path.exists():
                energyplus_dirs = sorted(base_path.glob("EnergyPlus*"), reverse=True)
                if energyplus_dirs:
                    return str(energyplus_dirs[0])
    
    print(f"WARNING: EnergyPlus installation not found automatically on {system}")
    print("Please set ENERGYPLUS_PATH manually in config.py")
    
    if system == "Darwin":
        return "/Applications/EnergyPlus-25-1-0"
    elif system == "Windows":
        return r"C:\EnergyPlusV25-1-0"
    else:
        return "/usr/local/EnergyPlus-25-1-0"

ENERGYPLUS_PATH = get_energyplus_path()

WEATHER_FILE = "weather/USA_GA_Atlanta-Hartsfield-Jackson.Intl.AP.722190_TMY3.epw"

REFERENCE_IDF = "reference/1ZoneDataCenterCRAC_wPumpedDXCoolingCoil.idf"

SIMULATION_PERIOD = "single_day"
TIMESTEP = 4
REPORTING_FREQUENCY = "Timestep"

AIR_DENSITY = 1.184
AIR_SPECIFIC_HEAT = 1007
CFM_TO_M3S = 1 / 2119

SCENARIO_1 = {
    "name": "Baseline_Validated",
    "description": "Validated against ATL01 PACE Room",
    "room": {
        "length": 15.0,
        "width": 10.0,
        "height": 3.0,
    },
    "racks": {
        "rows": 3,
        "racks_per_row": 20,
        "power_per_rack": 40000,
        "total_racks": 60,
        "total_power": 2400000,
    },
    "cooling": {
        "dclc_effectiveness": 0.20,
        "rdhx_effectiveness": 0.90,
        "num_air_handlers": 2,
        "cfm_per_handler": 155000,
        "total_cfm": 310000,
    },
    "heat_exchangers": {
        "count": 0,
        "capacity_each": 0,
    },
    "target_temp": 24.4,
}

SCENARIO_2 = {
    "name": "Waste_Heat_Recovery",
    "description": "Baseline + heat exchangers for waste heat recovery",
    "room": {
        "length": 15.0,
        "width": 10.0,
        "height": 3.0,
    },
    "racks": {
        "rows": 3,
        "racks_per_row": 20,
        "power_per_rack": 40000,
        "total_racks": 60,
        "total_power": 2400000,
    },
    "cooling": {
        "dclc_effectiveness": 0.20,
        "rdhx_effectiveness": 0.90,
        "num_air_handlers": 2,
        "cfm_per_handler": 155000,
        "total_cfm": 310000,
    },
    "heat_exchangers": {
        "count": 2,
        "capacity_each": 80000,
    },
    "target_temp": 24.0,
}

SCENARIO_3 = {
    "name": "Scheduled_Mixed_Workloads",
    "description": "Time-varying loads throughout the day",
    "room": {
        "length": 15.0,
        "width": 10.0,
        "height": 3.0,
    },
    "racks": {
        "rows": 3,
        "racks_per_row": 20,
        "power_per_rack": 40000,
        "total_racks": 60,
        "total_power": 2400000,
    },
    "cooling": {
        "dclc_effectiveness": 0.20,
        "rdhx_effectiveness": 0.90,
        "num_air_handlers": 2,
        "cfm_per_handler": 155000,
        "total_cfm": 310000,
    },
    "heat_exchangers": {
        "count": 0,
        "capacity_each": 0,
    },
    "schedules": [
        {
            "name": "Morning_High",
            "start_hour": 8,
            "duration_hours": 4,
            "power_level": 55000,
            "num_racks": 20,
            "total_power": 1100000,
        },
        {
            "name": "Afternoon_Medium",
            "start_hour": 13,
            "duration_hours": 3,
            "power_level": 40000,
            "num_racks": 15,
            "total_power": 600000,
        },
        {
            "name": "Overnight_Low",
            "start_hour": 22,
            "duration_hours": 8,
            "power_level": 20000,
            "num_racks": 30,
            "total_power": 600000,
        },
    ],
    "target_temp": 24.4,
}

SCENARIO_4 = {
    "name": "High_Density_Upgrade",
    "description": "Increased rack count with enhanced cooling",
    "room": {
        "length": 15.0,
        "width": 10.0,
        "height": 3.0,
    },
    "racks": {
        "rows": 4,
        "racks_per_row": 25,
        "power_per_rack": 40000,
        "total_racks": 100,
        "total_power": 4000000,
    },
    "cooling": {
        "dclc_effectiveness": 0.30,
        "rdhx_effectiveness": 0.95,
        "num_air_handlers": 3,
        "cfm_per_handler": 155000,
        "total_cfm": 465000,
    },
    "heat_exchangers": {
        "count": 0,
        "capacity_each": 0,
    },
    "target_temp": 25.0,
}

SCENARIO_5 = {
    "name": "Room_Expansion",
    "description": "Doubled room size with same load",
    "room": {
        "length": 20.0,
        "width": 15.0,
        "height": 3.0,
    },
    "racks": {
        "rows": 3,
        "racks_per_row": 20,
        "power_per_rack": 40000,
        "total_racks": 60,
        "total_power": 2400000,
    },
    "cooling": {
        "dclc_effectiveness": 0.20,
        "rdhx_effectiveness": 0.90,
        "num_air_handlers": 2,
        "cfm_per_handler": 155000,
        "total_cfm": 310000,
    },
    "heat_exchangers": {
        "count": 0,
        "capacity_each": 0,
    },
    "target_temp": 23.5,
}

SCENARIOS = {
    1: SCENARIO_1,
    2: SCENARIO_2,
    3: SCENARIO_3,
    4: SCENARIO_4,
    5: SCENARIO_5,
}