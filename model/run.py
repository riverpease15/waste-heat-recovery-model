#!/usr/bin/env python3
import sys
import os
import subprocess
from pathlib import Path
import shutil

try:
    from .config import ENERGYPLUS_PATH, WEATHER_FILE
except ImportError:
    from config import ENERGYPLUS_PATH, WEATHER_FILE


def run_energyplus(idf_filename):
    scenarios_dir = Path('model/scenarios')
    idf_path = scenarios_dir / idf_filename
    
    if not idf_path.exists():
        print(f"Error: IDF file not found: {idf_path}")
        print(f"\nAvailable IDF files in {scenarios_dir}:")
        for f in sorted(scenarios_dir.glob('*.idf')):
            print(f"  - {f.name}")
        return False
    
    scenario_name = idf_path.stem
    
    outputs_dir = Path('model/outputs')
    scenario_output_dir = outputs_dir / scenario_name
    scenario_output_dir.mkdir(parents=True, exist_ok=True)
    
    weather_path = Path('model') / WEATHER_FILE
    if not weather_path.exists():
        print(f"Error: Weather file not found: {weather_path}")
        return False
    
    #Get EnergyPlus executable and ExpandObjects
    if sys.platform == 'darwin':
        energyplus_exe = os.path.join(ENERGYPLUS_PATH, 'energyplus')
        expandobjects_exe = os.path.join(ENERGYPLUS_PATH, 'ExpandObjects')
    elif sys.platform == 'win32':
        energyplus_exe = os.path.join(ENERGYPLUS_PATH, 'energyplus.exe')
        expandobjects_exe = os.path.join(ENERGYPLUS_PATH, 'ExpandObjects.exe')
    else:
        energyplus_exe = os.path.join(ENERGYPLUS_PATH, 'energyplus')
        expandobjects_exe = os.path.join(ENERGYPLUS_PATH, 'ExpandObjects')
    
    if not os.path.exists(energyplus_exe):
        print(f"Error: EnergyPlus executable not found: {energyplus_exe}")
        print(f"EnergyPlus path: {ENERGYPLUS_PATH}")
        return False
    
    print(f"Running EnergyPlus Simulation")
    print(f"IDF File:      {idf_path}")
    print(f"Weather File:  {weather_path}")
    print(f"Output Dir:    {scenario_output_dir}")
    print(f"EnergyPlus:    {energyplus_exe}")
    
    needs_expansion = False
    with open(idf_path, 'r') as f:
        idf_content = f.read()
        if 'HVACTemplate:' in idf_content or 'HVACTEMPLATE:' in idf_content:
            needs_expansion = True
    
    if needs_expansion:
        print("\nHVACTemplate objects detected - running ExpandObjects preprocessor...")
        
        in_idf = scenario_output_dir / 'in.idf'
        shutil.copy(idf_path, in_idf)
        
        idd_source = os.path.join(ENERGYPLUS_PATH, 'Energy+.idd')
        idd_dest = scenario_output_dir / 'Energy+.idd'
        if os.path.exists(idd_source):
            shutil.copy(idd_source, idd_dest)
        
        if os.path.exists(expandobjects_exe):
            print(f"Running: {expandobjects_exe}")
            expand_result = subprocess.run(
                [expandobjects_exe],
                cwd=str(scenario_output_dir.absolute()),
                capture_output=True,
                text=True,
                check=False
            )
            
            if expand_result.stdout:
                print(expand_result.stdout)
            
            expanded_idf = scenario_output_dir / 'expanded.idf'
            if expanded_idf.exists():
                print("ExpandObjects completed - using expanded.idf")
                idf_to_run = expanded_idf
            else:
                print("ExpandObjects did not create expanded.idf - using original")
                idf_to_run = idf_path
        else:
            print(f"ExpandObjects not found at {expandobjects_exe}")
            idf_to_run = idf_path
    else:
        idf_to_run = idf_path
    
    cmd = [
        energyplus_exe,
        '-w', str(weather_path.absolute()),
        '-d', str(scenario_output_dir.absolute()),
        str(idf_to_run.absolute())
    ]
    
    print(f"\nExecuting: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.stdout:
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:", result.stderr)
        
        err_file = scenario_output_dir / 'eplusout.err'
        if err_file.exists():
            with open(err_file, 'r') as f:
                err_content = f.read()
                
            if 'EnergyPlus Terminated--Fatal Error Detected' in err_content:
                print("\nError file content:")
                print(err_content)
                return False
            elif 'EnergyPlus Completed Successfully' in err_content:
                print("SIMULATION COMPLETED SUCCESSFULLY")
                print(f"\nOutput files saved to: {scenario_output_dir}")
                print("\nKey output files:")
                
                output_files = [
                    ('eplusout.err', 'Error/warning messages'),
                    ('eplusout.end', 'Simulation end status'),
                    ('eplusout.eso', 'Standard output (time series data)'),
                    ('eplusout.mtr', 'Meter output'),
                    ('eplustbl.htm', 'Summary tables (HTML)'),
                    ('eplustbl.csv', 'Summary tables (CSV)'),
                ]
                
                for filename, description in output_files:
                    filepath = scenario_output_dir / filename
                    if filepath.exists():
                        size = filepath.stat().st_size / 1024
                        print(f"  ✓ {filename:20s} - {description} ({size:.1f} KB)")
                
                return True
            else:
                print("\nCheck error file for details:")
                print(err_content)
                return False
        else:
            print("ERROR: No error file generated")
            return False
            
    except Exception as e:
        print(f"\nError running EnergyPlus: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python model/run.py <idf_filename>")
        print("\nExample:")
        print("  python model/run.py scenario_1_Baseline_Validated_detailed.idf")
        print("  python model/run.py scenario_2_Waste_Heat_Recovery_simplified.idf")
        print("\nAvailable scenarios:")
        
        scenarios_dir = Path('model/scenarios')
        if scenarios_dir.exists():
            for f in sorted(scenarios_dir.glob('*.idf')):
                print(f"  - {f.name}")
        else:
            print("(No scenarios found - run EPlusIDF.py first)")
        
        sys.exit(1)
    
    idf_filename = sys.argv[1]
    
    success = run_energyplus(idf_filename)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()