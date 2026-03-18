import sys
import os
import time
from copy import deepcopy

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By

import pandas as pd

'''
Commercial link:
    https://data.openei.org/s3_viewer?bucket=oedi-data-lake&prefix=nrel-pds-building-stock%2Fend-use-load-profiles-for-us-building-stock%2F2024%2Fcomstock_amy2018_release_1%2F
    json meanings: https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/comstock_amy2018_release_1/upgrades_lookup.json
    https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/comstock_amy2018_release_1/upgrades_lookup.json
'''

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

# STATES_OF_INTEREST = ['CA', 'NC', 'TX', 'MN', 'FL', 'MI', 'NY']  # THis constant defines the state
STATES_OF_INTEREST = ['NC']  # THis constant defines the state
CASE_ID = '20250330_comm_NC'  # This constant defines the metadata file after filtering for desired characteristics

# The dictionary below will help select specific parquet files to focus analysis

'''
column_selection_case = {
    'State':['NC'],
    'bldg_id':[
    230291, 227605, 227194, 230841, 234257, 226834, 230918, 224430, 235167, 231933,
    227704, 225861, 233114, 225292, 228644, 229300, 227326, 233946, 233114, 233689,
    232501, 234764, 233964, 229569, 231354, 232651, 234905, 230312, 225329, 229607,
    234494, 230301, 234729, 235441, 228957, 226151, 231392, 234494, 230312, 233085,
    231858, 232906, 225479, 234720, 225479, 227086, 235498, 227679, 234575, 229243,
    235631, 227273, 235199, 236260, 231196, 229509, 225390, 229254, 224825, 234472,
    232930, 233609, 231337, 228376, 229757, 230152, 232160, 236149, 232632, 235730,
    229064, 230152, 230694, 229254, 232160, 234230, 230014, 225647, 228376, 228376,
    233609, 227530, 224805, 224825, 228328, 228670, 236149, 233609, 234624, 228670,
    228863, 224578, 224578, 229254, 224733, 224674, 228670, 233633, 228165, 229139,
    235280, 228228, 232160, 230443, 236050, 236177, 224675, 231255, 230468, 235602,
    231017, 230004, 229002, 228356, 229161, 232725, 232006, 230793, 231086, 234358,
    225551, 233357, 230398, 228386, 225271, 229776, 231017, 230162, 234752, 224859,
    226272, 235147, 230895, 224743, 232313, 235554, 224569, 225551, 230333, 224548,
    228808, 228689, 225653, 232724, 231853, 227244, 224738, 227850, 234065, 235913,
    229002, 235736, 232006, 230162, 224548, 229370, 230655, 230795, 232245, 232059,
    224555, 229677, 233783, 230292, 228790, 224555, 233186, 227671, 234418, 233244,
    233780, 227917, 236105, 227671, 227488, 224969, 225696, 227671, 224555, 232508,
    235209, 227726, 224555, 232996, 224555, 229004, 225379, 228790, 225393, 233244,
    231980, 224611, 228452, 227671, 226176, 224780, 234500, 226176, 226512, 229974,
    232597, 228996, 229974, 231409, 226828, 225686, 232597, 231154, 230085, 232597,
    232597, 232470, 227941, 231468, 230664, 230423, 226176, 231468, 235759, 233897,
    229974, 235036, 230812, 229309, 228287, 227005, 233287, 228050, 235949, 230812,
    224666, 231340, 225051, 231574, 226684, 233166, 232105, 230812, 235924, 233750,
    234432, 228222, 226354, 231004, 231025, 225590, 230681, 226810, 224595, 228774,
    225468, 230145, 230481, 224703, 230055, 227180, 235861, 226529, 232568, 235090,
    235625, 229900, 231686, 226866, 229671, 225143, 224547, 227668, 230364, 230492,
    228969, 226866, 226493, 225701, 224927, 228557, 233596, 230211, 225590, 225074,
    228561, 229550, 230322, 231290, 225092, 234179, 228383, 226318, 232198, 226952,
    225790, 232198, 235277, 228313, 224950, 236214, 224692, 232515, 226211, 230630,
    224515, 235245, 232515, 230904, 234478, 227074, 234947, 231948, 224693, 228326,
    227570, 225202, 230630, 233031, 231758, 231977, 235956, 227558, 230609, 232092,
    232092, 224497, 235088, 226733, 234942, 228298, 233532, 235160, 232020, 229868,
    234315, 229972, 230501, 233840, 231070, 234850, 224950, 224515, 232092, 233592,
    231382, 229868, 236144, 232403, 235598, 226352, 225300, 228190, 227415, 226245,
    224515, 231758, 225071, 230562, 227197, 226952, 227534, 231977, 231424, 229472,
    234453, 227197, 233020, 226897, 232722, 231977, 228527, 233020, 235725, 230025,
    235245, 232515, 225549, 232309, 233236, 232010, 224518, 233928]
    }
'''


column_selection_case = {
    'State':['NC'],
    'bldg_id':[
    227194,     227605,     230291,     225038,     226834,     230841,     234257,     226675,     226096,     230918,     233327,     233584,
    229341,     227513,     231933,     224430,     233185,     233222,     227704,     235684,     228644,     225958,     233114,     226488,
    226004,     225292,     229300,     231297,     231803,     229335,     232608,     233946,     225889,     233689,     226570,     229574,
    227326,     232456,     226281,     234494,     234415,     235049,     228957,     229513,     226887,     229607,     227277,     234764,
    232332,     235115,     232651,     231354,     235706,     225329,     233964,     230260,     231392,     234785,     229569,     234905,
    226574,     235934,     226151,     224935,     234729,     226594,     230657,     230301,     230312,     225858,     230350,     232501,
    235441,     230780,     232321,     235025,     227273,     234219,     229042,     225397,     235498,     233077,     233651,     236260,
    234720,     228155,     235809,     235199,     227086,     231934,     235631,     227679,     232906,     224759,     224951,     229802,
    226888,     233305,     233085,     227032,     234575,     229243,     231858,     232824,     231540,     231242,     228376,     235404,
    227542,     232632,     224805,     228328,     229254,     224578,     227166,     224861,     230567,     232930,     226993,     228251,
    228670,     227105,     225390,     227444,     232160,     230152,     231660,     224825,     226179,     233609,     229064,     236149,
    233111,     229757,     224853,     226424,     224733,     230569,     236006,     228165,     234805,     230620,     230004,     231086,
    230895,     235147,     224551,     235875,     228602,     224569,     226122,     227244,     230162,     236071,     229917,     235602,
    235560,     232313,     227729,     234054,     230333,     232006,     229487,     233002,     235734,     229861,     235000,     235736,
    230472,     230625,     229161,     228356,     228808,     230793,     224548,     234065,     230662,     233357,     224706,     226272,
    228689,     232058,     230398,     224738,     230855,     230132,     233970,     225271,     232727,     228119,     231626,     231255,
    232725,     235913,     233790,     227053,     233852,     224675,     234645,     224859,     226138,     232730,     229659,     236177,
    225001,     234304,     230029,     229735,     235554,     231853,     231017,     225653,     226895,     231038,     226630,     227976,
    227155,     231134,     227850,     228776,     230795,     235410,     229002,     229370,     233815,     233168,     224716,     230655,
    225307,     228662,     229847,     231903,     231599,     226563,     224650,     234418,     227726,     226334,     228708,     231453,
    225696,     224463,     233809,     236083,     231718,     229715,     235081,     232996,     225908,     224611,     227671,     229004,
    228737,     228977,     225883,     235209,     232839,     229964,     229257,     233780,     233796,     226869,     224555,     232508,
    232603,     232245,     227189,     233186,     230292,     235990,     224917,     227184,     230179,     226457,     233739,     235153,
    232597,     226176,     234749,     232648,     224780,     232416,     227226,     230085,     234498,     225180,     227003,     229980,
    234580,     226512,     234973,     227942,     231468,     234360,     225686,     231918,     229838,     232470,     235583,     235759,
    234627,     228366,     227974,     229030,     234916,     235746,     230886,     232768,     232837,     226737,     233897,     230760,
    229974,     229006,     228596,     226518,     230187,     228395,     230725,     224426,     235169,     232523,     231428,     230214,
    236017,     224598,     234151,     229821,     225500,     227481,     230265,     235339,     234816,     232483,     229685,     229075,
    226337,     235036,     230093,     235949,     229263,     227267,     224666,     231574,     234687,     226416,     226684,     230812,
    228405,     235924,     233759,     234651,     227564,     235108,     234064,     233166,     226864,     233750,     232105,     228050,
    227077,     225837,     234853,     227261,     230036,     230677,     236118,     233644,     227005,     228287,     225051,     226307,
    226789,     227201,     233287,     235259,     233923,     226962,     230619,     236040,     225878,     231142,     231381,     235389,
    231104,     231340,     233499,     229231,     229065,     227283,     235159,     228679,     228441,     225519,     227588,     230591,
    234246,     234333,     231267,     232409,     235029,     228378,     234028,     229309,     227066,     225618,     235861,     230492,
    232886,     227736,     227668,     234893,     234676,     230041,     226493,     231727,     225590,     232463,     231686,     234860,
    226431,     232126,     228557,     233671,     230322,     225468,     234179,     228198,     232568,     231442,     230532,     228774,
    235503,     232170,     228969,     229900,     234432,     230211,     224927,     230892,     224982,     233414,     230789,     233596,
    231004,     235625,     224971,     230681,     231025,     230584,     232450,     234369,     224703,     234870,     234370,     228918,
    227626,     228937,     226271,     234482,     226101,     226529,     234706,     228383,     233665,     227927,     231181,     234348,
    231290,     228561,     227341,     226866,     234129,     230099,     228755,     231351,     224900,     235090,     231637,     228222,
    225421,     226318,     225503,     224595,     235235,     226354,     229671,     233469,     230145,     231199,     229399,     230364,
    234323,     234010,     230967,     226254,     231645,     225126,     229550,     227958,     224790,     231750,     232216,     225701,
    227180,     225776,     229312,     226810,     234696,     225444,     226394,     224513,     225478,     235452,     232783,     232146,
    232822,     233008,     224593,     226359,     227534,     227857,     225790,     230562,     230501,     231884,     234942,     232092,
    233592,     231977,     235725,     233541,     227228,     227197,     225257,     230870,     234315,     231758,     225300,     228264,
    234850,     228668,     229200,     232403,     224518,     229706,     225443,     229719,     227405,     231012,     226757,     228864,
    231070,     233236,     235277,     224711,     232131,     230074,     224692,     225127,     230629,     233830,     232515,     232428,
    228760,     225835,     229912,     226211,     235956,     235532,     232198,     225462,     224557,     226245,     234789,     235092,
    224515,     228817,     229057,     224497,     229297,     235598,     230264,     226280,     235148,     227687,     233928,     228797,
    232446,     225860,     234692,     227856,     232947,     232722,     225146,     235088,     234947,     230246,     228527,     236171,
    233020,     231205,     235570,     234743,     235160,     229472,     232309,     235245,     225071,     236214,     234464,     226952,
    231761,     227415,     231272,     234453,     229972,     235065,     230630,     230904,     236144,     233468,     233532,     224693,
    231431,     230025,     231382,     228078,     224908,     224867,     226242,     232400,     227766,     229868,     232020,     227558,
    229352,     228298,     233880,     235082,     228267,     236193,     228699,     225549,     226733,     227630,     235349,     226403,
    234478,     227074,     226261,     230609,     232010,     231948,     233088,     228753,     226352
]}

'''
The processing starts here.
'''

START_PROCESS = time.time()
# LIST_INCLUDE_UPGRADES = ['baseline', 'upgrade01']
# list_upgrades_reformat = [i.replace('upgrade0', 'upgrade=') 
#    for i in LIST_INCLUDE_UPGRADES if i != 'baseline']
LIST_INCLUDE_UPGRADES = ['upgrade=0', 'upgrade=1', 'upgrade=2', 'upgrade=3', 'upgrade=8', 'upgrade=9', 'upgrade=19', 'upgrade=20']
LIST_INCLUDE_UPGRADES_INT = [0, 1, 2, 3, 8, 9, 19, 20]
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

address_nav_2 = address_nav_1 + 'comstock_amy2018_release_1' + concat_string

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
    ### path_metadata_folder = './Metadata_Com_' + str(astate)
    ### baseline_file_name = [
    ###    i for i in os.listdir(path_metadata_folder) if 'baseline' in i][0]
    path_baseline_csv = './commercial_data_SELECT_STATES_FILTERED_' + astate + '.csv'

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

file_elements_TS = driver_7.find_elements(
    By.XPATH, "//a[@data-s3='folder' or @data-s3='file']")
file_names_raw_TS_all = [element.text for element in file_elements_TS]
file_names_raw_TS = [i for i in file_names_raw_TS_all 
                     if i.replace('/', '').split('=')[-1]
                     in STATES_OF_INTEREST]

# print('stop here please')
# sys.exit()

parquet_file_urls_raw = []

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
            parquet_file_urls_raw += parquet_file_urls

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

            #if count_offsets == 1:
            #    print('stop this here')
            #    sys.exit()

            count_offsets += 1

            # keep_offset = False
            
            if len(parquet_file_urls) == 0:
                keep_offset = False

        # print('What is going on here')
        # sys.exit()

# print('check this')
# sys.exit()

'''
At this stage we want to expand the "downloadables" to other upgrades,
following:  list_upgrades_reformat
'''
url_list_base = deepcopy(url_list)

# print('what do we have here?')
# sys.exit()

expanded_url_list = []
for u in LIST_INCLUDE_UPGRADES_INT:
    expanded_url_list_local_0 = [
        url.replace('-0.parquet', '-' + str(u) + '.parquet')
        for url in url_list_base]

    expanded_url_list_local_1  = [
        url.replace("upgrade%3D0", "upgrade%3D" + str(u))
        for url in expanded_url_list_local_0]

    expanded_url_list += expanded_url_list_local_1
# Using list comprehension for efficient expansion
url_list = deepcopy(expanded_url_list)

'''
expanded_url_list = [
    url.replace("upgrade=0", upgrade).replace('-0.parquet', '-9.parquet')
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
    download_any_files(chunk, './parquet_commercial_' + CASE_ID)
    
    # Introduce a delay to avoid triggering rate limits
    time.sleep(1)  # Adjust this value if necessary

'''
The script will now finish.
'''
END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')


