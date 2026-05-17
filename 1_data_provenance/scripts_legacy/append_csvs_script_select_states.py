# -*- coding: utf-8 -*-
"""
Created on Thu Oct 10 23:12:34 2024

@author: luisfernando
"""

import os
import pandas as pd
import sys

# List of columns for commercial files
commercial_columns = [
    'bldg_id', 'upgrade', 'in.sqft', 'in.building_america_climate_zone', 'in.state', 
    'in.state_name', 'in.building_subtype', 'in.comstock_building_type', 
    'in.comstock_building_type_group', 'in.floor_area_category', 'in.heating_fuel', 
    'in.hvac_category', 'in.hvac_combined_type', 'in.hvac_cool_type', 
    'in.hvac_heat_type', 'in.hvac_night_variability', 'in.hvac_system_type', 
    'in.hvac_vent_type', 'in.interior_lighting_generation', 'in.number_of_stories', 
    'in.number_stories', 'in.year_built', 'out.district_cooling.cooling.energy_consumption', 
    'out.district_cooling.total.energy_consumption', 'out.district_heating.cooling.energy_consumption', 
    'out.district_heating.heating.energy_consumption', 'out.district_heating.total.energy_consumption', 
    'out.district_heating.water_systems.energy_consumption', 
    'out.electricity.cooling.energy_consumption', 'out.electricity.exterior_lighting.energy_consumption', 
    'out.electricity.fans.energy_consumption', 'out.electricity.heat_recovery.energy_consumption', 
    'out.electricity.heat_rejection.energy_consumption', 'out.electricity.heating.energy_consumption', 
    'out.electricity.interior_equipment.energy_consumption', 
    'out.electricity.interior_lighting.energy_consumption', 'out.electricity.pumps.energy_consumption', 
    'out.electricity.refrigeration.energy_consumption', 'out.electricity.total.apr.energy_consumption..kwh', 
    'out.electricity.total.aug.energy_consumption..kwh', 'out.electricity.total.dec.energy_consumption..kwh', 
    'out.electricity.total.energy_consumption', 'out.electricity.total.feb.energy_consumption..kwh', 
    'out.electricity.total.jan.energy_consumption..kwh', 'out.electricity.total.jul.energy_consumption..kwh', 
    'out.electricity.total.jun.energy_consumption..kwh', 'out.electricity.total.mar.energy_consumption..kwh', 
    'out.electricity.total.may.energy_consumption..kwh', 'out.electricity.total.nov.energy_consumption..kwh', 
    'out.electricity.total.oct.energy_consumption..kwh', 'out.electricity.total.sep.energy_consumption..kwh', 
    'out.electricity.water_systems.energy_consumption', 'out.natural_gas.heating.energy_consumption', 
    'out.natural_gas.interior_equipment.energy_consumption', 'out.natural_gas.total.energy_consumption', 
    'out.natural_gas.water_systems.energy_consumption', 'out.other_fuel.cooling.energy_consumption', 
    'out.other_fuel.heating.energy_consumption', 'out.other_fuel.total.energy_consumption', 
    'out.other_fuel.water_systems.energy_consumption', 'out.site_energy.total.energy_consumption', 
    'out.electricity.total.peak_demand', 'out.qoi.maximum_daily_peak_apr..kw', 
    'out.qoi.maximum_daily_peak_aug..kw', 'out.qoi.maximum_daily_peak_dec..kw', 
    'out.qoi.maximum_daily_peak_feb..kw', 'out.qoi.maximum_daily_peak_jan..kw', 
    'out.qoi.maximum_daily_peak_jul..kw', 'out.qoi.maximum_daily_peak_jun..kw', 
    'out.qoi.maximum_daily_peak_mar..kw', 'out.qoi.maximum_daily_peak_may..kw', 
    'out.qoi.maximum_daily_peak_nov..kw', 'out.qoi.maximum_daily_peak_oct..kw', 
    'out.qoi.maximum_daily_peak_sep..kw', 'out.qoi.median_daily_peak_apr..kw', 
    'out.qoi.median_daily_peak_aug..kw', 'out.qoi.median_daily_peak_dec..kw', 
    'out.qoi.median_daily_peak_feb..kw', 'out.qoi.median_daily_peak_jan..kw', 
    'out.qoi.median_daily_peak_jul..kw', 'out.qoi.median_daily_peak_jun..kw', 
    'out.qoi.median_daily_peak_mar..kw', 'out.qoi.median_daily_peak_may..kw', 
    'out.qoi.median_daily_peak_nov..kw', 'out.qoi.median_daily_peak_oct..kw', 
    'out.qoi.median_daily_peak_sep..kw', 'out.qoi.minimum_daily_peak_apr..kw', 
    'out.qoi.minimum_daily_peak_aug..kw', 'out.qoi.minimum_daily_peak_dec..kw', 
    'out.qoi.minimum_daily_peak_feb..kw', 'out.qoi.minimum_daily_peak_jan..kw', 
    'out.qoi.minimum_daily_peak_jul..kw', 'out.qoi.minimum_daily_peak_jun..kw', 
    'out.qoi.minimum_daily_peak_mar..kw', 'out.qoi.minimum_daily_peak_may..kw', 
    'out.qoi.minimum_daily_peak_nov..kw', 'out.qoi.minimum_daily_peak_oct..kw', 
    'out.qoi.minimum_daily_peak_sep..kw',
    'applicability',
    'out.qoi.maximum_daily_use_shoulder..kw',
    'out.qoi.maximum_daily_use_summer..kw',
    'out.qoi.maximum_daily_use_winter..kw',
    'out.qoi.minimum_daily_use_shoulder..kw',
    'out.qoi.minimum_daily_use_summer..kw',
    'out.qoi.minimum_daily_use_winter..kw',
    'in.economizer_changeover_temperature_fault_applicable',
    'out.params.area_fraction_with_supply_air_temperature_reset',
    'out.params.dx_heating_average_minimum_operating_temperature..c',
    'out.params.economizer_high_limit_temperature..c',
    'out.params.fluid_hx_demand_inlet_temp..c',
    'out.params.fluid_hx_demand_outlet_temp..c',
    'out.params.fluid_hx_supply_inlet_temp..c',
    'out.params.fluid_hx_supply_outlet_temp..c',
    'out.params.heat_pump_cooling_source_inlet_temp..c',
    'out.params.heat_pump_heating_source_inlet_temp..c',
    'out.params.vrf_temperature_type',
    'in.service_water_heating_fuel'
]

# Create two lists to hold dataframes: one for commercial and one for residential
commercial_dataframes = []

# Filter to focus on some states:
allowed_subfolders = [i for i in os.listdir() if ('Commercial' in i) and
                      ('CA' in i or 'TX' in i or 'NC' in i or
                      'MN' in i or 'FL' in i or 'NY' in i or 'MI' in i) and
                      ('_2' not in i)]

# Traverse through the allowed subfolders
for folder in allowed_subfolders:
    folder_path = os.path.join('.', folder)  # Construct the folder path
    
    # List all 'baseline.csv' files in the folder
    csv_files = [i for i in os.listdir(folder_path) if 'baseline' in i] # glob.glob(os.path.join(folder_path, 'baseline.csv'))
    
    for a_file in csv_files:
        file_path = os.path.join('.', folder, a_file)
        print(f"Processing file: {file_path}")  # Debugging output

        # Read commercial CSV with the relevant columns
        df = pd.read_csv(file_path, usecols=commercial_columns)  # Update columns as needed
        # df = pd.read_csv(file_path)
        df['Folder_File'] = f"{os.path.basename(folder_path)}_baseline.csv"

        # print('get up to here')
        # sys.exit()

        commercial_dataframes.append(df)

# Combine all dataframes into a single one, if applicable
if commercial_dataframes:
    combined_df = pd.concat(commercial_dataframes, ignore_index=True)
    combined_df.to_csv('combined_commercial_data.csv', index=False)

print("Processing complete!")


