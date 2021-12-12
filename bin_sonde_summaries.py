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
import boto3
import botocore.credentials
import time

from threading import Thread
from queue import Queue

from utils import *

BUCKET = "sondehub-history"

# Remapping of type data present in the old Sondehub V1 "comment" field, into
# Sondehub-V2 compatible radiosonde high-level types.
# This includes for some weirdness that I've found in the DB.
ALLOWED_TYPE_CHANGES = {
    "RS41": "RS41",
    "RS41-Ozone": "RS41",
    "RS41-SGP-Ozone": "RS41",
    "RS41-SG": "RS41",
    "RS41-SG-Ozone": "RS41",
    "RS41-SGP": "RS41",
    "RS41-SGM": "RS41",
    "RS41-NG": "RS41",
    "RS92": "RS92",
    "RS92-Ozone": "RS92",
    "IMET": "iMet-4",
    "iMet": "iMet-4",
    "DFM": "DFM",
    "DFM06": "DFM",
    "DFM09": "DFM",
    "DFMxB": "DFM",
    "DFMxC": "DFM",
    "DFMx7": "DFM",
    "DFMx9": "DFM",
    "DFM17": "DFM",
    "DFM09P": "DFM",
    "MK2LMS": "LMS6-1680",
    "LMS6": "LMS6-403",
    "M10": "M10",
    ",M10": "M10",
    "M10-Ptu": "M10",
    "M20": "M20",
    "MEISEI": "IMS100",
    "IMS100": "IMS100",
    "IMET5": "iMet-5x"
}

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


def upload_summary_to_s3(s3, summary):
    """ 
    Updates a summary dataset back to the S3 sondehub-history bucket.

    This requires S3 credentials set up in ~/.aws/credentials
    """

    # Generate metadata
    metadata = {
        "first-lat": str(summary[0]['lat']),
        "first-lon": str(summary[0]['lon']),
        "first-alt": str(summary[0]['alt']),
        "max-lat": str(summary[1]['lat']),
        "max-lon": str(summary[1]['lon']),
        "max-alt": str(summary[1]['alt']),
        "last-lat": str(summary[2]['lat']),
        "last-lon": str(summary[2]['lon']),
        "last-alt": str(summary[2]['alt']),
        "launch_site": str(summary[0]['launch_site'])
    }

    _serial = summary[0]['serial']
    _launch_site = summary[0]['launch_site']

    # Generate what dates we need to add this summary file to.
    _dates = []
    for x in summary:
        _date = x['datetime'].split("T")[0].replace("-","/")
        if _date not in _dates:
            _dates.append(_date)
        
        # Try and clean up some Sondehub-V1 data, by extracting the
        # type field from the comment field.
        if x['type'] == "payload_telemetry":
            _type = x["comment"].split(" ")[0]

            if _type not in ALLOWED_TYPE_CHANGES:
                logging.error(f"Unknown type: {_type} ({x['comment']}), discarding.")
                return
            else:
                _type = ALLOWED_TYPE_CHANGES[_type]

            x['type'] = _type
            logging.debug(f"{_serial}: Updated type to {_type}")


    logging.debug(f"{_serial} {_launch_site}: {str(metadata)}")

    for _date in _dates:
        _date_path = f'date/{_date}/{_serial}.json'
        logging.debug(f"S3 path 1: {_date_path}")
        object = s3.Object(BUCKET,_date_path)
        object.put(
            Body=json.dumps(summary).encode("utf-8"),
            Metadata=metadata
        )

        _launchsite_path = f'launchsites/{_launch_site}/{_date}/{_serial}.json'
        logging.debug(f"S3 path 2: {_launchsite_path}")
        object = s3.Object(BUCKET,_launchsite_path)
        object.put(
            Body=json.dumps(summary).encode("utf-8"),
            Metadata=metadata
        )

# Queue for uploading summary data to S3.
upload_queue = Queue()
uploader_threads_running = True

def uploader_thread():
    """
    Uploader thread - reads from upload queue, uploads summary file to S3.
    Currently no way of killing this thread, just ctrl-c.
    """
    logging.info("Uploader thread running.")
    s3 = boto3.resource('s3')
    while uploader_threads_running:
        _data = upload_queue.get()
        upload_summary_to_s3(s3, _data)



if __name__ == "__main__":
    # Read command-line arguments
    parser = argparse.ArgumentParser(description="SondeHub Utils - Bin Summary Data", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--folder", default=None, help="Top-level folder to work on.")
    parser.add_argument("--outputfolder", default=None, help="Write out individual summary files to output folder.")
    parser.add_argument("--radius", type=float, default=30, help="Radius from launch site in km.")
    parser.add_argument("--alt", type=float, default=5000, help="Altitude Cap (m)")
    parser.add_argument("--binnedoutput", type=str, default='binned_sites.json', help='Write binned sondes to this file - default binned_sites.json')
    parser.add_argument("--postanalysis", action="store_true", default=False, help="Perform Burst Altitude / Descent Rate Analysis")
    parser.add_argument("--binnedinput", type=str, default=None, help="Use existing binned data file.")
    parser.add_argument("--updatesites", type=str, default=None, help="Write out updated launch sites JSON file.")
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output (set logging level to DEBUG)")
    parser.add_argument("--s3_upload", action="store_true", default=False, help="Re-write data into S3 bucket (requires credentials!).")
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

    # Start up all of our uploader threads. We need many threads
    # to make S3 uploading not take ages.
    _threads = []
    if args.s3_upload:
        NUM_THREADS = 100
        for x in range(NUM_THREADS):
            _thread = Thread(target=uploader_thread)
            _thread.start()
            _threads.append(_thread)
        


    if (args.binnedinput is None):

        if args.folder is None:
            logging.critical("Need a folder to work on!")
            sys.exit(1)

        file_list = get_sonde_file_list(args.folder)

        logging.info(f"Working on {len(file_list)} files.")

        binned_data = {}

        file_count = len(file_list)
        unknown_sondes = 0
        already_allocated = 0
        count = 1

        for _file in file_list:

            _summary = load_summary_file(_file)

            if _summary is None:
                continue
            
            _first = _summary[0]
            _burst = _summary[1]
            _last = _summary[2]
            _serial = _summary[0]['serial']

            if 'launch_site' in _first:
                # This summary already has a launch site allocated.
                already_allocated += 1
                continue

            (_site_bin, _site_range) = bin_launch_data(_first, sites, radius=args.radius, alt_limit=args.alt)

            if _site_bin:
                logging.debug(f"{count}/{file_count} - {_serial}: {sites[_site_bin]['station_name']}, {_site_range:.1f} km")

                if _site_bin not in binned_data:
                    binned_data[_site_bin] = {'site': sites[_site_bin], 'serials':[], 'serial_data':{}}
                
                binned_data[_site_bin]['serials'].append(_serial)
                binned_data[_site_bin]['serial_data'][_serial] = _summary

                # Add in launch site data to all three entries in the summary.
                _summary[0]['launch_site'] = _site_bin
                _summary[0]['launch_site_range_estimate'] = _site_range*1000
                _summary[1]['launch_site'] = _site_bin
                _summary[1]['launch_site_range_estimate'] = _site_range*1000
                _summary[2]['launch_site'] = _site_bin
                _summary[2]['launch_site_range_estimate'] = _site_range*1000


                if(args.s3_upload):
                    # Put data into the upload queue for uploading by the many worker threads.
                    upload_queue.put(_summary)


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
        logging.info(f"Sondes already allocated: {already_allocated}/{file_count}")

    if args.s3_upload:
        # If uploading back into S3, just spin here and print out the number of
        # items in the upload queue. The operator can hit Ctrl-C when the number
        # stays at 0.
        try:
            while True:
                logging.info(f"Items in upload queue: {upload_queue.qsize()}")
                time.sleep(5)
        except KeyboardInterrupt:
            sys.exit(1)



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