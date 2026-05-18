# -*- coding: utf-8 -*-
"""
Module Name: pfs_heatpump_plotting.py
Description:
    

Functions:
    - 
    

Usage:
    This module is intended to be imported and used by 
    `power_flow_sim.py`. It is not designed to be executed directly.

Author: Luis F. Victor Gallardo
Date: 2024/03/21
Version: 0.1
"""

def write_simulation_results_to_csv(
    filename, dict_temp_powers, dict_temp_power_data, 
    dict_temp_power_data_rating, dict_temp_voltage_data, 
    start_timestamp):

    import csv
    from datetime import datetime, timedelta
    from copy import deepcopy
    import sys

    # Writing to csv
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
    
        # Write the header
        writer.writerow(['Timeslice', 'Timestamp', 'P1', 'Q1', 'P2', 'Q2', 'P3', 'Q3', 'Element', 'Element_Type', 'Element_Detail', 'Rating', 'Apparent power', 'Order_ID', 'Order_ID_individual',
                         'V1', 'Ang1', 'V1_pu', 'V2', 'Ang2', 'V2_pu', 'V3', 'Ang3', 'V3_pu', 'Voltage_Condition'])

        # Empty voltages
        empt_volt_list = ['']*len(['V1', 'Ang1', 'V1_pu', 'V2', 'Ang2', 'V2_pu', 'V3', 'Ang3', 'V3_pu', 'Voltage_Condition'])

        general_power_list = []

        # Write the data 1
        for index, (timeslice, powers) in enumerate(dict_temp_powers.items()):
            timestamp = start_timestamp + timedelta(minutes=15 * index)
            writer.writerow([timeslice, timestamp.strftime('%H:%M')] + list(powers[:6]) + ['Main', 'Main', 'Main', '-', '-', '-', '-'])

            general_power = list(powers[:6])[0] + list(powers[:6])[2] + list(powers[:6])[4]
            general_power_list.append(general_power)

        general_power_list_sorted = deepcopy(general_power_list)
        general_power_list_sorted.sort(reverse=True)
        general_power_list_sorted_oi = [general_power_list.index(i) for i in general_power_list_sorted]

        # print('check sort')
        # sys.exit()

        dict_temp_power_data_per_element = {}
        element_list = []

        # Write the data 2
        for index, (timeslice, grab_power_data) in enumerate(dict_temp_power_data.items()):
            timestamp = start_timestamp + timedelta(minutes=15 * index)
            for an_element in list(grab_power_data.keys()):
                if 'Transformer' in an_element:
                    element_type = 'Transformer'
                    this_rating = dict_temp_power_data_rating[timeslice][an_element]['rated_kva']
                    this_apparent_power = dict_temp_power_data_rating[timeslice][an_element]['total_apparent_power']
                elif 'Line' in an_element:
                    element_type = 'Line'
                    this_rating = '-'
                    this_apparent_power = '+'
                else:
                    print('Element Not defined', an_element)
                    sys.exit()
                get_tuple = grab_power_data[an_element]

                tuple_size = len(get_tuple)
                if (tuple_size == 12 and 'Line' in an_element) or (tuple_size == 16 and 'Transformer' in an_element):
                    element_detail = 'Three-phase'
                    writer.writerow([timeslice, timestamp.strftime('%H:%M')] + list(get_tuple[:6]) + [an_element, element_type, element_detail, this_rating, this_apparent_power, '-', '-'] + empt_volt_list)
                elif (tuple_size == 8 and 'Line' in an_element) or (tuple_size == 12 and 'Transformer' in an_element):
                    element_detail = 'Single-phase'
                    writer.writerow([timeslice, timestamp.strftime('%H:%M')] + list(get_tuple[:4]) + [0, 0] + [an_element, element_type, element_detail, this_rating, this_apparent_power, '-', '-'] + empt_volt_list)
                else:
                    print('Element Detail Not defined', tuple_size)
                    sys.exit()

                # Take advantage of this loop to invert the elements
                if an_element not in element_list:
                    element_list.append(an_element)
                    dict_temp_power_data_per_element.update({an_element:{}})

                dict_temp_power_data_per_element[an_element].update({timeslice:deepcopy(get_tuple)})

        for index, (timeslice, grab_voltage_data) in enumerate(dict_temp_voltage_data.items()):
            element_type = 'Load'
            timestamp = start_timestamp + timedelta(minutes=15 * index)
            for an_element in list(grab_voltage_data.keys()):
                this_volt_condition = grab_voltage_data[an_element]['condition']
                volt_mag = grab_voltage_data[an_element]['voltage_magnitude']
                volt_ang = grab_voltage_data[an_element]['voltage_angle']
                volt_mag_pu = grab_voltage_data[an_element]['voltage_magnitude_pu']

                empty_powers = ['']*6
                this_volt_condition_list_1 = [volt_mag[0], volt_ang[0], volt_mag_pu[0]]

                if len(volt_mag) == 3:
                    element_detail = 'Three-phase'
                    this_volt_condition_list_2 = [volt_mag[1], volt_ang[1], volt_mag_pu[1]]
                    this_volt_condition_list_3 = [volt_mag[2], volt_ang[2], volt_mag_pu[2]]
                elif len(volt_mag) == 1:
                    element_detail = 'Single-phase'
                    this_volt_condition_list_2 = ['']*3
                    this_volt_condition_list_3 = ['']*3
                else:
                    print('Line type is not defined!')
                    sys.exit()

                this_volt_condition_list_all = \
                    this_volt_condition_list_1 + this_volt_condition_list_2 + \
                    this_volt_condition_list_3 + [this_volt_condition]

                writer.writerow([timeslice, timestamp.strftime('%H:%M')] + empty_powers + [an_element, element_type, element_detail, '-', '-', '-', '-'] + this_volt_condition_list_all)

        # Write the data 3
        counter_normal = 0
        for index in general_power_list_sorted_oi:
            powers = dict_temp_powers[index+1]
            writer.writerow(['-', '-'] + list(powers[:6]) + ['Main', 'Main', 'Main', '-', '-', counter_normal])
            counter_normal += 1

        # print('check the printing order elements here')
        # sys.exit()

        # Write the data 4
        counter_normal = 0
        for index in general_power_list_sorted_oi:
            grab_power_data = dict_temp_power_data[index+1]
            for an_element in list(grab_power_data.keys()):
                if 'Transformer' in an_element:
                    element_type = 'Transformer'
                    this_rating = dict_temp_power_data_rating[index+1][an_element]['rated_kva']
                    this_apparent_power = dict_temp_power_data_rating[index+1][an_element]['total_apparent_power']
                elif 'Line' in an_element:
                    element_type = 'Line'
                    this_rating = '-'
                    this_apparent_power = '+'
                else:
                    print('Element Not defined', an_element)
                    sys.exit()
                get_tuple = grab_power_data[an_element]
    
                tuple_size = len(get_tuple)
                if (tuple_size == 12 and 'Line' in an_element) or (tuple_size == 16 and 'Transformer' in an_element):
                    element_detail = 'Three-phase'
                    writer.writerow(['-', '-'] + list(get_tuple[:6]) + [an_element, element_type, element_detail, this_rating, this_apparent_power, counter_normal, '-'] + empt_volt_list)
                elif (tuple_size == 8 and 'Line' in an_element) or (tuple_size == 12 and 'Transformer' in an_element):
                    element_detail = 'Single-phase'
                    writer.writerow(['-', '-'] + list(get_tuple[:4]) + [0, 0] + [an_element, element_type, element_detail, this_rating, this_apparent_power, counter_normal, '-'] + empt_volt_list)
                else:
                    print('Element Detail Not defined', tuple_size)
                    sys.exit()

            counter_normal += 1

        # Write the data 5 // this must give me load duration curves per circuit
        for an_element in element_list:
            time_slice_all = [i for i in range(1,96+1)]
            power_list = []
            for t in time_slice_all:
                loc_powers = dict_temp_power_data_per_element[an_element][t]
                get_tuple = dict_temp_power_data_per_element[an_element][t]
                tuple_size = len(get_tuple)
                if (tuple_size == 12 and 'Line' in an_element):
                    power_list.append(list(loc_powers[:6])[0] + list(loc_powers[:6])[2] + list(loc_powers[:6])[4])
                elif (tuple_size == 16 and 'Transformer' in an_element):
                    power_list.append(list(loc_powers[:6])[0] + list(loc_powers[:6])[2] + list(loc_powers[:6])[4])
                elif (tuple_size == 8 and 'Line' in an_element):
                    power_list.append(list(loc_powers[:6])[0] + list(loc_powers[:6])[2])
                elif (tuple_size == 12 and 'Transformer' in an_element):
                    power_list.append(list(loc_powers[:6])[0] + list(loc_powers[:6])[2])
                else:
                    print('Element Detail Not defined (0)', tuple_size)
                    sys.exit()
            power_list_sorted = deepcopy(power_list)
            power_list_sorted.sort(reverse=True)
            power_list_sorted_oi = [power_list.index(i) + 1 for i in power_list_sorted]

            counter_normal_inner = 0
            for index in power_list_sorted_oi:
                if 'Transformer' in an_element:
                    element_type = 'Transformer'
                    this_rating = dict_temp_power_data_rating[index][an_element]['rated_kva']
                    this_apparent_power = dict_temp_power_data_rating[index][an_element]['total_apparent_power']
                elif 'Line' in an_element:
                    element_type = 'Line'
                    this_rating = '-'
                    this_apparent_power = '+'
                else:
                    print('Element Not defined', an_element)
                    sys.exit()
                get_tuple = dict_temp_power_data_per_element[an_element][index]

                tuple_size = len(get_tuple)
                if (tuple_size == 12 and 'Line' in an_element) or (tuple_size == 16 and 'Transformer' in an_element):
                    element_detail = 'Three-phase'
                    writer.writerow(['-', '-'] + list(get_tuple[:6]) + [an_element, element_type, element_detail, this_rating, this_apparent_power, '-', counter_normal_inner] + empt_volt_list)
                elif (tuple_size == 8 and 'Line' in an_element) or (tuple_size == 12 and 'Transformer' in an_element):
                    element_detail = 'Single-phase'
                    writer.writerow(['-', '-'] + list(get_tuple[:4]) + [0, 0] + [an_element, element_type, element_detail, this_rating, this_apparent_power, '-', counter_normal_inner] + empt_volt_list)
                else:
                    print('Element Detail Not defined', tuple_size)
                    sys.exit()

                counter_normal_inner += 1

            #if 'Transformer' in an_element and '2937' in an_element:
            #    print('review grid')
            #    sys.exit()


