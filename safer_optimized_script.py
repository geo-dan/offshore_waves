import numpy as np
from netCDF4 import Dataset
import sys
import time as time_module

print("Extract time-series from CAWCR wave hindcast")
print("usage: hindcast_extract_ts.py lonp latp var1 var2 ...")
print("var1 var2 ... is variable name e.g., hs, tm01, dir, ...")

# Configuration
sys.argv = ["-c", "153.22", "-26.29", "hs", "t0m1", "dp"] # make sure you change the reference file if the values here are not working!! Can check the values on the opendap site for CAWCR.
year1 = 2025
year2 = 2026
ln = float(sys.argv[1])
lt = float(sys.argv[2])
variables = sys.argv[3:]

# Get grid indices once
print("Finding grid indices...")
hcst = Dataset('http://data-cbr.csiro.au/thredds/dodsC/catch_all/CMAR_CAWCR-Wave_archive/CAWCR_Wave_Hindcast_aggregate/gridded/ww3.aus_4m.202001.nc')
lons = hcst.variables['longitude'][:]
lats = hcst.variables['latitude'][:]
idx = (np.abs(lons - ln)).argmin()
idy = (np.abs(lats - lt)).argmin()
print(f"Grid indices: longitude index {idx}, latitude index {idy}")

# Store reference to time and variable attributes
time_attrs = {attr: hcst.variables['time'].getncattr(attr) 
              for attr in hcst.variables['time'].ncattrs()}
var_attrs = {}
for var_name in variables:
    var_attrs[var_name] = {attr: hcst.variables[var_name].getncattr(attr) 
                          for attr in hcst.variables[var_name].ncattrs() 
                          if attr in ('long_name', 'standard_name', 'globwave_name', 'units', 'valid_min', 'valid_max')}

hcst.close()

# Generate file list
file_list = []
for yr in range(year1, year2):
    nmon = 13 if yr < 2012 else 13
    for mon in range(1, nmon):
        file_list.append((yr, mon))

# Pre-calculate total size for pre-allocation
print("Estimating data size...")
# Sample one file to get typical time dimension size
sample_yr, sample_mon = file_list[0]
path = 'http://data-cbr.csiro.au/thredds/dodsC/catch_all/CMAR_CAWCR-Wave_archive/CAWCR_Wave_Hindcast_aggregate/gridded/'
sample_file = f'{path}ww3.aus_4m.{sample_yr:04d}{sample_mon:02d}.nc'
with Dataset(sample_file) as sample:
    time_points_per_file = len(sample.variables['time'])

estimated_total_points = len(file_list) * time_points_per_file
print(f"Estimated total time points: {estimated_total_points}")

# Pre-allocate arrays
time_data = []
var_data = {var_name: [] for var_name in variables}

# Download and process files sequentially with optimizations
print(f"Processing {len(file_list)} files...")
start_time = time_module.time()

for i, (yr, mon) in enumerate(file_list):
    print(f"Processing {yr}-{mon:02d} ({i+1}/{len(file_list)})...")
    
    try:
        path = 'http://data-cbr.csiro.au/thredds/dodsC/catch_all/CMAR_CAWCR-Wave_archive/CAWCR_Wave_Hindcast_aggregate/gridded/'
        file = f'{path}ww3.aus_4m.{yr:04d}{mon:02d}.nc'
        
        # Use context manager for proper resource management
        with Dataset(file) as hcst:
            # Extract time data
            time_data.append(hcst.variables['time'][:])
            
            # Extract variable data for the specific location only
            # This is more efficient than reading the full array
            for var_name in variables:
                # Read only the specific lat/lon point we need
                var_data[var_name].append(hcst.variables[var_name][:, idy, idx])
                
    except Exception as e:
        print(f"Error processing {yr}-{mon:02d}: {e}")
        continue

download_time = time_module.time() - start_time
print(f"Downloaded {len(time_data)} files in {download_time:.2f} seconds")

# Efficiently concatenate all data
print("Concatenating data...")
if time_data:
    # Use numpy's concatenate which is much more efficient than repeated append
    final_time = np.concatenate(time_data)
    final_vars = {var_name: np.concatenate(var_data[var_name]) 
                  for var_name in variables}
    
    print(f"Total time points: {len(final_time)}")
    
    # Write netcdf file
    print("Writing output file...")
    newfile = f"HCtimeseries_aus_4m_{ln:.2f}E_{-lt:.2f}S_SC_{year1:.0f}_{year2:.0f}.nc"
    
    with Dataset(newfile, 'w', format='NETCDF4') as w_nc_fid:
        w_nc_fid.description = f"CAWCR Wave Hindcast time-series from location {ln} {lt}"
        
        # Create dimensions and time variable
        w_nc_fid.createDimension('time', None)
        w_nc_dim = w_nc_fid.createVariable('time', 'f8', ('time',))
        
        # Set time attributes
        for attr_name, attr_value in time_attrs.items():
            w_nc_dim.setncattr(attr_name, attr_value)
        
        w_nc_fid.variables['time'][:] = final_time
        
        # Create variable datasets
        for var_name in variables:
            w_nc_var = w_nc_fid.createVariable(var_name, 'f8', ('time',))
            
            # Set variable attributes
            for attr_name, attr_value in var_attrs[var_name].items():
                w_nc_var.setncattr(attr_name, attr_value)
            
            w_nc_fid.variables[var_name][:] = final_vars[var_name]
    
    total_time = time_module.time() - start_time
    print(f"Total processing time: {total_time:.2f} seconds")
    print(f"Output file: {newfile}")
    print(f"Average time per file: {total_time/len(file_list):.2f} seconds")
    
else:
    print("No data was successfully downloaded!")
