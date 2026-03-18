1) Run copy_cricuits.py

2) Run circuit_make_daily_list_sets.py

3) Run review_parquet_matches.py, which produces review_parquet_matches.csv

4) Bring all the metadata using "commercial_data_SELECT_STATES.csv" and "residential_data_SELECT_STATES.csv". They are stored in 6_Paper_1_Simulator\imp_20240601\GSO\urban-suburban.

5) Run match_smartds_parquets_NC.py. This will produce "df_res_matches_out_NC.csv" AND "df_com_matches_out_NC.csv".

6) Run clean_up_bldgs_NC.py. This will produce "commercial_building_source_map_NC.csv" AND "residential_data_SELECT_STATES_FILTERED_mid_NC.csv" (and permutations).

7) Now you could run select_rep_family_NC.py. This will result in "NC_final_commercial.csv" AND "NC_final_residential.csv". For this to run completely, crease folder "parquet_residential_short_20250330_NC".
After running step #7, we get NC_final_commercial.csv and NC_final_residential.csv







