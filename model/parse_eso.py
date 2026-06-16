#!/usr/bin/env python3
"""
Parse EnergyPlus .eso output files to extract and analyze time-series data.

Usage:
    python model/parse_eso.py                          # List all available scenarios
    python model/parse_eso.py scenario_1_Baseline_Validated_detailed
    python model/parse_eso.py 1                        # Use scenario number
"""

import sys
from pathlib import Path


def parse_eso_file(filepath):
    """
    Parses an EnergyPlus .eso file to extract time series data.
    
    Returns:
        variables_map: dict of report_code -> variable_name
        data: dict of variable_name -> list of values
    """
    variables_map = {}
    data = {}
    
    if not filepath.exists():
        print(f"Error: File {filepath} not found.")
        return variables_map, data
        
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("Program Version") or line.startswith("End of Data"):
                continue
            
            parts = line.split(',')
            
            if len(parts) >= 3 and '!' in line:
                try:
                    report_code = int(parts[0].strip())
                    desc_part = ','.join(parts[2:]).split('!')[0].strip()
                    
                    if ',' in desc_part:
                        desc_part = desc_part.split(',', 1)[1].strip()
                    
                    if '[' in desc_part:
                        var_name = desc_part.split('[')[0].strip()
                    else:
                        var_name = desc_part
                    
                    variables_map[report_code] = var_name
                    if var_name not in data:
                        data[var_name] = []
                except (ValueError, IndexError):
                    pass
            elif len(parts) == 2:
                try:
                    report_code = int(parts[0].strip())
                    val = float(parts[1].strip())
                    if report_code in variables_map:
                        var_name = variables_map[report_code]
                        data[var_name].append(val)
                except ValueError:
                    pass
    
    return variables_map, data


def find_var(data, key):
    for k in data.keys():
        if key.lower() in k.lower():
            return k
    return None


def analyze_detailed_model(eso_path, scenario_name):
    print(f"ANALYZING: {scenario_name}")
    print(f"ESO File: {eso_path}")
    print()
    
    det_vars, det_data = parse_eso_file(eso_path)
    
    if not det_data:
        print("No simulation data found in .eso file.")
        print("The simulation may have failed or not completed.")
        return
    
    print(f"Found {len(det_data)} variables with time-series data")
    print(f"Total data points: {sum(len(v) for v in det_data.values())}")
    print()
    
    print("ZONE CONDITIONS")
    temp_key = find_var(det_data, "Zone Mean Air Temperature")
    if temp_key and det_data[temp_key]:
        temps = det_data[temp_key]
        print(f"Zone Mean Temperature: Min={min(temps):.2f}°C, Max={max(temps):.2f}°C, Avg={sum(temps)/len(temps):.2f}°C")
    
    cool_set_key = find_var(det_data, "Zone Thermostat Cooling Setpoint")
    if cool_set_key and det_data[cool_set_key]:
        sets = det_data[cool_set_key]
        print(f"Cooling Setpoint: Min={min(sets):.2f}°C, Max={max(sets):.2f}°C, Avg={sum(sets)/len(sets):.2f}°C")
    
    print()
    print("ITE EQUIPMENT (Server Racks)")
    
    ite_cpu_key = find_var(det_data, "Zone ITE CPU Electricity Rate")
    ite_fan_key = find_var(det_data, "Zone ITE Fan Electricity Rate")
    ite_ups_key = find_var(det_data, "Zone ITE UPS Electricity Rate")
    ite_total_gain_key = find_var(det_data, "Zone ITE Total Heat Gain to Zone Rate")
    
    if ite_cpu_key and det_data[ite_cpu_key]:
        val = det_data[ite_cpu_key]
        print(f"CPU Power: Min={min(val)/1000:.1f} kW, Max={max(val)/1000:.1f} kW, Avg={sum(val)/len(val)/1000:.1f} kW")
    
    if ite_fan_key and det_data[ite_fan_key]:
        val = det_data[ite_fan_key]
        print(f"ITE Internal Fans: Min={min(val)/1000:.1f} kW, Max={max(val)/1000:.1f} kW, Avg={sum(val)/len(val)/1000:.1f} kW")
    
    if ite_ups_key and det_data[ite_ups_key]:
        val = det_data[ite_ups_key]
        print(f"UPS Losses: Min={min(val)/1000:.1f} kW, Max={max(val)/1000:.1f} kW, Avg={sum(val)/len(val)/1000:.1f} kW")
    
    if ite_total_gain_key and det_data[ite_total_gain_key]:
        val = det_data[ite_total_gain_key]
        print(f"Total Heat to Zone: Min={min(val)/1000:.1f} kW, Max={max(val)/1000:.1f} kW, Avg={sum(val)/len(val)/1000:.1f} kW")
    
    print()
    print("HVAC SYSTEM PERFORMANCE")
    
    coil_cool_tot_key = find_var(det_data, "Cooling Coil Total Cooling Rate")
    coil_elec_key = find_var(det_data, "Cooling Coil Electricity Rate")
    fan_elec_key = find_var(det_data, "Fan Electricity Rate")
    
    if coil_cool_tot_key and det_data[coil_cool_tot_key]:
        val = det_data[coil_cool_tot_key]
        print(f"Cooling Coil Capacity: Min={min(val)/1000:.1f} kW, Max={max(val)/1000:.1f} kW, Avg={sum(val)/len(val)/1000:.1f} kW")
    
    if coil_elec_key and det_data[coil_elec_key]:
        val = det_data[coil_elec_key]
        print(f"Cooling Coil Power: Min={min(val)/1000:.1f} kW, Max={max(val)/1000:.1f} kW, Avg={sum(val)/len(val)/1000:.1f} kW")
    
    if fan_elec_key and det_data[fan_elec_key]:
        val = det_data[fan_elec_key]
        print(f"Supply Fan Power: Min={min(val)/1000:.1f} kW, Max={max(val)/1000:.1f} kW, Avg={sum(val)/len(val)/1000:.1f} kW")
    
    if coil_cool_tot_key and coil_elec_key and det_data[coil_cool_tot_key] and det_data[coil_elec_key]:
        tot_cool = sum(det_data[coil_cool_tot_key])
        elec = sum(det_data[coil_elec_key])
        if elec > 0:
            cop = tot_cool / elec
            print(f"Average Cooling COP: {cop:.2f}")
    
    print()
    print("ENERGY SUMMARY")
    
    if ite_total_gain_key and det_data[ite_total_gain_key]:
        total_ite_energy = sum(det_data[ite_total_gain_key]) / 1000
        print(f"Total ITE Heat Output: {total_ite_energy:.1f} kWh")
    
    if coil_cool_tot_key and det_data[coil_cool_tot_key]:
        total_cooling = sum(det_data[coil_cool_tot_key]) / 1000
        print(f"Total Cooling Delivered: {total_cooling:.1f} kWh")
    
    if fan_elec_key and det_data[fan_elec_key]:
        total_fan = sum(det_data[fan_elec_key]) / 1000
        print(f"Total Fan Energy: {total_fan:.1f} kWh")
    
    print()


def find_detailed_scenarios():
    outputs_dir = Path('model/outputs')
    
    if not outputs_dir.exists():
        return []
    
    detailed_dirs = [d for d in outputs_dir.iterdir() 
                     if d.is_dir() and d.name.endswith('_detailed')]
    
    return sorted(detailed_dirs)


def main():
    detailed_scenarios = find_detailed_scenarios()
    
    if not detailed_scenarios:
        print("No detailed scenario outputs found in model/outputs/")
        print("\nRun simulations first:")
        print("  python model/run.py scenario_1_Baseline_Validated_detailed.idf")
        return
    
    if len(sys.argv) < 2:
        print()
        
        analyzed_count = 0
        for i, scenario_dir in enumerate(detailed_scenarios, 1):
            eso_file = scenario_dir / 'eplusout.eso'
            
            if eso_file.exists():
                analyze_detailed_model(eso_file, scenario_dir.name)
                analyzed_count += 1
                
                if i < len(detailed_scenarios):
                    print()
            else:
                print(f"Skipping {scenario_dir.name} - no simulation data found")
                print()
        
        print("ANALYSIS COMPLETE")
        print(f"\nAnalyzed {analyzed_count} of {len(detailed_scenarios)} scenarios")
        print("\nTo analyze a specific scenario:")
        print("  python model/parse_eso.py <scenario_name>")
        print("  python model/parse_eso.py <scenario_number>")
        return
    
    arg = sys.argv[1]
    
    if arg.isdigit():
        scenario_num = int(arg)
        if 1 <= scenario_num <= len(detailed_scenarios):
            scenario_dir = detailed_scenarios[scenario_num - 1]
        else:
            print(f"Error: Scenario number {scenario_num} out of range (1-{len(detailed_scenarios)})")
            return
    else:
        scenario_name = arg
        if not scenario_name.endswith('_detailed'):
            scenario_name += '_detailed'
        
        scenario_dir = Path('model/outputs') / scenario_name
        
        if not scenario_dir.exists():
            print(f"Error: Scenario '{scenario_name}' not found")
            print("\nAvailable scenarios:")
            for i, d in enumerate(detailed_scenarios, 1):
                print(f"  {i}. {d.name}")
            return
    
    eso_file = scenario_dir / 'eplusout.eso'
    if not eso_file.exists():
        print(f"Error: No eplusout.eso file found in {scenario_dir}")
        print("\nRun the simulation first:")
        print(f"  python model/run.py {scenario_dir.name}.idf")
        return
    
    analyze_detailed_model(eso_file, scenario_dir.name)


if __name__ == '__main__':
    main()