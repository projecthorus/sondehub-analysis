# Analysis Utilities for SondeHub DB Archive Data

Some scripts that I've been using to analyse Sondehub data. Note that these have very little error checking!

### Authors
* Mark Jessop <vk5qi(at)rfhead.net>

## Dependencies
You will need the awscli python lib for this:
```
$ python -m venv venv
$ . venv/bin/activate
$ pip install awscli numpy matplotlib
```

### Optional AWS Configurations
In `~/.aws/config`:
```
[default]
s3 =
  max_concurrent_requests = 100
  max_queue_size = 10000
  multipart_threshold = 64MB
  multipart_chunksize = 16MB
  max_bandwidth = 50MB/s
  use_accelerate_endpoint = false
  addressing_style = path
```

## Preparation

### Grab latest launchSites.json
```
$ wget https://raw.githubusercontent.com/projecthorus/sondehub-tracker/testing/launchSites.json
```

### Download Sonde Summary Datasets
The sonde 'summary' datasets provide first/highest/last telemetry snapshots for every sonde serial number observed by the SondeHub network. This information is enough to perform quite a lot of analysis, such as assigning sondes to launch sites, and determining mean flight profile parameters.

To grab a month worth of summary data, in this case January 2021:

```
aws s3 cp --recursive --no-sign-request s3://sondehub-history/date/2021/01/ sondes_2021/01/
```

You can try and grab an entire year if you want:
```
aws s3 cp --recursive --no-sign-request s3://sondehub-history/date/2021/ sondes_2021/
```
This will take a long time...

The rest of this codebase assumes your directory structure looks like: `toplevel/month/day/serial.json`

## Binning Data to Launch Sites
The aim of this step is to estimate what launch site each sonde serial number was launched from. We do this by calculating the distance of the sondes first observed position from each launch site, and picking the smallest (if it is less than a provided radius - by default 30km). We also only make use of positions that were less than 5km in altitude, to avoid issues with sondes flying over other launch sites (it happens!).

Now that we have a folder structure containing sonde summary data, we can bin to launch sites by running:
```
$ python bin_sonde_summaries.py --folder sondes_2021/
2021-08-22 15:18:25,985 INFO: Loaded 704 launch sites.
2021-08-22 15:18:26,414 INFO: Working on 50732 files.
2021-08-22 15:18:29,261 INFO: 1000/50732 processed.
2021-08-22 15:18:32,297 INFO: 2000/50732 processed.
... lots of lines ...
2021-08-22 15:21:25,136 INFO: 50000/50732 processed.
2021-08-22 15:21:27,443 INFO: Sonde Summary processing complete!
2021-08-22 15:21:29,056 INFO: Wrote binned data to binned_sites.json.
2021-08-22 15:21:29,056 INFO: Sondes that could not be binned: 17858/50732
```

You can also add the `-v` option to get a very verbose output, including the site result for each sonde (often many tens of thousands of lines!).

Once finished the script will produce a file `binned_sites.json` which contains a dictionary, indexed by station code (refer launchSites.json), with each element containing the serial numbers associated with that site, and the telemetry data for each of those serial numbers. To avoid having to reprocess each individual sonde telemetry file each time, you can use the argument `--binnedinput binned_sites.json`.

### Flight Profile Analysis
By adding `--postanalysis` the script will analyse the sonde telemetry for each site, calculating the mean and standard deviation for burst altitudes and landing descent rates. 

```
$ python bin_sonde_summaries.py --binnedinput binned_sites.json --postanalysis
2021-08-22 15:46:56,647 INFO: Loaded 704 launch sites.
2021-08-22 15:46:57,779 INFO: Washington DC, Washington-Dulles International Airport (United States) (72403): 583 sondes - Bursts (431): 32099 m, 3115 m std-dev; Landing Rates (380): 5.4 m/s, 3.0 m/s std-dev; LMS6-400: 302; RS41-SGP: 20; DFM17: 31; RS41-NG: 29; DFM09: 7
2021-08-22 15:46:57,782 INFO: Wien / Hohe Warte (Austria) (11035): 443 sondes - Bursts (300): 30991 m, 5941 m std-dev; Landing Rates (270): 8.0 m/s, 3.4 m/s std-dev; M20: 41; RS41-SG: 234; RS41: 1
2021-08-22 15:46:57,784 INFO: Whenuapai (New Zealand) (93112): 410 sondes - Bursts (277): 26586 m, 3083 m std-dev; Landing Rates (270): 12.3 m/s, 2.7 m/s std-dev; RS41-SG: 270; RS41: 2
2021-08-22 15:46:57,786 INFO: Payerne (Switzerland) (06610): 425 sondes - Bursts (291): 34737 m, 4760 m std-dev; Landing Rates (258): 6.0 m/s, 2.9 m/s std-dev; RS41-SG: 251; M10: 4; RS41: 8

... many more lines
```

You can optionally update the data in `launchSites.json` and write out an updated file using the `--updatesites outputfile.json` option.

## Plotting Data for a specific Launch Site
We can plot out the burst altitudes and ascent/descent rates for a station by running:
```
$ python plot_site_data.py --binnedinput binned_sites.json 94672
```

(This also shows the observed transmit frequencies).