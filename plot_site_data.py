#!/usr/bin/env python
#
#   Plot a launch sites burst / descent rate data
#

import argparse
import os
import sys
import logging
import pprint
import numpy as np
import matplotlib.pyplot as plt
from dateutil.parser import parse

from utils import *


if __name__ == "__main__":
    # Read command-line arguments
    parser = argparse.ArgumentParser(description="SondeHub Utils - Plot Binned Data", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("station", type=str, help="Station code to plot, e.g. 94672")
    parser.add_argument("--binnedinput", type=str, default=None, help="Use existing binned data file.")
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

    # Load Input file
    _f = open(args.binnedinput,'r')
    _data = _f.read()
    _f.close()
    binned_data = json.loads(_data)

    if args.station not in binned_data:
        logging.critical(f"Could not find station {args.station} in binned data!")
        sys.exit(1)
    
    _site_name = sites[args.station]['station_name']
    serial_data = binned_data[args.station]['serial_data']

    logging.info(f"Found {len(serial_data)} Serial numbers.")

    bursts = []
    burst_times = []
    descents = []
    descent_times = []
    ascents = []
    ascent_times = []
    freqs = []
    freq_times = []

    descent_max_alt = 12000

    for _serial in serial_data:
        _first = serial_data[_serial][0]
        _burst = serial_data[_serial][1]
        _last = serial_data[_serial][2]

        _first_alt = float(_first['alt'])
        _burst_alt = float(_burst['alt'])
        _last_alt = float(_last['alt'])


        _first_time = parse(_first['datetime'])
        _burst_time = parse(_burst['datetime'])

        try:
            freqs.append(_last['frequency'])
            freq_times.append(_first_time)
        except:
            pass

        if (_burst_alt > _first_alt) and (_burst_alt > _last_alt):
            bursts.append(_burst_alt)
            burst_times.append(parse(_burst['datetime']))

            _ascent_time = (_burst_time - _first_time).total_seconds()
            _ascent_rate = (_burst_alt - _first_alt)/_ascent_time

            ascents.append(_ascent_rate)
            ascent_times.append(_first_time)
        
        if(_last_alt < _burst_alt):
            if 'vel_v' in _last:
                if (_last['vel_v'] < 0) and (_last_alt < descent_max_alt):
                    descents.append(seaLevelDescentRate(_last['vel_v'], _last_alt))
                    descent_times.append(parse(_last['datetime']))

    logging.info(f"Extracted {len(bursts)} Burst Altitude Datapoints.")
    logging.info(f"Extracted {len(descents)} Landing Rate Datapoints")
    logging.info(f"Extracted {len(freqs)} Frequency Datapoints")

    plt.figure(figsize=(12,6))
    plt.title(f"{_site_name} - Burst Altitudes")
    plt.scatter(burst_times, bursts, color='C0')
    plt.ylabel("Altitude (m)")
    plt.axhline(np.median(bursts), label=f'Median ({np.median(bursts):.0f} m)', color='C1')
    plt.axhline(np.median(bursts)+np.std(bursts), label=f'+1 Std-Dev ({np.std(bursts):.0f} m)', linestyle='--', color='C2')
    plt.axhline(np.median(bursts)-np.std(bursts), label=f'-1 Std-Dev (-{np.std(bursts):.0f} m)', linestyle='--', color='C2')
    plt.legend()
    plt.grid()

    plt.figure(figsize=(12,6))
    plt.title(f"{_site_name} - Ascent Rates")
    plt.scatter(ascent_times, ascents, color='C0')
    plt.axhline(np.median(ascents), label=f'Median ({np.median(ascents):.1f} m/s)', color='C1')
    plt.axhline(np.median(ascents)+np.std(ascents), label=f'+1 Std-Dev ({np.std(ascents):.1f} m/s)', linestyle='--', color='C2')
    plt.axhline(np.median(ascents)-np.std(ascents), label=f'-1 Std-Dev (-{np.std(ascents):.1f} m/s)', linestyle='--', color='C2')
    plt.ylabel("Average Ascent Rate (m/s)")
    plt.legend()
    plt.grid()

    plt.figure(figsize=(12,6))
    plt.title(f"{_site_name} - Landing Rates")
    plt.scatter(descent_times, descents, color='C0')
    plt.axhline(np.median(descents), label=f'Median ({np.median(descents):.1f} m/s)', color='C1')
    plt.axhline(np.median(descents)+np.std(descents), label=f'+1 Std-Dev ({np.std(descents):.1f} m/s)', linestyle='--', color='C2')
    plt.axhline(np.median(descents)-np.std(descents), label=f'-1 Std-Dev (-{np.std(descents):.1f} m/s)', linestyle='--', color='C2')
    plt.ylabel("Estimated Landing Rate (m/s)")
    plt.legend()
    plt.grid()

    plt.figure(figsize=(12,6))
    plt.title(f"{_site_name} - Transmit Frequencies")
    plt.scatter(freq_times, freqs, color='C0')
    plt.ylabel("Transmit Frequency (MHz)")
    plt.legend()
    plt.grid()

    plt.show()