import sys
import os
import time
from copy import deepcopy

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

STATES_OF_INTEREST = ["NC"]  # Florida  # THis constant defines the state
CASE_ID = '20250330_NC'  # This constant defines the metadata file after filtering for desired characteristics

# The dictionary below will help select specific parquet files to focus analysis

'''
column_selection_case = {
    'State':['NC'],
    'bldg_id':[
    25663, 150291, 205503, 429073, 477810, 343821, 535157, 178248, 55155, 308312,
    535157, 116051, 348818, 126708, 493765, 348818, 78392, 384137, 420236, 89325,
    176299, 233938, 384137, 299463, 142749, 226712, 73001, 504394, 405136, 299752,
    386669, 464653, 299098, 418771, 362340, 89697, 238227, 360423, 173195, 386669,
    464653, 114415, 542279, 15187, 333539, 381663, 400868, 256640, 163626, 386669,
    105334, 309227, 156440, 383650, 238227, 453122, 266734, 429819, 429819, 28783,
    24560, 253941, 386669, 386669, 34116, 46399, 360423, 171812, 306376, 50493,
    171812, 283149, 403496, 386669, 28783, 373975, 246434, 373975, 96347, 429819,
    337063, 333588, 28783, 346839, 145537, 97638, 494895, 153423, 356578, 386669,
    537666, 314867, 405136, 323690, 342328, 545983, 546336, 335619, 179974, 312969,
    176423, 469329, 78844, 523788, 235156, 7133, 80629, 332488, 49586, 7133, 70581,
    191862, 75554, 230382, 249154, 265788, 367503, 416131, 276879, 393157, 194301,
    90648, 469329, 410230, 405340, 58395, 495667, 405218, 371618, 6539, 411558,
    227275, 38621, 7133, 545624, 455887, 390096, 507440, 207152, 51907, 257457,
    250991, 288412, 196782, 398813, 151452, 29575, 386541, 520320, 417285, 169725,
    494828, 238641, 428860, 312969, 91052, 50471, 260895, 466863, 147152, 378131,
    165446, 477979, 19256, 417285, 462198, 225005, 136069, 221319, 441337, 296974,
    28998, 93040, 254253, 99985, 43946, 165210, 480985, 290771, 272050, 248597,
    455623, 229873, 227945, 178092, 121759, 45702, 195998, 489936, 174125, 294470,
    317109, 368190, 105321, 522468, 465726, 412222, 369374, 50395, 481022, 495356,
    325354, 229788, 88305, 433342, 522468, 409622, 19256, 526235, 38621, 29575,
    48311, 385340, 33321, 454355, 279058, 247662, 334241, 11668, 247662, 58966,
    204241, 234287, 405204, 234287, 173139, 55474, 111922, 365297, 130368, 55743,
    79083, 497563, 130368, 120917, 401881, 323952, 391643, 444115, 204366, 224885,
    532475, 104347, 243792, 302499, 169876, 323480, 62198, 395696, 19595]
    }
'''

column_selection_case = {
    'State':['NC'],
    'bldg_id':[
    280535, 529030, 344090, 457130, 51248, 97064, 279056, 438217, 156448, 164952, 35477, 420203, 167400, 218062,
    72447, 367703, 84697, 481382, 91378, 97925, 178981, 527921, 17111, 59917, 261886, 220549, 178093, 6026,
    527501, 432723, 319515, 359965, 235585, 546364, 485394, 262127, 529033, 493987, 407787, 344018, 535227, 139348,
    263649, 239844, 379231, 313792, 534332, 222362, 435560, 72777, 35373, 264802, 67210, 193963, 68118, 462831,
    287287, 8782, 9317, 267097, 265199, 352076, 136435, 38417, 259129, 419312, 286489, 92439, 517977, 118125,
    247367, 457116, 546233, 460644, 404686, 130527, 478918, 354365, 404797, 337045, 250118, 98294, 98674, 15396,
    129565, 244868, 534901, 3287, 15650, 107647, 428637, 222728, 200756, 517627, 240691, 454538, 202962, 451679,
    328107, 282264, 154971, 126100, 73055, 334241, 88537, 36597, 464775, 467570, 247612, 116266, 194672, 363975,
    529756, 203533, 329979, 283333, 413132, 53909, 212677, 45392, 532168, 507754, 199135, 507902, 348156, 473225,
    521039, 174039, 387763, 518840, 381400, 544432, 60154, 246233, 64957, 70635, 447079, 502536, 97124, 434770,
    287291, 188940, 203311, 189739, 168854, 138890, 212492, 545651, 479216, 199058, 108419, 401346, 111958, 417893,
    136108, 23436, 472351, 478693, 130213, 190125, 478171, 446954, 143236, 204029, 216945, 388824, 62209, 266419,
    394308, 119047, 80170, 390007, 347276, 231804, 204241, 118222, 455247, 272261, 296854, 396519, 154882, 119211,
    487394, 486640, 65464, 257869, 232311, 272431, 69383, 121670, 94364, 162506, 17134, 258869, 660, 173600,
    217789, 501337, 234287, 58966, 224061, 83078, 43483, 213633, 86151, 511168, 34965, 26565, 492347, 448472,
    114512, 509702, 354097, 330728, 101087, 528778, 247582, 457829, 414074, 30486, 178112, 224275, 10560, 179307,
    432679, 402350, 324000, 458193, 491844, 341075, 200878, 390095, 373084, 260245, 98055, 288150, 83997, 3268,
    123790, 289532, 321144, 206334, 400900, 502706, 19803, 476516, 66479, 524421, 306028, 522637, 282044, 15373,
    328007, 307599, 156896, 248378, 323108, 245135, 183001, 6456, 173686, 283447, 31765, 430363, 44529, 11668,
    30407, 217842, 375123, 24785, 399644, 45508, 491298, 326186, 444657, 128919, 196063, 397370, 4326, 232001,
    197032, 98514, 440300, 158466, 284740, 43831, 73164, 68408, 350461, 430198, 151208, 277033, 9326, 227698,
    173139, 523510, 117315, 189705, 132061, 165855, 464019, 167987, 441994, 123009, 419799, 457181, 19256, 441337,
    136069, 464736, 371618, 81558, 83034, 265788, 150612, 75554, 409622, 269518, 80629, 302888, 77448, 340504,
    367862, 326128, 466863, 287519, 359000, 422987, 480467, 75643, 165446, 455102, 489128, 524791, 38621, 197962,
    199237, 481022, 196782, 120437, 33321, 37802, 454355, 279058, 179415, 391643, 467343, 417792, 253062, 55743,
    365297, 130368, 345074, 327027, 321381, 265915, 401881, 367039, 499540, 497563, 299351, 323952, 79083, 537198,
    19424, 444115, 549881, 342312, 401468, 6626, 204366, 224885, 323480, 293010, 302499, 243792, 336459, 21154,
    388024, 62198, 376022, 104347, 395696, 19595, 384776, 126000
]}

'''
OLD 1
column_selection_case = {
    'State':['FL'],
    'in.vacancy_status': ['Occupied'],
    'in.geometry_building_type_acs':['Single-Family Detached', 'Single-Family Attached']
    }
'''

'''
OLD 2
column_selection_case = {
    'in.heating_fuel':['Electricity'],
    'in.geometry_floor_area':['750-999'],
    'in.vintage': ['2010s'],
    'in.building_america_climate_zone': ['Very Cold'], # removed this column above
    'in.vacancy_status': ['Occupied'],
    'in.geometry_building_type_acs':['Single-Family Detached']
    }
'''

'''
The processing starts here.
'''

START_PROCESS = time.time()
# LIST_INCLUDE_UPGRADES = ['baseline', 'upgrade01']
# list_upgrades_reformat = [i.replace('upgrade0', 'upgrade=') 
#    for i in LIST_INCLUDE_UPGRADES if i != 'baseline']
LIST_INCLUDE_UPGRADES = ['upgrade=0', 'upgrade=1', 'upgrade=2', 'upgrade=4']
# list_upgrades_reformat = [i.replace('upgrade0', 'upgrade=') 
#     for i in LIST_INCLUDE_UPGRADES]


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

# BOOL_DOWNLOAD_METADATA = True
BOOL_DOWNLOAD_METADATA = False
if BOOL_DOWNLOAD_METADATA:
    for a_state in file_names_raw_META:
        address_nav_5 = address_nav_4 + a_state + 'csv' + concat_string

        driver_5 = webdriver.Chrome()
        driver_5.get(address_nav_5)
        file_links = \
            driver_5.find_elements(By.XPATH, "//a[contains(@href, '.csv')]")
            
            
        # print('got it until here 1')
        # sys.exit()
        csv_file_urls_all = [link.get_attribute('href') for link in file_links]
        # print('stop here')
        # sys.exit()

        csv_file_urls = []
        for acsv in csv_file_urls_all:
            for up_str in LIST_INCLUDE_UPGRADES:
                if up_str in acsv:
                    csv_file_urls.append(acsv)

        str_state = a_state.split('=')[-1].replace('/', '')
        download_folder = 'Metadata_' + str(str_state)
        download_any_files(csv_file_urls, download_folder)

        # print('Check the list of CSVs')
        # sys.exit()

'''
Crucially, at this stage we need to figure out the extraction of features
from the .csv files that will provide us the needed parquet files.
'''

# Open up the baseline metadata file for the states of interest; at this stage
# we need to iterate across the states of interest.
dict_parsed_metadata = {}

parquet_list_per_state = {}

for astate in STATES_OF_INTEREST:
    # Open the files in the metadata folder:
    path_baseline_csv = './residential_data_SELECT_STATES_FILTERED_' + astate + '.csv'

    # Load the CSV file into a pandas DataFrame
    df = pd.read_csv(path_baseline_csv)
    df_orig = deepcopy(df)

    # Assuming df is your DataFrame and column_selection_case is your filter dictionary

    # Apply cumulative filters based on the dictionary
    for column, values in column_selection_case.items():
        if column in df.columns:  # Check if the column exists in the DataFrame
            df = df[df[column].isin(values)]
        else:
            print(f"Warning: Column '{column}' not found in DataFrame.")

    # print('stay here')
    # sys.exit()

    # Verify that the final DataFrame contains only the desired values
    verification_passed = True
    for column, values in column_selection_case.items():
        unique_values = df[column].unique()
        if not set(unique_values).issubset(set(values)):
            print(f"Verification failed for column '{column}'. Found values: {unique_values}")
            verification_passed = False
        else:
            print(f"Verification passed for column '{column}'.")

    if verification_passed:
        print("All criteria successfully applied.")
    else:
        print("Some criteria were not met in the final DataFrame.")

    parquet_list_per_state.update({astate:df['bldg_id'].tolist()})

    dict_parsed_metadata.update({astate:deepcopy(df)})

    # print('Check up until here')
    # sys.exit()

# dict_parsed_metadata['MN']

# --
# c) Navigate to second level - parquet timeseries individual buildings:
address_nav_6 = address_nav_2 + 'timeseries_individual_buildings' + \
    concat_string + 'by_state' + concat_string
print('Address 6: ', address_nav_6)

# Select parquets from upgrade=0:

address_nav_7 = address_nav_6 + 'upgrade=0' + concat_string
print('Address 7: ', address_nav_7)

driver_7 = webdriver.Chrome()  # Change this to your preferred WebDriver
driver_7.get(address_nav_7)
wait = WebDriverWait(driver_7, 60)
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataTable, table#objects, div.dataTables_wrapper")))
wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "a[data-s3]")) > 0)

file_elements_TS = driver_7.find_elements(
    By.XPATH, "//a[@data-s3='folder' or @data-s3='file']")
if not file_elements_TS:
    # Fallback if the attribute changes: grab first‑column links in the table
    file_elements_TS = driver_7.find_elements(By.CSS_SELECTOR, "table.dataTable tbody tr td:first-child a, table#objects tbody tr td:first-child a")

print('Stop here')
sys.exit()

file_names_raw_TS_all = [element.text for element in file_elements_TS]
file_names_raw_TS = [i for i in file_names_raw_TS_all 
                     if i.replace('/', '').split('=')[-1]
                     in STATES_OF_INTEREST]


BOOL_DOWNLOAD_TIMESERIES = True
# BOOL_DOWNLOAD_TIMESERIES = False
if BOOL_DOWNLOAD_TIMESERIES:
    for a_state in file_names_raw_TS:
        a_state_str = a_state.split('=')[-1].replace('/', '')
        url_list = []
        keep_offset = True
        count_offsets = 0
        while keep_offset:
            address_nav_8_raw = \
                address_nav_7 + a_state.replace('/', '') + concat_string
            address_nav_8 = address_nav_8_raw.replace('prefix=', 'limit=100&prefix=')

            if count_offsets > 0:
                address_nav_8 = \
                    address_nav_8 + '&offset=' + str(int(count_offsets*100))

            print('Address 8: ', address_nav_8)

            driver_8 = webdriver.Chrome()
            driver_8.get(address_nav_8)
            file_links = driver_8.find_elements(
                By.XPATH, "//a[contains(@href, '.parquet')]")
            parquet_file_urls = [
                link.get_attribute('href') for link in file_links]

            parquet_file_urls_use = []
            for aparq in parquet_file_urls:
                parq_str = aparq.split('/')[-1]
                parq_int = int(parq_str.split('-')[0])
                # print('stop here for checking')
                # sys.exit()
                if parq_int in parquet_list_per_state[a_state_str]:
                    parquet_file_urls_use.append(aparq)

            url_list += parquet_file_urls_use

            # print('Stop it right here')
            # sys.exit()

            count_offsets += 1

            # keep_offset = False
            
            if len(parquet_file_urls) == 0:
                keep_offset = False

        # print('What is going on here')
        # sys.exit()

'''
At this stage we want to expand the "downloadables" to other upgrades,
following:  list_upgrades_reformat
'''
url_list_base = deepcopy(url_list)

# print('what do we have here?')
# sys.exit()

# Using list comprehension for efficient expansion
expanded_url_list = [
    url.replace("upgrade%3D0", "upgrade%3D1").replace('-0.parquet', '-1.parquet')
    for url in url_list
]

expanded_url_list_2 = [
    url.replace("upgrade%3D0", "upgrade%3D2").replace('-0.parquet', '-2.parquet')
    for url in url_list
]

expanded_url_list_3 = [
    url.replace("upgrade%3D0", "upgrade%3D4").replace('-0.parquet', '-4.parquet')
    for url in url_list
]

url_list += expanded_url_list
url_list += expanded_url_list_2
url_list += expanded_url_list_3

'''
expanded_url_list = [
    url.replace("upgrade=0", upgrade).replace('-0.parquet', '-1.parquet')
    for url in url_list
    for upgrade in list_upgrades_reformat
]
'''

# Set the chunk size
chunk_size = 50  # Adjust this value based on your needs

# Break the url_list into chunks
url_chunks = chunk_list(url_list, chunk_size)

'''
The script will download the parquet files.
'''
# Iterate over each chunk, process, and then sleep
for i, chunk in enumerate(url_chunks):
    print(f"Processing chunk {i+1}")
    download_any_files(chunk, './parquet_residential_short_' + CASE_ID)
    
    # Introduce a delay to avoid triggering rate limits
    time.sleep(0.25)  # Adjust this value if necessary

'''
The script will now finish.
'''
END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')


