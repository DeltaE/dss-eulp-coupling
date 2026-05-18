# -*- coding: utf-8 -*-
"""
Created on Sat Nov  8 16:01:56 2025

@author: luisfernando
"""

import pickle

# Replace with your actual file path
filename = 'daily_list_set_uhs0_1247--udt12274.pkl'

# Open and load the pickle file
with open(filename, 'rb') as file:
    data = pickle.load(file)