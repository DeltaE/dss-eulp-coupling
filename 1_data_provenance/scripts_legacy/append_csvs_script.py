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
    'out.qoi.minimum_daily_peak_sep..kw'
]

# List of columns for residential files
residential_columns = [
    'bldg_id', 'upgrade', 'in.sqft', 'in.area_median_income', 'in.building_america_climate_zone',
    'in.city', 'in.county', 
    'in.electric_vehicle', 'in.geometry_stories', 'in.heating_fuel', 'in.heating_setpoint', 
    'in.heating_setpoint_has_offset', 'in.heating_setpoint_offset_magnitude', 
    'in.heating_setpoint_offset_period', 'in.hvac_cooling_efficiency', 
    'in.hvac_cooling_partial_space_conditioning', 'in.hvac_cooling_type', 
    'in.hvac_heating_efficiency', 'in.hvac_heating_type', 'in.hvac_heating_type_and_fuel', 
    'in.hvac_secondary_heating_efficiency', 'in.hvac_secondary_heating_fuel', 
    'in.hvac_secondary_heating_partial_space_conditioning', 'in.income', 'in.occupants', 
    'in.plug_load_diversity', 'in.plug_loads', 'in.water_heater_efficiency', 
    'in.water_heater_fuel', 'out.params.size_cooling_system_primary_k_btu_h', 
    'out.params.size_heat_pump_backup_primary_k_btu_h', 'out.params.size_heating_system_primary_k_btu_h', 
    'out.params.size_heating_system_secondary_k_btu_h', 'out.params.size_water_heater_gal', 
    'out.electricity.heating.energy_consumption.kwh', 'out.electricity.heating_fans_pumps.energy_consumption.kwh', 
    'out.electricity.heating_hp_bkup.energy_consumption.kwh', 
    'out.electricity.heating_hp_bkup_fa.energy_consumption.kwh', 
    'out.electricity.hot_water.energy_consumption.kwh', 'out.electricity.summer.peak.kw', 
    'out.electricity.total.energy_consumption.kwh', 'out.electricity.winter.peak.kw', 
    'out.fuel_oil.heating.energy_consumption.kwh', 'out.fuel_oil.heating_hp_bkup.energy_consumption.kwh', 
    'out.fuel_oil.hot_water.energy_consumption.kwh', 'out.fuel_oil.total.energy_consumption.kwh', 
    'out.natural_gas.heating.energy_consumption.kwh', 'out.natural_gas.heating_hp_bkup.energy_consumption.kwh', 
    'out.natural_gas.hot_water.energy_consumption.kwh', 'out.natural_gas.total.energy_consumption.kwh', 
    'out.propane.heating.energy_consumption.kwh', 'out.propane.heating_hp_bkup.energy_consumption.kwh', 
    'out.propane.hot_water.energy_consumption.kwh', 'out.propane.total.energy_consumption.kwh', 
    'out.site_energy.total.energy_consumption.kwh', 'out.load.cooling.energy_delivered.kbtu', 
    'out.load.cooling.peak.kbtu_hr', 'out.load.heating.energy_delivered.kbtu', 
    'out.load.heating.peak.kbtu_hr', 'out.load.hot_water.energy_delivered.kbtu'
]

# Create two lists to hold dataframes: one for commercial and one for residential
commercial_dataframes = []
residential_dataframes = []

# Traverse through all folders and subfolders
for foldername, subfolders, filenames in os.walk('.'):  # Use '.' to refer to the current directory
    for filename in filenames:
        if filename.endswith('.csv'):
            file_path = os.path.join(foldername, filename)
            
            # Determine if the folder is for commercial or residential files
            if 'Commercial' in foldername:
                # Read commercial CSV with the relevant columns
                df = pd.read_csv(file_path, usecols=commercial_columns)
                df['Folder_File'] = f"{os.path.basename(foldername)}_{filename}"
                commercial_dataframes.append(df)
            elif 'Residential' in foldername:
                # Read residential CSV with the relevant columns
                df = pd.read_csv(file_path, usecols=residential_columns)
                df['Folder_File'] = f"{os.path.basename(foldername)}_{filename}"
                residential_dataframes.append(df)

# print('check this')
# sys.exit()

# Concatenate all commercial dataframes
if commercial_dataframes:
    commercial_dataframe = pd.concat(commercial_dataframes, ignore_index=True)
    print("Commercial Data:")
    commercial_dataframe.to_csv('commercial_data.csv', index=False)
    # print(commercial_dataframe)

# Concatenate all residential dataframes
if residential_dataframes:
    residential_dataframe = pd.concat(residential_dataframes, ignore_index=True)
    print("Residential Data:")
    residential_dataframe.to_csv('residential_data.csv', index=False)
    # print(residential_dataframe)

