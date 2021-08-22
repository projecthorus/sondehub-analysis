#!/usr/bin/env python
#
#   Utility functions to help with analysing Sondehub Data
#
#   Copyright (C) 2021  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import json
import glob
import math
import os.path
from math import radians, degrees, sin, cos, atan2, sqrt, pi
import numpy as np


def position_info(listener, balloon):
    """
    Calculate and return information from 2 (lat, lon, alt) tuples

    Copyright 2012 (C) Daniel Richman; GNU GPL 3

    Returns a dict with:

     - angle at centre
     - great circle distance
     - distance in a straight line
     - bearing (azimuth or initial course)
     - elevation (altitude)

    Input and output latitudes, longitudes, angles, bearings and elevations are
    in degrees, and input altitudes and output distances are in meters.
    """

    # Earth:
    # radius = 6371000.0
    radius = 6364963.0  # Optimized for Australia :-)

    (lat1, lon1, alt1) = listener
    (lat2, lon2, alt2) = balloon

    lat1 = radians(lat1)
    lat2 = radians(lat2)
    lon1 = radians(lon1)
    lon2 = radians(lon2)

    # Calculate the bearing, the angle at the centre, and the great circle
    # distance using Vincenty's_formulae with f = 0 (a sphere). See
    # http://en.wikipedia.org/wiki/Great_circle_distance#Formulas and
    # http://en.wikipedia.org/wiki/Great-circle_navigation and
    # http://en.wikipedia.org/wiki/Vincenty%27s_formulae
    d_lon = lon2 - lon1
    sa = cos(lat2) * sin(d_lon)
    sb = (cos(lat1) * sin(lat2)) - (sin(lat1) * cos(lat2) * cos(d_lon))
    bearing = atan2(sa, sb)
    aa = sqrt((sa ** 2) + (sb ** 2))
    ab = (sin(lat1) * sin(lat2)) + (cos(lat1) * cos(lat2) * cos(d_lon))
    angle_at_centre = atan2(aa, ab)
    great_circle_distance = angle_at_centre * radius

    # Armed with the angle at the centre, calculating the remaining items
    # is a simple 2D triangley circley problem:

    # Use the triangle with sides (r + alt1), (r + alt2), distance in a
    # straight line. The angle between (r + alt1) and (r + alt2) is the
    # angle at the centre. The angle between distance in a straight line and
    # (r + alt1) is the elevation plus pi/2.

    # Use sum of angle in a triangle to express the third angle in terms
    # of the other two. Use sine rule on sides (r + alt1) and (r + alt2),
    # expand with compound angle formulae and solve for tan elevation by
    # dividing both sides by cos elevation
    ta = radius + alt1
    tb = radius + alt2
    ea = (cos(angle_at_centre) * tb) - ta
    eb = sin(angle_at_centre) * tb
    elevation = atan2(ea, eb)

    # Use cosine rule to find unknown side.
    distance = sqrt((ta ** 2) + (tb ** 2) - 2 * tb * ta * cos(angle_at_centre))

    # Give a bearing in range 0 <= b < 2pi
    if bearing < 0:
        bearing += 2 * pi

    return {
        "listener": listener,
        "balloon": balloon,
        "listener_radians": (lat1, lon1, alt1),
        "balloon_radians": (lat2, lon2, alt2),
        "angle_at_centre": degrees(angle_at_centre),
        "angle_at_centre_radians": angle_at_centre,
        "bearing": degrees(bearing),
        "bearing_radians": bearing,
        "great_circle_distance": great_circle_distance,
        "straight_distance": distance,
        "elevation": degrees(elevation),
        "elevation_radians": elevation,
    }



def getDensity(altitude):
    """ 
	Calculate the atmospheric density for a given altitude in metres.
	This is a direct port of the oziplotter Atmosphere class
	"""

    # Constants
    airMolWeight = 28.9644  # Molecular weight of air
    densitySL = 1.225  # Density at sea level [kg/m3]
    pressureSL = 101325  # Pressure at sea level [Pa]
    temperatureSL = 288.15  # Temperature at sea level [deg K]
    gamma = 1.4
    gravity = 9.80665  # Acceleration of gravity [m/s2]
    tempGrad = -0.0065  # Temperature gradient [deg K/m]
    RGas = 8.31432  # Gas constant [kg/Mol/K]
    R = 287.053
    deltaTemperature = 0.0

    # Lookup Tables
    altitudes = [0, 11000, 20000, 32000, 47000, 51000, 71000, 84852]
    pressureRels = [
        1,
        2.23361105092158e-1,
        5.403295010784876e-2,
        8.566678359291667e-3,
        1.0945601337771144e-3,
        6.606353132858367e-4,
        3.904683373343926e-5,
        3.6850095235747942e-6,
    ]
    temperatures = [288.15, 216.65, 216.65, 228.65, 270.65, 270.65, 214.65, 186.946]
    tempGrads = [-6.5, 0, 1, 2.8, 0, -2.8, -2, 0]
    gMR = gravity * airMolWeight / RGas

    # Pick a region to work in
    i = 0
    if altitude > 0:
        while altitude > altitudes[i + 1]:
            i = i + 1

    # Lookup based on region
    baseTemp = temperatures[i]
    tempGrad = tempGrads[i] / 1000.0
    pressureRelBase = pressureRels[i]
    deltaAltitude = altitude - altitudes[i]
    temperature = baseTemp + tempGrad * deltaAltitude

    # Calculate relative pressure
    if math.fabs(tempGrad) < 1e-10:
        pressureRel = pressureRelBase * math.exp(
            -1 * gMR * deltaAltitude / 1000.0 / baseTemp
        )
    else:
        pressureRel = pressureRelBase * math.pow(
            baseTemp / temperature, gMR / tempGrad / 1000.0
        )

    # Add temperature offset
    temperature = temperature + deltaTemperature

    # Finally, work out the density...
    speedOfSound = math.sqrt(gamma * R * temperature)
    pressure = pressureRel * pressureSL
    density = densitySL * pressureRel * temperatureSL / temperature

    return density


def seaLevelDescentRate(descent_rate, altitude):
    """ Calculate the descent rate at sea level, for a given descent rate at altitude """

    rho = getDensity(altitude)
    return math.sqrt((rho / 1.225) * math.pow(descent_rate, 2))


def get_sonde_file_list(folder="."):
    """ Use glob to recurse through our sonde data store and return a list of all sondes files """
    return glob.glob(os.path.join(folder,"*/*/*.json"))


def load_summary_file(filename):
    _f = open(filename,'r')
    _data = _f.read()
    _f.close()

    try:
        data = json.loads(_data)

        # Summary data only has 3 entries, launch, burst and landing.
        if len(data) != 3:
            return None

        return data
    except:
        return None


def load_launch_sites(filename='launchSites.json'):
    """ Load in the launch sites dataset and rearrange it a bit to be useful later """
    _f = open(filename,'r')
    _data = _f.read()
    _f.close()

    data = json.loads(_data)

    output = {}

    for _site in data:
        output[_site['station']] = _site

    return output


def calculate_averages(serial_data, min_count=5, descent_max_alt=12000):
    """ Take a dictionary of sonde summary data (one key per serial) and calculate burst and descent rate statistics"""
    bursts = []

    descents = []

    _types = {}

    sonde_count = 0

    for _serial in serial_data:

        _first = serial_data[_serial][0]
        _burst = serial_data[_serial][1]
        _last = serial_data[_serial][2]

        _first_alt = float(_first['alt'])
        _burst_alt = float(_burst['alt'])
        _last_alt = float(_last['alt'])

        if (_burst_alt > _first_alt) and (_burst_alt > _last_alt):
            bursts.append(_burst_alt)
        
        if(_last_alt < _burst_alt):
            if 'vel_v' in _last:
                if (_last['vel_v'] < 0) and (_last_alt < descent_max_alt):
                    descents.append(seaLevelDescentRate(_last['vel_v'], _last_alt))

        if 'subtype' in _last:
            _type = _last['subtype']
        else:
            _type = _last['type']


        if 'Sondehub' not in _type:
            if _type not in _types:
                _types[_type] = 1
            else:
                _types[_type] += 1
        
        

    output = {'type':_types, 'burst_count': len(bursts), 'descent_count': len(descents)}
        
    if len(bursts) >= min_count:
        output['burst_mean'] = np.mean(bursts)
        output['burst_std'] = np.std(bursts)
    else:
        return None
    
    if len(descents) >= min_count:
        output['descent_mean'] = np.mean(descents)
        output['descent_std'] = np.std(descents)
    else:
        output['descent_mean'] = -999.0
        output['descent_std'] = -999.0

    return output