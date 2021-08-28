#!/usr/bin/env python
#
#   Bin Sonde Summary data into Launch Sites
#

import argparse
import json
import os
import sys
import logging
import pprint
import numpy as np

from utils import *



def bin_launch_data(telemetry, sites, radius=30, alt_limit=5000):

    _sonde = (float(telemetry['lat']), float(telemetry['lon']), float(telemetry['alt']))

    if _sonde[2] > alt_limit:
        return (None, 999999999)

    min_dist = 999999999
    min_site = None
    
    for _site in sites:
        _site_loc = (sites[_site]['lat'], sites[_site]['lon'], 0)

        try:
            _pos_info = position_info(_site_loc, _sonde)
        except:
            logging.error(f"Error performing calc: {_site}, {_telemetry['serial']} {_site_loc}, {_sonde}")
            sys.exit(1)

        _dist_km = _pos_info['great_circle_distance']/1000.0

        if (_dist_km > 0) and (_dist_km < radius):
            if _dist_km < min_dist:
                min_dist = _dist_km
                min_site = sites[_site]['station']
        
    
    return (min_site, min_dist)


if __name__ == "__main__":
    # Read command-line arguments
    parser = argparse.ArgumentParser(description="SondeHub Utils - Bin Summary Data", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--folder", default=None, help="Top-level folder to work on.")
    parser.add_argument("--radius", type=float, default=30, help="Radius from launch site in km.")
    parser.add_argument("--alt", type=float, default=5000, help="Altitude Cap (m)")
    parser.add_argument("--binnedoutput", type=str, default='binned_sites.json', help='Write binned sondes to this file - default binned_sites.json')
    parser.add_argument("--postanalysis", action="store_true", default=False, help="Perform Burst Altitude / Descent Rate Analysis")
    parser.add_argument("--binnedinput", type=str, default=None, help="Use existing binned data file.")
    parser.add_argument("--updatesites", type=str, default=None, help="Write out updated launch sites JSON file.")
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output (set logging level to DEBUG)")
    args = parser.parse_args()

    if args.verbose:
        _log_level = logging.DEBUG
    else:
        _log_level = logging.INFO

    # Setup Logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", level=_log_level
    )

    sites = load_launch_sites()

    logging.info(f"Loaded {len(sites)} launch sites.")


    if (args.binnedinput is None):

        if args.folder is None:
            logging.critical("Need a folder to work on!")
            sys.exit(1)

        file_list = get_sonde_file_list(args.folder)

        logging.info(f"Working on {len(file_list)} files.")

        binned_data = {}

        file_count = len(file_list)
        unknown_sondes = 0
        count = 1

        for _file in file_list:

            _summary = load_summary_file(_file)

            if _summary is None:
                continue
            
            _first = _summary[0]
            _burst = _summary[1]
            _last = _summary[2]
            _serial = _summary[0]['serial']

            (_site_bin, _site_range) = bin_launch_data(_first, sites, radius=args.radius, alt_limit=args.alt)

            if _site_bin:
                logging.debug(f"{count}/{file_count} - {_serial}: {sites[_site_bin]['station_name']}, {_site_range:.1f} km")

                if _site_bin not in binned_data:
                    binned_data[_site_bin] = {'site': sites[_site_bin], 'serials':[], 'serial_data':{}}
                
                binned_data[_site_bin]['serials'].append(_serial)
                binned_data[_site_bin]['serial_data'][_serial] = _summary

            else:
                logging.debug(f"{count}/{file_count} - {_serial}: None Found")
                unknown_sondes += 1


            count += 1
            if count%1000 == 0:
                logging.info(f"{count}/{file_count} processed.")
        
        logging.info("Sonde Summary processing complete!")
        # Save binned data
        _f = open(args.binnedoutput, 'w')
        _f.write(json.dumps(binned_data))
        _f.close()

        #pprint.pprint(binned_data)
        logging.info(f"Wrote binned data to {args.binnedoutput}.")
        logging.info(f"Sondes that could not be binned: {unknown_sondes}/{file_count}")


    if args.binnedinput:
        _f = open(args.binnedinput,'r')
        _data = _f.read()
        _f.close()
        binned_data = json.loads(_data)
    

    if args.postanalysis:
        for _site in binned_data:
            _site_name = sites[_site]['station_name']
            _num_sondes = len(binned_data[_site]['serials'])
            _serials = binned_data[_site]['serial_data']

            _avgs = calculate_averages(_serials)

            if _avgs:
                _avg_data = f"Bursts ({_avgs['burst_count']}): {_avgs['burst_mean']:.0f} m, {_avgs['burst_std']:.0f} m std-dev"
                sites[_site]['burst_altitude'] = int(_avgs['burst_mean'])
                sites[_site]['burst_samples'] = _avgs['burst_count']
                sites[_site]['burst_std'] = int(_avgs['burst_std'])

                if _avgs['descent_count'] > 5:
                  _avg_data += f"; Landing Rates ({_avgs['descent_count']}): {_avgs['descent_mean']:.1f} m/s, {_avgs['descent_std']:.1f} m/s std-dev"
                  sites[_site]['descent_rate'] = round(_avgs['descent_mean'],1)
                  sites[_site]['descent_samples'] = _avgs['descent_count']
                  sites[_site]['descent_std'] = round(_avgs['descent_std'],1)
            
                for _type in _avgs['type']:
                    _avg_data += f"; {_type}: {_avgs['type'][_type]}"

            else:
                _avg_data = "Not enough data for analysis."



            logging.info(f"{_site_name} ({sites[_site]['station']}): {_num_sondes} sondes - {_avg_data}")

    
    # TODO: Write out launch site data again.

    if args.updatesites:
        _outf = open(args.updatesites, 'w')

        _outf.write("[\n  ")

        _sites = list(sites.keys())
        _sites.sort()

        _site_lines = []

        for _site in _sites:
            _line = "  " + json.dumps(sites[_site])
            _site_lines.append(_line)
        
        _site_lines_str = ",\n  ".join(_site_lines)

        _outf.write(_site_lines_str)
        _outf.write("\n]")
        _outf.close()