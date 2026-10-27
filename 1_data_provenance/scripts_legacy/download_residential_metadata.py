import sys
import os
import time
from copy import deepcopy

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By

import pandas as pd

# Function to chunk a list into smaller pieces
def chunk_list(lst, chunk_size):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def download_any_files(any_file_urls, target_directory):
    # Ensure target directory exists
    os.makedirs(target_directory, exist_ok=True)

    for url in any_file_urls:
        # Extract filename from URL or generate your own naming scheme
        filename = url.split('/')[-1]  # This gets the last part of the URL as the filename
        
        # Define the full path where the file will be saved
        file_path = os.path.join(target_directory, filename)
        
        # Download and save the file
        response = requests.get(url)
        if response.status_code == 200:  # Successful download
            with open(file_path, 'wb') as file:
                file.write(response.content)
            print(f"Downloaded {filename} to {file_path}")
        else:
            print(f"Failed to download {url}")

def download_any_files(any_file_urls, target_directory):
    # Ensure target directory exists
    os.makedirs(target_directory, exist_ok=True)

    for url in any_file_urls:
        # Extract filename from URL or generate your own naming scheme
        filename = url.split('/')[-1]  # This gets the last part of the URL as the filename
        
        # Define the full path where the file will be saved
        file_path = os.path.join(target_directory, filename)
        
        # Download and save the file
        response = requests.get(url)
        if response.status_code == 200:  # Successful download
            with open(file_path, 'wb') as file:
                file.write(response.content)
            print(f"Downloaded {filename} to {file_path}")
        else:
            print(f"Failed to download {url}")

def get_database_address(file_path):
    try:
        with open(file_path, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        print("Database address file not found.")
        return None

'''
One key thing fo this script is that we need to select the specific states of
interest. Then, we need to choose the charactersitics of the households that 
we want to donwload.
'''

'''
The configuration starts here.
'''

# STATES_OF_INTEREST = ['MN']  # THis constant defines the state
STATES_OF_INTEREST = [
    'AL', 'AR', 'AZ', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA', 'IA', 'ID', 'IL', 'IN', 'KS', 'KY', 
    'LA', 'MA', 'MD', 'ME', 'MI', 'MN', 'MO', 'MS', 'MT', 'NC', 'ND', 'NE', 'NH', 'NJ', 'NM', 'NV', 
    'NY', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VA', 'VT', 'WA', 'WI', 'WV', 'WY'
]
CASE_ID = '1'  # This constant defines the metadata file after filtering for desired characteristics

# The dictionary below will help select specific parquet files to focus analysis
column_selection_case = {
    'in.heating_fuel':['Electricity', 'Natural Gas'],
    'in.geometry_floor_area':['1500-1999', '2000-2499', '2500-2999', '3000-3999'],
    'in.vintage': ['1970s', '1980s', '1990s', '2000s', '2010s'],
    'in.building_america_climate_zone': ['Very Cold'],
    'in.vacancy_status': ['Occupied'],
    'in.geometry_building_type_acs':['Single-Family Detached']
    }

'''
The processing starts here.
'''

START_PROCESS = time.time()
LIST_INCLUDE_UPGRADES = ['baseline', 'upgrade01', 'upgrade02', 'upgrade03',
                         'upgrade04']
list_upgrades_reformat = [i.replace('upgrade0', 'upgrade=') 
    for i in LIST_INCLUDE_UPGRADES if i != 'baseline']


# Choosing the database helps figure out what the repository is and what version of the database is being used.
db_address = get_database_address('pds_database_address.txt')

# --
# a) Navigate throught the right address (first level):
QUERY_YEAR = 2024
concat_string = '%2F'

address_list = []

address_nav_1 = db_address + str(QUERY_YEAR) + concat_string
address_list.append(address_nav_1)
print('Address 1: ', address_nav_1)

address_nav_2 = address_nav_1 + 'resstock_tmy3_release_2' + concat_string

# --
# b) Navigate to second level - metadata:
address_nav_3 = address_nav_2 + 'metadata_and_annual_results' + concat_string
address_nav_4 = address_nav_3 + 'by_state' + concat_string

driver_4 = webdriver.Chrome()  # Change this to your preferred WebDriver
driver_4.get(address_nav_4)

file_elements_META = driver_4.find_elements(
    By.XPATH, "//a[@data-s3='folder' or @data-s3='file']")
file_names_raw_META_all = [element.text for element in file_elements_META]

file_names_raw_META = [i for i in file_names_raw_META_all 
                       if i.replace('/', '').split('=')[-1]
                       in STATES_OF_INTEREST]

BOOL_DOWNLOAD_METADATA_RESI = True
# BOOL_DOWNLOAD_METADATA_RESI = False
if BOOL_DOWNLOAD_METADATA_RESI:
    for a_state in file_names_raw_META:
        address_nav_5 = address_nav_4 + a_state + 'csv' + concat_string

        driver_5 = webdriver.Chrome()
        driver_5.get(address_nav_5)
        file_links = \
            driver_5.find_elements(By.XPATH, "//a[contains(@href, '.csv')]")
        csv_file_urls_all = [link.get_attribute('href') for link in file_links]

        csv_file_urls = []
        for acsv in csv_file_urls_all:
            for up_str in LIST_INCLUDE_UPGRADES:
                if up_str in acsv:
                    csv_file_urls.append(acsv)

        str_state = a_state.split('=')[-1].replace('/', '')
        download_folder = 'Metadata_' + str(str_state) + '_Residential'
        download_any_files(csv_file_urls, download_folder)

# BOOL_DOWNLOAD_METADATA_COMM = True
BOOL_DOWNLOAD_METADATA_COMM = False
if BOOL_DOWNLOAD_METADATA_COMM:
    for a_state in file_names_raw_META:
        address_nav_5 = address_nav_4 + a_state + 'csv' + concat_string

        address_nav_5_vcom = address_nav_5.replace('resstock_tmy3_release_2', 'comstock_amy2018_release_1')

        driver_5 = webdriver.Chrome()
        driver_5.get(address_nav_5_vcom)
        file_links = \
            driver_5.find_elements(By.XPATH, "//a[contains(@href, '.csv')]")
        csv_file_urls_all = [link.get_attribute('href') for link in file_links]

        csv_file_urls = []
        for acsv in csv_file_urls_all:
            for up_str in LIST_INCLUDE_UPGRADES:
                if up_str in acsv:
                    csv_file_urls.append(acsv)

        str_state = a_state.split('=')[-1].replace('/', '')
        download_folder = 'Metadata_' + str(str_state) + '_Commercial'
        download_any_files(csv_file_urls, download_folder)

'''
The script will now finish.
'''
END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')

print('Check up until here')
sys.exit()

###############################################################################
###############################################################################
###############################################################################



