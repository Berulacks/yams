#!/usr/bin/env python3

from pathlib import Path
import argparse
import os
import yaml

HOME=str(Path.home())

PROGRAM_HOMES=[
        "{}/.config/yams".format(HOME),
        "{}/.yams".format(HOME),
        HOME
        ]

CONFIG_FILE="yams.yml"

DEFAULTS={
        "scrobble_threshold":50,
        "scrobble_min_time":10,
        "watch_threshold":5,
        "update_interval":1,
        "base_url":"http://ws.audioscrobbler.com/2.0/",
        "session_file":".lastfm_session",
        "mpd_host":"127.0.0.1",
        "mpd_port":"6600",
        "api_key":"MISSING",
        "real_time":True,
        "allow_same_track_scrobble_in_a_row":False,
        "api_secret":"MISSING"
        }

def write_config_to_file(path,config):
    print("Writing config...")
    with open(path,"w+") as config_stream:
        yaml.dump(config,config_stream,default_flow_style=False,Dumper=yaml.Dumper)
    print("Config written to: ".format(path))

def read_from_file(path,working_config):
    try:
        with open(path) as config_stream:
            config = yaml.load(config_stream)

            print("Config found, reading from config at {}...".format(path))
            for key in config.keys():
                working_config[key] = config[key]
                #print("Reading {} from file: {}".format(str(key),str(config[key])))
    except Exception as e:
        print("Couldn't open config at path {}!: {}".format(path,e))

def configure():

    #0 Find home directory
    home = "."

    # Check for a config first
    for potential_home in PROGRAM_HOMES:
        if Path(potential_home,CONFIG_FILE).exists():
            home=str(potential_home)
            break
    # If none go for whichever directory actually exists
    if home == ".":
        for potential_home in PROGRAM_HOMES:
            if Path(potential_home).exists():
                home=str(potential_home)
                break
    config_path=str(Path(home,CONFIG_FILE))

    #1 Defaults:
    config = DEFAULTS
    config["session_file"] = str(Path(home,DEFAULTS["session_file"]))
    #2 Environment variables
    if 'MPD_HOST' in os.environ:
        config['mpd_host']=os.environ['MPD_HOST']
    if 'MPD_PORT' in os.environ:
        config['mpd_port']=os.environ['MPD_PORT']
    #3 User config
    read_from_file(config_path,config)

    #4 CLI Arguments

    parser = argparse.ArgumentParser(prog="YAMS", description="Yet Another Mpd Scrobbler",formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-m', '--mpd-host', type=str, help="Your MPD instance's host", metavar='127.0.0.1')
    parser.add_argument('-p', '--mpd-port', type=int, help="Your MPD instance's port", metavar='6600')
    parser.add_argument('-s', '--session-file-path', type=str, help='Where to read in/save your session file to. Defaults to inside your config directory.', metavar='./.lastfm_session')
    parser.add_argument('--api-key', type=str, help='Your last.fm api key', metavar='wdoqwnd10j2903j013r')
    parser.add_argument('--api-secret', type=str, help='Your last.fm api secret', metavar='oegnapj390rj2q')
    parser.add_argument('-t', '--scrobble-threshold', type=int, help='The minimum point at which to scrobble, defaults to 50 percent', metavar='50')
    parser.add_argument('-r', '--real-time', action='store_true', help="Use real times when calculating scrobble times? (e.g. how long you've been running the app, not the track time reported by mpd). Default: True")
    parser.add_argument('-d', '--allow-duplicate-scrobbles', action='store_true', help='Allow the program to scrobble the same track multiple times in a row? Default: False')
    parser.add_argument('-c', '--config', type=str, help="Your config to read", metavar='~/my_config')
    parser.add_argument('-g', '--generate-config', action='store_true', help='Automatically save/update a configuration file. Good for bootsrapping.')

    args = parser.parse_args()

    if args.mpd_host:
        config['mpd_host']=args.mpd_host
    if args.mpd_port:
        config['mpd_port']=args.mpd_port
    if args.session_file_path:
        config["session_file"]=args.session_file_path
    if args.api_key:
        config["api_key"]=args.api_key
    if args.api_secret:
        config["api_secret"]=args.api_key
    if args.scrobble_threshold:
        config["scrobble_threshold"]=args.scrobble_threshold
    if args.real_time:
        config["real_time"]=args.real_time
    if args.allow_duplicate_scrobbles:
        config["allow_same_track_scrobble_in_a_row"]=args.allow_duplicate_scrobbles
    if args.config:
        read_from_file(args.config,config)
    if args.generate_config:
        write_config_to_file(config_path,config)


    #5 Sanity check
    if( config['mpd_host'] == "" or
        config['api_key'] == "" or
        config['api_secret'] == ""):
        print("Error! Your config is missing some values. Please check your config. (Note: You can generate a config file with the '-g' flag.")
        print(config)
        exit(1)

    return config





