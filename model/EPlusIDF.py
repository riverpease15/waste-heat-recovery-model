import sys
import os
from pathlib import Path
from io import StringIO

from eppy.modeleditor import IDF

try:
    from .config import SCENARIOS, ENERGYPLUS_PATH, WEATHER_FILE, TIMESTEP, REPORTING_FREQUENCY
except ImportError:
    from config import SCENARIOS, ENERGYPLUS_PATH, WEATHER_FILE, TIMESTEP, REPORTING_FREQUENCY

if ENERGYPLUS_PATH and os.path.exists(ENERGYPLUS_PATH):
    sys.path.insert(0, ENERGYPLUS_PATH)

class SimplifiedIDFGenerator:
    """Generate simplified IDF files using ideal loads approach"""
    
    def __init__(self, energyplus_path):
        """Initialize the generator with EnergyPlus installation path"""
        self.energyplus_path = energyplus_path
        self.idd_path = os.path.join(energyplus_path, 'Energy+.idd')
        
        try:
            IDF.setiddname(self.idd_path)
        except Exception as e:
            print(f"Warning: Could not set IDD file: {e}")
            print(f"Attempted path: {self.idd_path}")
    
    def create_base_idf(self):
        """Create a base IDF with common objects"""
        idf = IDF(StringIO(''))
        
        idf.newidfobject('VERSION')
        idf.idfobjects['VERSION'][0].Version_Identifier = '25.1'
        
        sim_control = idf.newidfobject('SIMULATIONCONTROL')
        sim_control.Do_Zone_Sizing_Calculation = 'Yes'
        sim_control.Do_System_Sizing_Calculation = 'Yes'
        sim_control.Do_Plant_Sizing_Calculation = 'Yes'
        sim_control.Run_Simulation_for_Sizing_Periods = 'Yes'
        sim_control.Run_Simulation_for_Weather_File_Run_Periods = 'No'
        
        timestep = idf.newidfobject('TIMESTEP')
        timestep.Number_of_Timesteps_per_Hour = TIMESTEP
        
        building = idf.newidfobject('BUILDING')
        building.Name = 'ATL01_DataCenter'
        building.North_Axis = 0
        building.Terrain = 'City'
        building.Loads_Convergence_Tolerance_Value = 0.04
        building.Temperature_Convergence_Tolerance_Value = 0.4
        building.Solar_Distribution = 'FullExterior'
        building.Maximum_Number_of_Warmup_Days = 25
        
        geom = idf.newidfobject('GLOBALGEOMETRYRULES')
        geom.Starting_Vertex_Position = 'UpperLeftCorner'
        geom.Vertex_Entry_Direction = 'Counterclockwise'
        geom.Coordinate_System = 'Relative'
        
        site = idf.newidfobject('SITE:LOCATION')
        site.Name = 'Atlanta_Hartsfield_Intl_AP_GA_USA'
        site.Latitude = 33.64
        site.Longitude = -84.43
        site.Time_Zone = -5.0
        site.Elevation = 308.0
        
        design_day = idf.newidfobject('SIZINGPERIOD:DESIGNDAY')
        design_day.Name = 'Atlanta_Summer_Design_Day'
        design_day.Month = 7
        design_day.Day_of_Month = 21
        design_day.Day_Type = 'SummerDesignDay'
        design_day.Maximum_DryBulb_Temperature = 33.3
        design_day.Daily_DryBulb_Temperature_Range = 10.0
        design_day.DryBulb_Temperature_Range_Modifier_Type = 'DefaultMultipliers'
        design_day.Humidity_Condition_Type = 'WetBulb'
        design_day.Wetbulb_or_DewPoint_at_Maximum_DryBulb = 23.9
        design_day.Barometric_Pressure = 98934
        design_day.Wind_Speed = 3.8
        design_day.Wind_Direction = 310
        design_day.Sky_Clearness = 1.0
        
        run_period = idf.newidfobject('RUNPERIOD')
        run_period.Name = 'SingleDay'
        run_period.Begin_Month = 7
        run_period.Begin_Day_of_Month = 21
        run_period.End_Month = 7
        run_period.End_Day_of_Month = 21
        run_period.Day_of_Week_for_Start_Day = 'Monday'
        run_period.Use_Weather_File_Holidays_and_Special_Days = 'No'
        run_period.Use_Weather_File_Daylight_Saving_Period = 'No'
        run_period.Apply_Weekend_Holiday_Rule = 'No'
        run_period.Use_Weather_File_Rain_Indicators = 'Yes'
        run_period.Use_Weather_File_Snow_Indicators = 'Yes'
        
        output_control = idf.newidfobject('OUTPUT:VARIABLEDICTIONARY')
        output_control.Key_Field = 'IDF'
        
        output_table = idf.newidfobject('OUTPUT:TABLE:SUMMARYREPORTS')
        output_table.Report_1_Name = 'AllSummary'
        
        self._add_output_variables(idf)
        
        return idf
    
    def _add_output_variables(self, idf):
        """Add output variables for monitoring"""
        variables = [
            ('Zone Mean Air Temperature', '*'),
            ('Zone Air System Sensible Cooling Rate', '*'),
            ('Zone Air System Sensible Heating Rate', '*'),
            ('Zone Electric Equipment Electricity Rate', '*'),
            ('Zone Electric Equipment Total Heating Rate', '*'),
            ('Zone Ideal Loads Zone Total Cooling Rate', '*'),
            ('Zone Ideal Loads Zone Total Heating Rate', '*'),
        ]
        
        for var_name, key in variables:
            output_var = idf.newidfobject('OUTPUT:VARIABLE')
            output_var.Key_Value = key
            output_var.Variable_Name = var_name
            output_var.Reporting_Frequency = REPORTING_FREQUENCY
    
    def add_zone(self, idf, scenario):
        """Add zone geometry for data center room"""
        room = scenario['room']
        name = scenario['name']
        
        zone = idf.newidfobject('ZONE')
        zone.Name = f'{name}_Zone'
        zone.Direction_of_Relative_North = 0
        zone.X_Origin = 0
        zone.Y_Origin = 0
        zone.Z_Origin = 0
        zone.Type = 1
        zone.Multiplier = 1
        zone.Ceiling_Height = room['height']
        zone.Volume = room['length'] * room['width'] * room['height']
        
        self._add_constructions(idf, scenario)
        
        floor = idf.newidfobject('BUILDINGSURFACE:DETAILED')
        floor.Name = f'{name}_Floor'
        floor.Surface_Type = 'Floor'
        floor.Construction_Name = 'Floor_Construction'
        floor.Zone_Name = zone.Name
        floor.Outside_Boundary_Condition = 'Ground'
        floor.Sun_Exposure = 'NoSun'
        floor.Wind_Exposure = 'NoWind'
        floor.View_Factor_to_Ground = 0
        floor.Number_of_Vertices = 4
        floor.Vertex_1_Xcoordinate = 0
        floor.Vertex_1_Ycoordinate = room['width']
        floor.Vertex_1_Zcoordinate = 0
        floor.Vertex_2_Xcoordinate = room['length']
        floor.Vertex_2_Ycoordinate = room['width']
        floor.Vertex_2_Zcoordinate = 0
        floor.Vertex_3_Xcoordinate = room['length']
        floor.Vertex_3_Ycoordinate = 0
        floor.Vertex_3_Zcoordinate = 0
        floor.Vertex_4_Xcoordinate = 0
        floor.Vertex_4_Ycoordinate = 0
        floor.Vertex_4_Zcoordinate = 0
        
        ceiling = idf.newidfobject('BUILDINGSURFACE:DETAILED')
        ceiling.Name = f'{name}_Ceiling'
        ceiling.Surface_Type = 'Ceiling'
        ceiling.Construction_Name = 'Adiabatic_Construction'
        ceiling.Zone_Name = zone.Name
        ceiling.Outside_Boundary_Condition = 'Adiabatic'
        ceiling.Sun_Exposure = 'NoSun'
        ceiling.Wind_Exposure = 'NoWind'
        ceiling.View_Factor_to_Ground = 0
        ceiling.Number_of_Vertices = 4
        ceiling.Vertex_1_Xcoordinate = 0
        ceiling.Vertex_1_Ycoordinate = 0
        ceiling.Vertex_1_Zcoordinate = room['height']
        ceiling.Vertex_2_Xcoordinate = room['length']
        ceiling.Vertex_2_Ycoordinate = 0
        ceiling.Vertex_2_Zcoordinate = room['height']
        ceiling.Vertex_3_Xcoordinate = room['length']
        ceiling.Vertex_3_Ycoordinate = room['width']
        ceiling.Vertex_3_Zcoordinate = room['height']
        ceiling.Vertex_4_Xcoordinate = 0
        ceiling.Vertex_4_Ycoordinate = room['width']
        ceiling.Vertex_4_Zcoordinate = room['height']
        
        walls = [
            ('North', [(0, room['width'], 0), (0, room['width'], room['height']),
                      (room['length'], room['width'], room['height']), (room['length'], room['width'], 0)]),
            ('East', [(room['length'], room['width'], 0), (room['length'], room['width'], room['height']),
                     (room['length'], 0, room['height']), (room['length'], 0, 0)]),
            ('South', [(room['length'], 0, 0), (room['length'], 0, room['height']),
                      (0, 0, room['height']), (0, 0, 0)]),
            ('West', [(0, 0, 0), (0, 0, room['height']),
                     (0, room['width'], room['height']), (0, room['width'], 0)]),
        ]
        
        for wall_name, vertices in walls:
            wall = idf.newidfobject('BUILDINGSURFACE:DETAILED')
            wall.Name = f'{name}_Wall_{wall_name}'
            wall.Surface_Type = 'Wall'
            if wall_name in ['North', 'South']:
                wall.Construction_Name = 'Wall_Construction'
                wall.Outside_Boundary_Condition = 'Outdoors'
                wall.Sun_Exposure = 'SunExposed'
                wall.Wind_Exposure = 'WindExposed'
            else:
                wall.Construction_Name = 'Adiabatic_Construction'
                wall.Outside_Boundary_Condition = 'Adiabatic'
                wall.Sun_Exposure = 'NoSun'
                wall.Wind_Exposure = 'NoWind'
            wall.Zone_Name = zone.Name
            wall.View_Factor_to_Ground = 0
            wall.Number_of_Vertices = 4
            for i, (x, y, z) in enumerate(vertices, 1):
                setattr(wall, f'Vertex_{i}_Xcoordinate', x)
                setattr(wall, f'Vertex_{i}_Ycoordinate', y)
                setattr(wall, f'Vertex_{i}_Zcoordinate', z)
        
        return zone.Name

    def _add_constructions(self, idf, scenario):
        """Add construction and material definitions"""
        try:
            ground_temp = idf.newidfobject('SITE:GROUNDTEMPERATURE:BUILDINGSURFACE')
            for month in ['January', 'February', 'March', 'April', 'May', 'June',
                          'July', 'August', 'September', 'October', 'November', 'December']:
                setattr(ground_temp, f'{month}_Ground_Temperature', 17.0)
        except Exception:
            pass
            
        wall_u = scenario.get('wall_u', 0.19)
        wall_r = 1.0 / wall_u
        
        wall_mat = idf.newidfobject('MATERIAL:NOMASS')
        wall_mat.Name = 'Wall_Material'
        wall_mat.Roughness = 'Smooth'
        wall_mat.Thermal_Resistance = wall_r
        wall_mat.Thermal_Absorptance = 0.9
        wall_mat.Solar_Absorptance = 0.7
        wall_mat.Visible_Absorptance = 0.7
        
        wall_const = idf.newidfobject('CONSTRUCTION')
        wall_const.Name = 'Wall_Construction'
        wall_const.Outside_Layer = 'Wall_Material'
        
        floor_u = scenario.get('floor_u', 0.50)
        floor_r = 1.0 / floor_u
        
        floor_mat = idf.newidfobject('MATERIAL:NOMASS')
        floor_mat.Name = 'Floor_Material'
        floor_mat.Roughness = 'Smooth'
        floor_mat.Thermal_Resistance = floor_r
        floor_mat.Thermal_Absorptance = 0.9
        floor_mat.Solar_Absorptance = 0.7
        floor_mat.Visible_Absorptance = 0.7
        
        floor_const = idf.newidfobject('CONSTRUCTION')
        floor_const.Name = 'Floor_Construction'
        floor_const.Outside_Layer = 'Floor_Material'
        
        construction = idf.newidfobject('CONSTRUCTION')
        construction.Name = 'Adiabatic_Construction'
        construction.Outside_Layer = 'Adiabatic_Material'
        
        material = idf.newidfobject('MATERIAL')
        material.Name = 'Adiabatic_Material'
        material.Roughness = 'Smooth'
        material.Thickness = 0.1
        material.Conductivity = 0.001
        material.Density = 1.0
        material.Specific_Heat = 1000
        material.Thermal_Absorptance = 0.9
        material.Solar_Absorptance = 0.7
        material.Visible_Absorptance = 0.7
        
        return zone.Name
    
    def add_internal_loads(self, idf, zone_name, scenario):
        """Add server rack loads as electric equipment with liquid cooling fraction lost"""
        racks = scenario['racks']
        name = scenario['name']
        cooling = scenario['cooling']
        
        dclc_eff = cooling['dclc_effectiveness']
        rdhx_eff = cooling['rdhx_effectiveness']
        
        #Base fraction of heat entering the zone air (not captured by liquid cooling)
        raw_frac_to_air = (1.0 - dclc_eff) * (1.0 - rdhx_eff)
        
        hx = scenario.get('heat_exchangers', {'count': 0, 'capacity_each': 0})
        total_hx_capacity = hx['count'] * hx['capacity_each']
        
        if 'schedules' in scenario:
            self._add_scheduled_loads(idf, zone_name, scenario, raw_frac_to_air, total_hx_capacity)
        else:
            schedule = self._create_constant_schedule(idf, name)
            
            total_power = racks['total_power']
            if total_power > 0:
                to_air_before_hx = total_power * raw_frac_to_air
                remaining = max(to_air_before_hx - total_hx_capacity, 0.0)
                frac_to_air = remaining / total_power
            else:
                frac_to_air = 0.0
                
            fraction_lost = 1.0 - frac_to_air
            fraction_radiant = frac_to_air * 0.30
            
            equipment = idf.newidfobject('ELECTRICEQUIPMENT')
            equipment.Name = f'{name}_ServerRacks'
            equipment.Zone_or_ZoneList_or_Space_or_SpaceList_Name = zone_name
            equipment.Schedule_Name = schedule
            equipment.Design_Level_Calculation_Method = 'EquipmentLevel'
            equipment.Design_Level = total_power
            equipment.Fraction_Latent = 0.0
            equipment.Fraction_Radiant = fraction_radiant
            equipment.Fraction_Lost = fraction_lost
    
    def _create_constant_schedule(self, idf, name):
        """Create a constant schedule (always on)"""
        schedule_name = f'{name}_AlwaysOn'
        
        schedule_type = idf.newidfobject('SCHEDULETYPELIMITS')
        schedule_type.Name = 'Fraction'
        schedule_type.Lower_Limit_Value = 0.0
        schedule_type.Upper_Limit_Value = 1.0
        schedule_type.Numeric_Type = 'Continuous'
        
        schedule = idf.newidfobject('SCHEDULE:COMPACT')
        schedule.Name = schedule_name
        schedule.Schedule_Type_Limits_Name = 'Fraction'
        schedule.Field_1 = 'Through: 12/31'
        schedule.Field_2 = 'For: AllDays'
        schedule.Field_3 = 'Until: 24:00'
        schedule.Field_4 = 1.0
        
        return schedule_name
    
    def _add_scheduled_loads(self, idf, zone_name, scenario, raw_frac_to_air, total_hx_capacity):
        """Add time-varying loads for scenario 3"""
        name = scenario['name']
        schedules = scenario['schedules']
        
        schedule_type = idf.newidfobject('SCHEDULETYPELIMITS')
        schedule_type.Name = 'Fraction'
        schedule_type.Lower_Limit_Value = 0.0
        schedule_type.Upper_Limit_Value = 1.0
        schedule_type.Numeric_Type = 'Continuous'
        
        for job in schedules:
            schedule_name = f'{name}_{job["name"]}_Schedule'
            
            self._create_job_schedule(idf, schedule_name, job)
            
            #Calculate fraction lost and radiant for this job
            job_power = job['total_power']
            if job_power > 0:
                to_air_before_hx = job_power * raw_frac_to_air
                remaining = max(to_air_before_hx - total_hx_capacity, 0.0)
                frac_to_air = remaining / job_power
            else:
                frac_to_air = 0.0
                
            fraction_lost = 1.0 - frac_to_air
            fraction_radiant = frac_to_air * 0.30
            
            equipment = idf.newidfobject('ELECTRICEQUIPMENT')
            equipment.Name = f'{name}_{job["name"]}'
            equipment.Zone_or_ZoneList_or_Space_or_SpaceList_Name = zone_name
            equipment.Schedule_Name = schedule_name
            equipment.Design_Level_Calculation_Method = 'EquipmentLevel'
            equipment.Design_Level = job_power
            equipment.Fraction_Latent = 0.0
            equipment.Fraction_Radiant = fraction_radiant
            equipment.Fraction_Lost = fraction_lost

    def _create_job_schedule(self, idf, schedule_name, job):
        """Create a compact schedule for a job, supporting midnight wrapping"""
        schedule = idf.newidfobject('SCHEDULE:COMPACT')
        schedule.Name = schedule_name
        schedule.Schedule_Type_Limits_Name = 'Fraction'
        schedule.Field_1 = 'Through: 12/31'
        schedule.Field_2 = 'For: AllDays'
        
        start_hour = int(job['start_hour'])
        duration = float(job.get('duration_hours', job.get('duration', 0.0)))
        end_hour = start_hour + duration
        
        if end_hour > 24.0:
            wrapped_end = int(end_hour - 24.0)
            schedule.Field_3 = f'Until: {wrapped_end:02d}:00'
            schedule.Field_4 = 1.0
            schedule.Field_5 = f'Until: {start_hour:02d}:00'
            schedule.Field_6 = 0.0
            schedule.Field_7 = 'Until: 24:00'
            schedule.Field_8 = 1.0
        else:
            current_field = 3
            if start_hour > 0:
                setattr(schedule, f'Field_{current_field}', f'Until: {start_hour:02d}:00')
                setattr(schedule, f'Field_{current_field+1}', 0.0)
                current_field += 2
            
            end_hour_int = int(end_hour)
            setattr(schedule, f'Field_{current_field}', f'Until: {end_hour_int:02d}:00')
            setattr(schedule, f'Field_{current_field+1}', 1.0)
            current_field += 2
            
            if end_hour_int < 24:
                setattr(schedule, f'Field_{current_field}', 'Until: 24:00')
                setattr(schedule, f'Field_{current_field+1}', 0.0)
            
            #Calculate fraction lost and radiant for this job
            job_power = job['total_power']
            if job_power > 0:
                to_air_before_hx = job_power * raw_frac_to_air
                remaining = max(to_air_before_hx - total_hx_capacity, 0.0)
                frac_to_air = remaining / job_power
            else:
                frac_to_air = 0.0
                
            fraction_lost = 1.0 - frac_to_air
            fraction_radiant = frac_to_air * 0.30
            
            equipment = idf.newidfobject('ELECTRICEQUIPMENT')
            equipment.Name = f'{name}_{job["name"]}'
            equipment.Zone_or_ZoneList_or_Space_or_SpaceList_Name = zone_name
            equipment.Schedule_Name = schedule_name
            equipment.Design_Level_Calculation_Method = 'EquipmentLevel'
            equipment.Design_Level = job_power
            equipment.Fraction_Latent = 0.0
            equipment.Fraction_Radiant = fraction_radiant
            equipment.Fraction_Lost = fraction_lost
    
    def add_ideal_loads(self, idf, zone_name, scenario):
        """Add ideal loads air system with effectiveness factors"""
        name = scenario['name']
        cooling = scenario['cooling']
        
        liquid_cooling_effectiveness = cooling['dclc_effectiveness'] + cooling['rdhx_effectiveness']
        
        hx = scenario.get('heat_exchangers', {'count': 0, 'capacity_each': 0})
        total_hx_capacity = hx['count'] * hx['capacity_each']
        
        ideal_loads = idf.newidfobject('HVACTEMPLATE:ZONE:IDEALLOADSAIRSYSTEM')
        ideal_loads.Zone_Name = zone_name
        ideal_loads.Template_Thermostat_Name = f'{name}_Thermostat'
        ideal_loads.System_Availability_Schedule_Name = 'AlwaysOn'
        ideal_loads.Maximum_Heating_Supply_Air_Temperature = 50
        ideal_loads.Minimum_Cooling_Supply_Air_Temperature = 13
        ideal_loads.Maximum_Heating_Supply_Air_Humidity_Ratio = 0.0156
        ideal_loads.Minimum_Cooling_Supply_Air_Humidity_Ratio = 0.0077
        ideal_loads.Heating_Limit = 'NoLimit'
        ideal_loads.Maximum_Heating_Air_Flow_Rate = 'autosize'
        ideal_loads.Cooling_Limit = 'NoLimit'
        ideal_loads.Maximum_Cooling_Air_Flow_Rate = 'autosize'
        ideal_loads.Dehumidification_Control_Type = 'None'
        ideal_loads.Cooling_Sensible_Heat_Ratio = 1.0
        ideal_loads.Humidification_Control_Type = 'None'
        ideal_loads.Outdoor_Air_Method = 'None'
        ideal_loads.Demand_Controlled_Ventilation_Type = 'None'
        ideal_loads.Outdoor_Air_Economizer_Type = 'NoEconomizer'
        ideal_loads.Heat_Recovery_Type = 'None'
        
        thermostat = idf.newidfobject('HVACTEMPLATE:THERMOSTAT')
        thermostat.Name = f'{name}_Thermostat'
        thermostat.Heating_Setpoint_Schedule_Name = 'HeatingSetpoint'
        thermostat.Constant_Heating_Setpoint = 18.0
        thermostat.Cooling_Setpoint_Schedule_Name = 'CoolingSetpoint'
        thermostat.Constant_Cooling_Setpoint = scenario.get('target_temp', 24.0)
        
        always_on = idf.newidfobject('SCHEDULE:COMPACT')
        always_on.Name = 'AlwaysOn'
        always_on.Schedule_Type_Limits_Name = 'Fraction'
        always_on.Field_1 = 'Through: 12/31'
        always_on.Field_2 = 'For: AllDays'
        always_on.Field_3 = 'Until: 24:00'
        always_on.Field_4 = 1.0
        
        heating = idf.newidfobject('SCHEDULE:COMPACT')
        heating.Name = 'HeatingSetpoint'
        heating.Schedule_Type_Limits_Name = 'Temperature'
        heating.Field_1 = 'Through: 12/31'
        heating.Field_2 = 'For: AllDays'
        heating.Field_3 = 'Until: 24:00'
        heating.Field_4 = 18.0
        
        cooling_sched = idf.newidfobject('SCHEDULE:COMPACT')
        cooling_sched.Name = 'CoolingSetpoint'
        cooling_sched.Schedule_Type_Limits_Name = 'Temperature'
        cooling_sched.Field_1 = 'Through: 12/31'
        cooling_sched.Field_2 = 'For: AllDays'
        cooling_sched.Field_3 = 'Until: 24:00'
        cooling_sched.Field_4 = scenario.get('target_temp', 24.0)
        
        temp_type = idf.newidfobject('SCHEDULETYPELIMITS')
        temp_type.Name = 'Temperature'
        temp_type.Lower_Limit_Value = -100
        temp_type.Upper_Limit_Value = 200
        temp_type.Numeric_Type = 'Continuous'
        temp_type.Unit_Type = 'Temperature'
    
    def generate_scenario_from_dict(self, scenario, filepath):
        """Generate IDF file for a scenario dictionary directly"""
        idf = self.create_base_idf()
        zone_name = self.add_zone(idf, scenario)
        self.add_internal_loads(idf, zone_name, scenario)
        self.add_ideal_loads(idf, zone_name, scenario)
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        idf.saveas(str(filepath))
        return filepath
        
    def generate_scenario(self, scenario_num):
        """Generate IDF file for a specific scenario"""
        scenario = SCENARIOS[scenario_num]
        print(f"\nGenerating Scenario {scenario_num}: {scenario['name']}")
        print(f"Description: {scenario['description']}")
        
        output_dir = Path('model/scenarios')
        output_file = output_dir / f'scenario_{scenario_num}_{scenario["name"]}_simplified.idf'
        self.generate_scenario_from_dict(scenario, output_file)
        
        print(f"✓ Generated: {output_file}")
        return output_file
    
    def generate_all_scenarios(self):
        print("Simplified IDF Generator for ATL01 Data Center")
        
        output_files = []
        for scenario_num in SCENARIOS.keys():
            output_file = self.generate_scenario(scenario_num)
            output_files.append(output_file)
        
        print(f"Successfully generated {len(output_files)} IDF files")
        
        return output_files


class DetailedIDFGenerator:
    """
    Generate detailed IDF files with actual HVAC components for data centers
    
    This generator creates realistic models with:
    - ElectricEquipment:ITE:AirCooled for server racks
    - AirLoopHVAC with DX cooling coils (CRAC system)
    - Variable volume fans
    - VAV terminals
    - Detailed performance curves
    """
    
    def __init__(self, energyplus_path):
        """Initialize the generator with EnergyPlus installation path"""
        self.energyplus_path = energyplus_path
        self.idd_path = os.path.join(energyplus_path, 'Energy+.idd')
        
        try:
            IDF.setiddname(self.idd_path)
        except Exception as e:
            print(f"Warning: Could not set IDD file: {e}")
            print(f"Attempted path: {self.idd_path}")
    
    def create_base_idf(self):
        """Create a base IDF with common objects"""
        idf = IDF(StringIO(''))
        
        idf.newidfobject('VERSION')
        idf.idfobjects['VERSION'][0].Version_Identifier = '25.1'
        
        sim_control = idf.newidfobject('SIMULATIONCONTROL')
        sim_control.Do_Zone_Sizing_Calculation = 'Yes'
        sim_control.Do_System_Sizing_Calculation = 'Yes'
        sim_control.Do_Plant_Sizing_Calculation = 'No'
        sim_control.Run_Simulation_for_Sizing_Periods = 'Yes'
        sim_control.Run_Simulation_for_Weather_File_Run_Periods = 'No'
        
        timestep = idf.newidfobject('TIMESTEP')
        timestep.Number_of_Timesteps_per_Hour = TIMESTEP
        
        building = idf.newidfobject('BUILDING')
        building.Name = 'ATL01_DataCenter'
        building.North_Axis = 0
        building.Terrain = 'City'
        building.Loads_Convergence_Tolerance_Value = 0.05
        building.Temperature_Convergence_Tolerance_Value = 0.05
        building.Solar_Distribution = 'MinimalShadowing'
        building.Maximum_Number_of_Warmup_Days = 30
        building.Minimum_Number_of_Warmup_Days = 6
        
        idf.newidfobject('HEATBALANCEALGORITHM', 'ConductionTransferFunction')
        
        idf.newidfobject('SURFACECONVECTIONALGORITHM:INSIDE', 'TARP')
        idf.newidfobject('SURFACECONVECTIONALGORITHM:OUTSIDE', 'DOE-2')
        
        geom = idf.newidfobject('GLOBALGEOMETRYRULES')
        geom.Starting_Vertex_Position = 'UpperLeftCorner'
        geom.Vertex_Entry_Direction = 'CounterClockWise'
        geom.Coordinate_System = 'Relative'
        
        site = idf.newidfobject('SITE:LOCATION')
        site.Name = 'Atlanta_Hartsfield_Intl_AP_GA_USA'
        site.Latitude = 33.64
        site.Longitude = -84.43
        site.Time_Zone = -5.0
        site.Elevation = 308.0
        
        design_day = idf.newidfobject('SIZINGPERIOD:DESIGNDAY')
        design_day.Name = 'Atlanta_Summer_Design_Day'
        design_day.Month = 7
        design_day.Day_of_Month = 21
        design_day.Day_Type = 'SummerDesignDay'
        design_day.Maximum_DryBulb_Temperature = 33.3
        design_day.Daily_DryBulb_Temperature_Range = 10.0
        design_day.DryBulb_Temperature_Range_Modifier_Type = 'DefaultMultipliers'
        design_day.Humidity_Condition_Type = 'WetBulb'
        design_day.Wetbulb_or_DewPoint_at_Maximum_DryBulb = 23.9
        design_day.Barometric_Pressure = 98934
        design_day.Wind_Speed = 3.8
        design_day.Wind_Direction = 310
        design_day.Sky_Clearness = 1.0
        
        run_period = idf.newidfobject('RUNPERIOD')
        run_period.Name = 'SingleDay'
        run_period.Begin_Month = 7
        run_period.Begin_Day_of_Month = 21
        run_period.End_Month = 7
        run_period.End_Day_of_Month = 21
        run_period.Day_of_Week_for_Start_Day = 'Monday'
        run_period.Use_Weather_File_Holidays_and_Special_Days = 'No'
        run_period.Use_Weather_File_Daylight_Saving_Period = 'No'
        run_period.Apply_Weekend_Holiday_Rule = 'No'
        run_period.Use_Weather_File_Rain_Indicators = 'Yes'
        run_period.Use_Weather_File_Snow_Indicators = 'Yes'
        
        output_control = idf.newidfobject('OUTPUT:VARIABLEDICTIONARY')
        output_control.Key_Field = 'IDF'
        
        output_table = idf.newidfobject('OUTPUT:TABLE:SUMMARYREPORTS')
        output_table.Report_1_Name = 'AllSummary'
        
        self._add_output_variables(idf)
        
        self._add_schedule_type_limits(idf)
        
        return idf
    
    def _add_schedule_type_limits(self, idf):
        """Add schedule type limits"""
        fraction = idf.newidfobject('SCHEDULETYPELIMITS')
        fraction.Name = 'Fraction'
        fraction.Lower_Limit_Value = 0.0
        fraction.Upper_Limit_Value = 1.0
        fraction.Numeric_Type = 'Continuous'
        
        any_num = idf.newidfobject('SCHEDULETYPELIMITS')
        any_num.Name = 'Any Number'
        
        temp = idf.newidfobject('SCHEDULETYPELIMITS')
        temp.Name = 'Temperature'
        temp.Lower_Limit_Value = -100
        temp.Upper_Limit_Value = 200
        temp.Numeric_Type = 'Continuous'
        temp.Unit_Type = 'Temperature'
    
    def _add_output_variables(self, idf):
        """Add output variables for monitoring"""
        variables = [
            ('Zone Mean Air Temperature', '*'),
            ('Zone Air System Sensible Cooling Rate', '*'),
            ('Zone Air System Sensible Heating Rate', '*'),
            ('Zone ITE CPU Electricity Rate', '*'),
            ('Zone ITE Fan Electricity Rate', '*'),
            ('Zone ITE UPS Electricity Rate', '*'),
            ('Zone ITE Total Heat Gain to Zone Rate', '*'),
            ('Cooling Coil Total Cooling Rate', '*'),
            ('Fan Electricity Rate', '*'),
            ('System Node Temperature', '*'),
            ('System Node Mass Flow Rate', '*'),
        ]
        
        for var_name, key in variables:
            output_var = idf.newidfobject('OUTPUT:VARIABLE')
            output_var.Key_Value = key
            output_var.Variable_Name = var_name
            output_var.Reporting_Frequency = REPORTING_FREQUENCY
    
    def add_zone(self, idf, scenario):
        """Add zone geometry for data center room"""
        room = scenario['room']
        name = scenario['name']
        
        zone = idf.newidfobject('ZONE')
        zone.Name = f'{name}_Zone'
        zone.Direction_of_Relative_North = 0
        zone.X_Origin = 0
        zone.Y_Origin = 0
        zone.Z_Origin = 0
        zone.Type = 1
        zone.Multiplier = 1
        zone.Ceiling_Height = room['height']
        zone.Volume = room['length'] * room['width'] * room['height']
        
        self._add_constructions(idf, scenario)
        
        floor = idf.newidfobject('BUILDINGSURFACE:DETAILED')
        floor.Name = f'{name}_Floor'
        floor.Surface_Type = 'Floor'
        floor.Construction_Name = 'Floor_Construction'
        floor.Zone_Name = zone.Name
        floor.Outside_Boundary_Condition = 'Ground'
        floor.Sun_Exposure = 'NoSun'
        floor.Wind_Exposure = 'NoWind'
        floor.View_Factor_to_Ground = 0
        floor.Number_of_Vertices = 4
        floor.Vertex_1_Xcoordinate = 0
        floor.Vertex_1_Ycoordinate = room['width']
        floor.Vertex_1_Zcoordinate = 0
        floor.Vertex_2_Xcoordinate = room['length']
        floor.Vertex_2_Ycoordinate = room['width']
        floor.Vertex_2_Zcoordinate = 0
        floor.Vertex_3_Xcoordinate = room['length']
        floor.Vertex_3_Ycoordinate = 0
        floor.Vertex_3_Zcoordinate = 0
        floor.Vertex_4_Xcoordinate = 0
        floor.Vertex_4_Ycoordinate = 0
        floor.Vertex_4_Zcoordinate = 0
        
        ceiling = idf.newidfobject('BUILDINGSURFACE:DETAILED')
        ceiling.Name = f'{name}_Ceiling'
        ceiling.Surface_Type = 'Ceiling'
        ceiling.Construction_Name = 'Adiabatic_Construction'
        ceiling.Zone_Name = zone.Name
        ceiling.Outside_Boundary_Condition = 'Adiabatic'
        ceiling.Sun_Exposure = 'NoSun'
        ceiling.Wind_Exposure = 'NoWind'
        ceiling.View_Factor_to_Ground = 0
        ceiling.Number_of_Vertices = 4
        ceiling.Vertex_1_Xcoordinate = 0
        ceiling.Vertex_1_Ycoordinate = 0
        ceiling.Vertex_1_Zcoordinate = room['height']
        ceiling.Vertex_2_Xcoordinate = room['length']
        ceiling.Vertex_2_Ycoordinate = 0
        ceiling.Vertex_2_Zcoordinate = room['height']
        ceiling.Vertex_3_Xcoordinate = room['length']
        ceiling.Vertex_3_Ycoordinate = room['width']
        ceiling.Vertex_3_Zcoordinate = room['height']
        ceiling.Vertex_4_Xcoordinate = 0
        ceiling.Vertex_4_Ycoordinate = room['width']
        ceiling.Vertex_4_Zcoordinate = room['height']
        
        walls = [
            ('North', [(0, room['width'], 0), (0, room['width'], room['height']),
                      (room['length'], room['width'], room['height']), (room['length'], room['width'], 0)]),
            ('East', [(room['length'], room['width'], 0), (room['length'], room['width'], room['height']),
                     (room['length'], 0, room['height']), (room['length'], 0, 0)]),
            ('South', [(room['length'], 0, 0), (room['length'], 0, room['height']),
                      (0, 0, room['height']), (0, 0, 0)]),
            ('West', [(0, 0, 0), (0, 0, room['height']),
                     (0, room['width'], room['height']), (0, room['width'], 0)]),
        ]
        
        for wall_name, vertices in walls:
            wall = idf.newidfobject('BUILDINGSURFACE:DETAILED')
            wall.Name = f'{name}_Wall_{wall_name}'
            wall.Surface_Type = 'Wall'
            if wall_name in ['North', 'South']:
                wall.Construction_Name = 'Wall_Construction'
                wall.Outside_Boundary_Condition = 'Outdoors'
                wall.Sun_Exposure = 'SunExposed'
                wall.Wind_Exposure = 'WindExposed'
            else:
                wall.Construction_Name = 'Adiabatic_Construction'
                wall.Outside_Boundary_Condition = 'Adiabatic'
                wall.Sun_Exposure = 'NoSun'
                wall.Wind_Exposure = 'NoWind'
            wall.Zone_Name = zone.Name
            wall.View_Factor_to_Ground = 0
            wall.Number_of_Vertices = 4
            for i, (x, y, z) in enumerate(vertices, 1):
                setattr(wall, f'Vertex_{i}_Xcoordinate', x)
                setattr(wall, f'Vertex_{i}_Ycoordinate', y)
                setattr(wall, f'Vertex_{i}_Zcoordinate', z)
        
        return zone.Name
    
    def _add_constructions(self, idf, scenario):
        """Add construction and material definitions"""
        try:
            ground_temp = idf.newidfobject('SITE:GROUNDTEMPERATURE:BUILDINGSURFACE')
            for month in ['January', 'February', 'March', 'April', 'May', 'June',
                          'July', 'August', 'September', 'October', 'November', 'December']:
                setattr(ground_temp, f'{month}_Ground_Temperature', 17.0)
        except Exception:
            pass
            
        wall_u = scenario.get('wall_u', 0.19)
        wall_r = 1.0 / wall_u
        
        wall_mat = idf.newidfobject('MATERIAL:NOMASS')
        wall_mat.Name = 'Wall_Material'
        wall_mat.Roughness = 'Smooth'
        wall_mat.Thermal_Resistance = wall_r
        wall_mat.Thermal_Absorptance = 0.9
        wall_mat.Solar_Absorptance = 0.7
        wall_mat.Visible_Absorptance = 0.7
        
        wall_const = idf.newidfobject('CONSTRUCTION')
        wall_const.Name = 'Wall_Construction'
        wall_const.Outside_Layer = 'Wall_Material'
        
        floor_u = scenario.get('floor_u', 0.50)
        floor_r = 1.0 / floor_u
        
        floor_mat = idf.newidfobject('MATERIAL:NOMASS')
        floor_mat.Name = 'Floor_Material'
        floor_mat.Roughness = 'Smooth'
        floor_mat.Thermal_Resistance = floor_r
        floor_mat.Thermal_Absorptance = 0.9
        floor_mat.Solar_Absorptance = 0.7
        floor_mat.Visible_Absorptance = 0.7
        
        floor_const = idf.newidfobject('CONSTRUCTION')
        floor_const.Name = 'Floor_Construction'
        floor_const.Outside_Layer = 'Floor_Material'
        
        construction = idf.newidfobject('CONSTRUCTION')
        construction.Name = 'Adiabatic_Construction'
        construction.Outside_Layer = 'Adiabatic_Material'
        
        material = idf.newidfobject('MATERIAL')
        material.Name = 'Adiabatic_Material'
        material.Roughness = 'Smooth'
        material.Thickness = 0.1
        material.Conductivity = 0.001
        material.Density = 1.0
        material.Specific_Heat = 1000
        material.Thermal_Absorptance = 0.9
        material.Solar_Absorptance = 0.7
        material.Visible_Absorptance = 0.7

    def _create_job_schedule(self, idf, schedule_name, job):
        """Create a compact schedule for a job, supporting midnight wrapping"""
        schedule = idf.newidfobject('SCHEDULE:COMPACT')
        schedule.Name = schedule_name
        schedule.Schedule_Type_Limits_Name = 'Fraction'
        schedule.Field_1 = 'Through: 12/31'
        schedule.Field_2 = 'For: AllDays'
        
        start_hour = int(job['start_hour'])
        duration = float(job.get('duration_hours', job.get('duration', 0.0)))
        end_hour = start_hour + duration
        
        if end_hour > 24.0:
            wrapped_end = int(end_hour - 24.0)
            schedule.Field_3 = f'Until: {wrapped_end:02d}:00'
            schedule.Field_4 = 1.0
            schedule.Field_5 = f'Until: {start_hour:02d}:00'
            schedule.Field_6 = 0.0
            schedule.Field_7 = 'Until: 24:00'
            schedule.Field_8 = 1.0
        else:
            current_field = 3
            if start_hour > 0:
                setattr(schedule, f'Field_{current_field}', f'Until: {start_hour:02d}:00')
                setattr(schedule, f'Field_{current_field+1}', 0.0)
                current_field += 2
            
            end_hour_int = int(end_hour)
            setattr(schedule, f'Field_{current_field}', f'Until: {end_hour_int:02d}:00')
            setattr(schedule, f'Field_{current_field+1}', 1.0)
            current_field += 2
            
            if end_hour_int < 24:
                setattr(schedule, f'Field_{current_field}', 'Until: 24:00')
                setattr(schedule, f'Field_{current_field+1}', 0.0)


    def add_ite_equipment(self, idf, zone_name, scenario):
        """Add ITE (Information Technology Equipment) for server racks"""
        racks = scenario['racks']
        name = scenario['name']
        cooling = scenario['cooling']
        
        dclc_eff = cooling['dclc_effectiveness']
        rdhx_eff = cooling['rdhx_effectiveness']
        
        #Base fraction of heat entering the zone air (not captured by liquid cooling)
        raw_frac_to_air = (1.0 - dclc_eff) * (1.0 - rdhx_eff)
        
        hx = scenario.get('heat_exchangers', {'count': 0, 'capacity_each': 0})
        total_hx_capacity = hx['count'] * hx['capacity_each']
        
        self._add_ite_curves(idf, name)
        
        # Determine if we have dynamic/scheduled jobs or a single static setup
        jobs = scenario.get('schedules', [])
        if not jobs:
            total_power = racks['total_power']
            jobs = [{
                'name': 'ConstantLoad',
                'start_hour': 0,
                'duration_hours': 24,
                'power_level': racks['power_per_rack'] if racks['total_racks'] > 0 else 0,
                'num_racks': racks['total_racks'],
                'total_power': total_power
            }]
            
        for idx, job in enumerate(jobs):
            job_name = f"{name}_{job['name']}_{idx}"
            job_power = job['total_power']
            
            #Calculate fraction to air for this job
            if job_power > 0:
                to_air_before_hx = job_power * raw_frac_to_air
                remaining = max(to_air_before_hx - total_hx_capacity, 0.0)
                frac_to_air = remaining / job_power
            else:
                frac_to_air = 0.0
                
            #Create operation and CPU load schedules for this job
            op_schedule_name = f'{job_name}_OpSchedule'
            cpu_schedule_name = f'{job_name}_CPUSchedule'
            
            self._create_job_schedule(idf, op_schedule_name, job)
            self._create_job_schedule(idf, cpu_schedule_name, job)
            
            ite = idf.newidfobject('ELECTRICEQUIPMENT:ITE:AIRCOOLED')
            ite.Name = f'{job_name}_Servers'
            ite.Zone_or_Space_Name = zone_name
            ite.Air_Flow_Calculation_Method = 'FlowFromSystem'
            ite.Design_Power_Input_Calculation_Method = 'Watts/Unit'
            ite.Watts_per_Unit = job['power_level'] * frac_to_air
            ite.Number_of_Units = job['num_racks']
            ite.Design_Power_Input_Schedule_Name = op_schedule_name
            ite.CPU_Loading_Schedule_Name = cpu_schedule_name
            ite.CPU_Power_Input_Function_of_Loading_and_Air_Temperature_Curve_Name = f'{name}_Power_fLoadTemp'
            ite.Design_Fan_Power_Input_Fraction = 0.4
            ite.Design_Fan_Air_Flow_Rate_per_Power_Input = 0.0001
            ite.Air_Flow_Function_of_Loading_and_Air_Temperature_Curve_Name = f'{name}_Airflow_fLoadTemp'
            ite.Fan_Power_Input_Function_of_Flow_Curve_Name = f'{name}_FanPower_fFlow'
            ite.Design_Entering_Air_Temperature = 15.0
            ite.Environmental_Class = 'A3'
            ite.Air_Inlet_Connection_Type = 'AdjustedSupply'
            ite.Supply_Air_Node_Name = f'{zone_name}_Inlet_Node'
            ite.Design_Recirculation_Fraction = 0.1
            ite.Recirculation_Function_of_Loading_and_Supply_Temperature_Curve_Name = f'{name}_Recirc_fLoadTemp'
            ite.Design_Electric_Power_Supply_Efficiency = 0.9
            ite.Electric_Power_Supply_Efficiency_Function_of_Part_Load_Ratio_Curve_Name = f'{name}_UPS_fPLR'
            ite.Fraction_of_Electric_Power_Supply_Losses_to_Zone = 1.0
            ite.CPU_EndUse_Subcategory = 'ITE-CPU'
            ite.Fan_EndUse_Subcategory = 'ITE-Fans'
            ite.Electric_Power_Supply_EndUse_Subcategory = 'ITE-UPS'
    
    def _add_ite_curves(self, idf, name):
        """Add performance curves for ITE equipment"""
        fan_curve = idf.newidfobject('CURVE:QUADRATIC')
        fan_curve.Name = f'{name}_FanPower_fFlow'
        fan_curve.Coefficient1_Constant = 0.0
        fan_curve.Coefficient2_x = 1.0
        fan_curve.Coefficient3_x2 = 0.0
        fan_curve.Minimum_Value_of_x = 0.0
        fan_curve.Maximum_Value_of_x = 99.0
        
        ups_curve = idf.newidfobject('CURVE:QUADRATIC')
        ups_curve.Name = f'{name}_UPS_fPLR'
        ups_curve.Coefficient1_Constant = 1.0
        ups_curve.Coefficient2_x = 0.0
        ups_curve.Coefficient3_x2 = 0.0
        ups_curve.Minimum_Value_of_x = 0.0
        ups_curve.Maximum_Value_of_x = 99.0
        
        power_curve = idf.newidfobject('CURVE:BIQUADRATIC')
        power_curve.Name = f'{name}_Power_fLoadTemp'
        power_curve.Coefficient1_Constant = -1.0
        power_curve.Coefficient2_x = 1.0
        power_curve.Coefficient3_x2 = 0.0
        power_curve.Coefficient4_y = 0.06667
        power_curve.Coefficient5_y2 = 0.0
        power_curve.Coefficient6_xy = 0.0
        power_curve.Minimum_Value_of_x = 0.0
        power_curve.Maximum_Value_of_x = 1.5
        power_curve.Minimum_Value_of_y = -10.0
        power_curve.Maximum_Value_of_y = 99.0
        
        airflow_curve = idf.newidfobject('CURVE:BIQUADRATIC')
        airflow_curve.Name = f'{name}_Airflow_fLoadTemp'
        airflow_curve.Coefficient1_Constant = -1.4
        airflow_curve.Coefficient2_x = 0.9
        airflow_curve.Coefficient3_x2 = 0.0
        airflow_curve.Coefficient4_y = 0.1
        airflow_curve.Coefficient5_y2 = 0.0
        airflow_curve.Coefficient6_xy = 0.0
        airflow_curve.Minimum_Value_of_x = 0.0
        airflow_curve.Maximum_Value_of_x = 1.5
        airflow_curve.Minimum_Value_of_y = -10.0
        airflow_curve.Maximum_Value_of_y = 99.0
        
        recirc_curve = idf.newidfobject('CURVE:QUADRATIC')
        recirc_curve.Name = f'{name}_Recirc_fLoadTemp'
        recirc_curve.Coefficient1_Constant = 1.0
        recirc_curve.Coefficient2_x = 0.0
        recirc_curve.Coefficient3_x2 = 0.0
        recirc_curve.Minimum_Value_of_x = -10.0
        recirc_curve.Maximum_Value_of_x = 99.0
    
    def _create_constant_schedule(self, idf, name, value):
        """Create a constant schedule"""
        schedule = idf.newidfobject('SCHEDULE:COMPACT')
        schedule.Name = name
        schedule.Schedule_Type_Limits_Name = 'Fraction'
        schedule.Field_1 = 'Through: 12/31'
        schedule.Field_2 = 'For: AllDays'
        schedule.Field_3 = 'Until: 24:00'
        schedule.Field_4 = value
        return name
    
    def add_crac_system(self, idf, zone_name, scenario):
        """Add CRAC (Computer Room Air Conditioning) system"""
        name = scenario['name']
        cooling = scenario['cooling']
        
        total_cfm = cooling['total_cfm']
        airflow_m3s = total_cfm * 0.000471947
        
        avail_schedule = self._create_constant_schedule(idf, f'{name}_System_Avail', 1.0)
        
        sizing_zone = idf.newidfobject('SIZING:ZONE')
        sizing_zone.Zone_or_ZoneList_Name = zone_name
        sizing_zone.Zone_Cooling_Design_Supply_Air_Temperature_Input_Method = 'SupplyAirTemperature'
        sizing_zone.Zone_Cooling_Design_Supply_Air_Temperature = 13.0
        sizing_zone.Zone_Heating_Design_Supply_Air_Temperature_Input_Method = 'SupplyAirTemperature'
        sizing_zone.Zone_Heating_Design_Supply_Air_Temperature = 50.0
        sizing_zone.Zone_Cooling_Design_Supply_Air_Humidity_Ratio = 0.0077
        sizing_zone.Zone_Heating_Design_Supply_Air_Humidity_Ratio = 0.0156
        sizing_zone.Cooling_Design_Air_Flow_Method = 'DesignDay'
        sizing_zone.Cooling_Design_Air_Flow_Rate = 0.0
        sizing_zone.Heating_Design_Air_Flow_Method = 'DesignDay'
        sizing_zone.Heating_Design_Air_Flow_Rate = 0.0
        
        eq_conn = idf.newidfobject('ZONEHVAC:EQUIPMENTCONNECTIONS')
        eq_conn.Zone_Name = zone_name
        eq_conn.Zone_Conditioning_Equipment_List_Name = f'{zone_name}_Equipment'
        eq_conn.Zone_Air_Inlet_Node_or_NodeList_Name = f'{zone_name}_Inlet_Node'
        eq_conn.Zone_Air_Node_Name = f'{zone_name}_Air_Node'
        eq_conn.Zone_Air_Exhaust_Node_or_NodeList_Name = f'{zone_name}_Return_Outlet'
        
        eq_list = idf.newidfobject('ZONEHVAC:EQUIPMENTLIST')
        eq_list.Name = f'{zone_name}_Equipment'
        eq_list.Load_Distribution_Scheme = 'SequentialLoad'
        eq_list.Zone_Equipment_1_Object_Type = 'ZoneHVAC:PackagedTerminalAirConditioner'
        eq_list.Zone_Equipment_1_Name = f'{name}_PTAC'
        eq_list.Zone_Equipment_1_Cooling_Sequence = 1
        eq_list.Zone_Equipment_1_Heating_or_NoLoad_Sequence = 1
        
        ptac = idf.newidfobject('ZONEHVAC:PACKAGEDTERMINALAIRCONDITIONER')
        ptac.Name = f'{name}_PTAC'
        ptac.Availability_Schedule_Name = avail_schedule
        ptac.Air_Inlet_Node_Name = f'{zone_name}_Return_Outlet'
        ptac.Air_Outlet_Node_Name = f'{zone_name}_Inlet_Node'
        ptac.Cooling_Supply_Air_Flow_Rate = airflow_m3s
        ptac.Heating_Supply_Air_Flow_Rate = airflow_m3s
        ptac.No_Load_Supply_Air_Flow_Rate = airflow_m3s
        ptac.Cooling_Outdoor_Air_Flow_Rate = 0.0
        ptac.Heating_Outdoor_Air_Flow_Rate = 0.0
        ptac.No_Load_Outdoor_Air_Flow_Rate = 0.0
        ptac.Supply_Air_Fan_Object_Type = 'Fan:OnOff'
        ptac.Supply_Air_Fan_Name = f'{name}_Supply_Fan'
        ptac.Heating_Coil_Object_Type = 'Coil:Heating:Electric'
        ptac.Heating_Coil_Name = f'{name}_Heating_Coil'
        ptac.Cooling_Coil_Object_Type = 'Coil:Cooling:DX:SingleSpeed'
        ptac.Cooling_Coil_Name = f'{name}_DX_Coil'
        ptac.Fan_Placement = 'DrawThrough'
        
        ht_coil = idf.newidfobject('COIL:HEATING:ELECTRIC')
        ht_coil.Name = f'{name}_Heating_Coil'
        ht_coil.Availability_Schedule_Name = avail_schedule
        ht_coil.Efficiency = 1.0
        ht_coil.Nominal_Capacity = 0.0
        ht_coil.Air_Inlet_Node_Name = f'{name}_Cooling_Coil_Outlet'
        ht_coil.Air_Outlet_Node_Name = f'{name}_Heating_Coil_Outlet'
        
        dx_coil = idf.newidfobject('COIL:COOLING:DX:SINGLESPEED')
        dx_coil.Name = f'{name}_DX_Coil'
        dx_coil.Availability_Schedule_Name = avail_schedule
        dx_coil.Gross_Rated_Total_Cooling_Capacity = 'autosize'
        dx_coil.Gross_Rated_Sensible_Heat_Ratio = 0.75
        dx_coil.Gross_Rated_Cooling_COP = 3.0
        dx_coil.Rated_Air_Flow_Rate = airflow_m3s
        dx_coil.Air_Inlet_Node_Name = f'{zone_name}_Return_Outlet'
        dx_coil.Air_Outlet_Node_Name = f'{name}_Cooling_Coil_Outlet'
        
        self._add_dx_curves(idf, name)
        dx_coil.Total_Cooling_Capacity_Function_of_Temperature_Curve_Name = f'{name}_CoolCapFT'
        dx_coil.Total_Cooling_Capacity_Function_of_Flow_Fraction_Curve_Name = f'{name}_CoolCapFFF'
        dx_coil.Energy_Input_Ratio_Function_of_Temperature_Curve_Name = f'{name}_EIRFT'
        dx_coil.Energy_Input_Ratio_Function_of_Flow_Fraction_Curve_Name = f'{name}_EIRFFF'
        dx_coil.Part_Load_Fraction_Correlation_Curve_Name = f'{name}_PLFFPLR'
        
        fan = idf.newidfobject('FAN:ONOFF')
        fan.Name = f'{name}_Supply_Fan'
        fan.Availability_Schedule_Name = avail_schedule
        fan.Fan_Total_Efficiency = 0.7
        fan.Pressure_Rise = 600
        fan.Maximum_Flow_Rate = airflow_m3s
        fan.Motor_Efficiency = 0.9
        fan.Motor_In_Airstream_Fraction = 1.0
        fan.Air_Inlet_Node_Name = f'{name}_Heating_Coil_Outlet'
        fan.Air_Outlet_Node_Name = f'{zone_name}_Inlet_Node'
        
        self._add_thermostat(idf, name, zone_name, scenario)
    
    def _add_dx_curves(self, idf, name):
        """Add DX coil performance curves"""
        cap_ft = idf.newidfobject('CURVE:BIQUADRATIC')
        cap_ft.Name = f'{name}_CoolCapFT'
        cap_ft.Coefficient1_Constant = 0.942587793
        cap_ft.Coefficient2_x = 0.009543347
        cap_ft.Coefficient3_x2 = 0.000683770
        cap_ft.Coefficient4_y = -0.011042676
        cap_ft.Coefficient5_y2 = 0.000005249
        cap_ft.Coefficient6_xy = -0.000009720
        cap_ft.Minimum_Value_of_x = 17.0
        cap_ft.Maximum_Value_of_x = 22.0
        cap_ft.Minimum_Value_of_y = 13.0
        cap_ft.Maximum_Value_of_y = 46.0
        
        cap_fff = idf.newidfobject('CURVE:QUADRATIC')
        cap_fff.Name = f'{name}_CoolCapFFF'
        cap_fff.Coefficient1_Constant = 0.8
        cap_fff.Coefficient2_x = 0.2
        cap_fff.Coefficient3_x2 = 0.0
        cap_fff.Minimum_Value_of_x = 0.5
        cap_fff.Maximum_Value_of_x = 1.5
        
        eir_ft = idf.newidfobject('CURVE:BIQUADRATIC')
        eir_ft.Name = f'{name}_EIRFT'
        eir_ft.Coefficient1_Constant = 0.342414409
        eir_ft.Coefficient2_x = 0.034885008
        eir_ft.Coefficient3_x2 = -0.000623700
        eir_ft.Coefficient4_y = 0.004977216
        eir_ft.Coefficient5_y2 = 0.000437951
        eir_ft.Coefficient6_xy = -0.000728028
        eir_ft.Minimum_Value_of_x = 17.0
        eir_ft.Maximum_Value_of_x = 22.0
        eir_ft.Minimum_Value_of_y = 13.0
        eir_ft.Maximum_Value_of_y = 46.0
        
        eir_fff = idf.newidfobject('CURVE:QUADRATIC')
        eir_fff.Name = f'{name}_EIRFFF'
        eir_fff.Coefficient1_Constant = 1.1552
        eir_fff.Coefficient2_x = -0.1808
        eir_fff.Coefficient3_x2 = 0.0256
        eir_fff.Minimum_Value_of_x = 0.5
        eir_fff.Maximum_Value_of_x = 1.5
        
        plf = idf.newidfobject('CURVE:QUADRATIC')
        plf.Name = f'{name}_PLFFPLR'
        plf.Coefficient1_Constant = 0.85
        plf.Coefficient2_x = 0.15
        plf.Coefficient3_x2 = 0.0
        plf.Minimum_Value_of_x = 0.0
        plf.Maximum_Value_of_x = 1.0
    
    
    def _add_thermostat(self, idf, name, zone_name, scenario):
        target_temp = scenario.get('target_temp', 24.0)
        
        thermostat = idf.newidfobject('ZONECONTROL:THERMOSTAT')
        thermostat.Name = f'{zone_name}_Thermostat'
        thermostat.Zone_or_ZoneList_Name = zone_name
        thermostat.Control_Type_Schedule_Name = f'{name}_Control_Type'
        thermostat.Control_1_Object_Type = 'ThermostatSetpoint:DualSetpoint'
        thermostat.Control_1_Name = f'{name}_DualSetpoint'
        
        control_sched = idf.newidfobject('SCHEDULE:COMPACT')
        control_sched.Name = f'{name}_Control_Type'
        control_sched.Schedule_Type_Limits_Name = 'Any Number'
        control_sched.Field_1 = 'Through: 12/31'
        control_sched.Field_2 = 'For: AllDays'
        control_sched.Field_3 = 'Until: 24:00'
        control_sched.Field_4 = 4
        
        dual_setpoint = idf.newidfobject('THERMOSTATSETPOINT:DUALSETPOINT')
        dual_setpoint.Name = f'{name}_DualSetpoint'
        dual_setpoint.Heating_Setpoint_Temperature_Schedule_Name = f'{name}_Heating_Setpoint'
        dual_setpoint.Cooling_Setpoint_Temperature_Schedule_Name = f'{name}_Cooling_Setpoint'
        
        heat_sched = idf.newidfobject('SCHEDULE:COMPACT')
        heat_sched.Name = f'{name}_Heating_Setpoint'
        heat_sched.Schedule_Type_Limits_Name = 'Temperature'
        heat_sched.Field_1 = 'Through: 12/31'
        heat_sched.Field_2 = 'For: AllDays'
        heat_sched.Field_3 = 'Until: 24:00'
        heat_sched.Field_4 = 15.0
        
        cool_sched = idf.newidfobject('SCHEDULE:COMPACT')
        cool_sched.Name = f'{name}_Cooling_Setpoint'
        cool_sched.Schedule_Type_Limits_Name = 'Temperature'
        cool_sched.Field_1 = 'Through: 12/31'
        cool_sched.Field_2 = 'For: AllDays'
        cool_sched.Field_3 = 'Until: 24:00'
        cool_sched.Field_4 = target_temp + 5.0
    
    def generate_scenario_from_dict(self, scenario, filepath):
        """Generate detailed IDF file for a scenario dictionary directly"""
        idf = self.create_base_idf()
        zone_name = self.add_zone(idf, scenario)
        self.add_ite_equipment(idf, zone_name, scenario)
        self.add_crac_system(idf, zone_name, scenario)
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        idf.saveas(str(filepath))
        return filepath
        
    def generate_scenario(self, scenario_num):
        """Generate detailed IDF file for a specific scenario"""
        scenario = SCENARIOS[scenario_num]
        print(f"\nGenerating Detailed Scenario {scenario_num}: {scenario['name']}")
        print(f"Description: {scenario['description']}")
        
        output_dir = Path('model/scenarios')
        output_file = output_dir / f'scenario_{scenario_num}_{scenario["name"]}_detailed.idf'
        self.generate_scenario_from_dict(scenario, output_file)
        
        print(f"Generated: {output_file}")
        return output_file
    
    def generate_all_scenarios(self):
        print("Detailed IDF Generator for ATL01 Data Center")
        
        output_files = []
        for scenario_num in SCENARIOS.keys():
            output_file = self.generate_scenario(scenario_num)
            output_files.append(output_file)
        
        print(f"Successfully generated {len(output_files)} detailed IDF files")
        
        return output_files


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate EnergyPlus IDF files for data center scenarios')
    parser.add_argument('--mode', choices=['simplified', 'detailed', 'both'], default='simplified',
                       help='Generation mode: simplified (ideal loads), detailed (CRAC system), or both')
    parser.add_argument('--scenario', type=int, choices=[1, 2, 3, 4, 5],
                       help='Generate specific scenario only (1-5)')
    
    args = parser.parse_args()
    
    print("EnergyPlus IDF Generator for ATL01 Data Center")
    
    if args.mode in ['simplified', 'both']:
        print("\nSimplified Generator (Ideal Loads)")
        simplified_gen = SimplifiedIDFGenerator(ENERGYPLUS_PATH)
        if args.scenario:
            simplified_gen.generate_scenario(args.scenario)
        else:
            simplified_gen.generate_all_scenarios()
    
    if args.mode in ['detailed', 'both']:
        print("\nDetailed Generator (CRAC System)")
        detailed_gen = DetailedIDFGenerator(ENERGYPLUS_PATH)
        if args.scenario:
            detailed_gen.generate_scenario(args.scenario)
        else:
            detailed_gen.generate_all_scenarios()
    
    print("Generation complete!")


if __name__ == '__main__':
    main()
