#!/usr/bin/env python3

from pathlib import Path
import argparse
import os
import yaml
import signal
import logging
import subprocess
from yams import VERSION
from sys import exit

HOME=str(Path.home())
LOGGING_ENABLED=False

PROGRAM_HOMES=[
        "{}/.config/yams".format(HOME),
        "{}/.yams".format(HOME),
        './.yams',
        '.',
        HOME
        ]

CREATE_IF_NOT_EXISTS_HOME="{}/.config/yams".format(HOME)

CONFIG_FILE="yams.yml"
LOG_FILE_NAME="yams.log"
DEFAULT_SESSION_FILENAME=".lastfm_session"
DEFAULT_PID_FILENAME="yams.pid"
DEFAULT_CACHE_FILENAME="scrobbles.cache"

DEFAULTS={
        "scrobble_threshold":50,
        "scrobble_min_time":10,
        "watch_threshold":5,
        "update_interval":1,
        "base_url":"http://ws.audioscrobbler.com/2.0/",
        "mpd_host":"127.0.0.1",
        "mpd_port":"6600",
        "api_key": "293ef0836603c5c8023ba86eb413794b",
        "api_secret": "e952c611efe32c66f2b48a93b39d6219",
        "real_time":True,
        "allow_same_track_scrobble_in_a_row":False,
        "disable_log":False,
        "no_daemon":False,
        }

logger = logging.getLogger("yams")

def write_config_to_file(path,config):
    logger.info("Writing config...")
    with open(path,"w+") as config_stream:
        yaml.dump(config,config_stream,default_flow_style=False,Dumper=yaml.Dumper)
    logger.info("Config written to: {}".format(path))

def read_from_file(path,working_config):
    try:
        with open(path) as config_stream:
            config = yaml.load(config_stream)

            logger.info("Config found, reading from config at {}...".format(path))
            for key in config.keys():
                working_config[key] = config[key]
                #logger.info("Reading {} from file: {}".format(str(key),str(config[key])))
    except Exception as e:
        logger.info("Couldn't open config at path {}!: {}".format(path,e))

def bootstrap_config():
    """ Creates a config directory and writes a suitable base config into it"""

    # No custom home directory was found, lets create one

    home = Path(CREATE_IF_NOT_EXISTS_HOME)
    home.mkdir(parents=True)

    default_config=DEFAULTS

    default_config['session_file']=str(Path(home,DEFAULT_SESSION_FILENAME))

    # Lets recognize environment variables by the user
    if 'MPD_HOST' in os.environ:
        default_config['mpd_host']=os.environ['MPD_HOST']
    if 'MPD_PORT' in os.environ:
        default_config['mpd_port']=os.environ['MPD_PORT']

    write_config_to_file(str(Path(home,CONFIG_FILE)), DEFAULTS)

    return str(home)

def get_home_dir():
    """ Returns the home directory for YAMS files (not to be confused with your system home directory """

    home = "."

    # Check for a config first
    for potential_home in PROGRAM_HOMES:
        if Path(potential_home,CONFIG_FILE).exists():
            home=str(potential_home)
            return home

    # If config's found, go for whichever directory actually exists
    for potential_home in PROGRAM_HOMES:
        if potential_home != "." and potential_home != HOME and Path(potential_home).exists():
            home=str(potential_home)
            return home

    # No custom home directory was found, lets create one
    return bootstrap_config()

def kill(path):

    try:
        with open(path, "r") as pid_file:
            try:
                pid = pid_file.readlines()[0].strip()
                logger.warn("Killing process #{pid} and shutting down...".format(pid=pid))
                pid = int(pid)
            except Exception as e:
                logger.error("Failed to kill process {pid}: {error}".format(pid=str(pid), error=e))
                logger.warn("Shutting down...")
                exit(1)
    except Exception as e:
        logger.error("Failed to open pid file {filename}: {error}".format(filename=str(path), error=e))
        logger.warn("Shutting down...")
        exit(1)

    os.remove(path)
    os.kill(pid,signal.SIGTERM)
    exit(0)

def is_pid_running(config):
    try:
        if "pid_file" in config and os.path.exists(config["pid_file"]):
            with open(config["pid_file"],"r") as pid_file:
                pid=int(pid_file.readlines()[0].strip())
                try:
                    logger.debug("Attempting to fake kill (check if running) process #{}".format(pid))
                    test=os.kill(pid,0)
                    logger.debug("Process {} is running".format(pid))
                    return True
                except Exception as e:
                    logger.debug("Process {} is not running!, Exception: {}".format(str(pid),str(e)))
                    return False

    except Exception as e:
        logger.debug("Couldn't detect old pid file, continuing. Error: {}".format(e))
        return False
    if not os.path.exists(config["pid_file"]):
        logger.debug("Could not find pid file at: {}".format(config["pid_file"]))
    return False

def watch_log(path):
    logger.info("Attaching to {}, press Ctrl-C to exit.".format(path))

    try:

        f = subprocess.Popen(['tail','-F',path],\
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        while True:
                line = f.stdout.readline()
                print(line.decode("utf-8").strip())

    except Exception as e:
        logger.info("Stream ended: {}".format(e))
    except:
        print("")
        logger.info("Stream ended")
    exit(0)

def process_cli_args():
    """ Process command line arguments"""

    parser = argparse.ArgumentParser(prog="YAMS", description="Yet Another Mpd Scrobbler, v{}. Configuration directories are either ~/.config/yams, ~/.yams, or your current working directory. Create one of these paths if need be.".format(VERSION))
    parser.add_argument('-m', '--mpd-host', type=str, help="Your MPD instance's host", metavar='127.0.0.1')
    parser.add_argument('-p', '--mpd-port', type=int, help="Your MPD instance's port", metavar='6600')
    parser.add_argument('-s', '--session-file-path', type=str, help='Where to read in/save your session file to. Defaults to inside your config directory.', metavar='./.lastfm_session')
    parser.add_argument('--api-key', type=str, help='Your last.fm api key', metavar='API_KEY')
    parser.add_argument('--api-secret', type=str, help='Your last.fm api secret', metavar='API_SECRET')
    parser.add_argument('-t', '--scrobble-threshold', type=int, help='The minimum point at which to scrobble, defaults to 50 percent', metavar='50')
    parser.add_argument('-r', '--real-time', action='store_true', help="Use real times when calculating scrobble times? (e.g. how long you've been running the app, not the track time reported by mpd). Default: True")
    parser.add_argument('-d', '--allow-duplicate-scrobbles', action='store_true', help='Allow the program to scrobble the same track multiple times in a row? Default: False')
    parser.add_argument('-g', '--generate-config', action='store_true', help='Save the entirety of the running configuration to the config file, including command line arguments. Use this if you always run yams a certain fashion and want that to be the default. Default: False')
    parser.add_argument('-l', '--log-file', type=str, help='Full path to a log file. If not set, a log file called "yams.log" will be placed in the current config directory.', default=None, metavar='/path/to/log')
    parser.add_argument('-c', '--cache-file', type=str, help='Full path to the scrobbles cache file. This stores failed scrobbles for upload at a later date. If not set, a log file called "scrobbles.cache" will be placed in the current config directory.', default=None, metavar='/path/to/cache')
    parser.add_argument('-C', '--config', type=str, help="Your config to read", metavar='~/my_config')
    parser.add_argument('-N', '--no-daemon', action='store_true', help='If set to true, program will not be run as a daemon (e.g. it will run in the foreground) Default: False')
    parser.add_argument('-D', '--debug', action='store_true', help='Run in Debug mode. Default: False')
    parser.add_argument('-k', '--kill-daemon', action='store_true', help='Will kill the daemon if running - will fail otherwise. Default: False')
    parser.add_argument('--disable-log', action='store_true', help='Disable the log? Default: False')
    parser.add_argument('-a', '--attach', action='store_true', help='Runs "tail -F" on a running instance of yams\' log file. "Attaches" to it, for all intents and purposes. NB: You will still need to kill it by hand. Default: False')

    return parser.parse_args()

def remove_log_streams():
    duplicate_handlers = logger.handlers.copy()

    for handler in duplicate_handlers:
        logger.removeHandler(handler)
        #logger.info("Removing {}".format(handler))

def remove_log_stream_of_type(handler_type):
    duplicate_handlers = logger.handlers.copy()

    for handler in duplicate_handlers:
        if type(handler) == handler_type:
            logger.removeHandler(handler)
            logger.debug("Removed log stream: {}".format(handler))

def set_log_file(path,level=logging.INFO):

    logger.info("Writing log to file: {}".format(path))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Remove old log handlers
    remove_log_stream_of_type(logging.FileHandler)

    fh = logging.FileHandler(path)
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

def add_log_stream_output(level=logging.INFO):

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setLevel(level)
    # create formatter and add it to the handlers
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def setup_logger(use_stream,use_file,level=logging.INFO):


    logger.setLevel(level)


    if use_file:
        # create file handler which logs even debug messages
        home = get_home_dir()
        path=str(Path(home,LOG_FILE_NAME))

        if os.path.exists(path):
            os.remove(path)

        set_log_file(path,level)
    if use_stream:
        add_log_stream_output(level)

def configure():

    #0 Find home directory and setup stream logger. Also find the config directory.
    args = process_cli_args()
    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    # If args.kill_daemon is true we don't want to touch the log file, but we still need to continue setting up incase there's a custom pid file to kill somewhere
    setup_logger(True,False,log_level)
    home = get_home_dir()
    config_path=str(Path(home,CONFIG_FILE))

    #1 Defaults:
    config = DEFAULTS
    #1.2 Home dependent defaults:
    config["session_file"] = str(Path(home,DEFAULT_SESSION_FILENAME))
    config["log_file"] = str(Path(home,LOG_FILE_NAME))
    config['pid_file']=str(Path(home,DEFAULT_PID_FILENAME))
    config['cache_file']=str(Path(home,DEFAULT_CACHE_FILENAME))
    #2 Environment variables
    if 'MPD_HOST' in os.environ:
        config['mpd_host']=os.environ['MPD_HOST']
    if 'MPD_PORT' in os.environ:
        config['mpd_port']=os.environ['MPD_PORT']
    #3 User config
    read_from_file(config_path,config)

    #4 CLI Arguments
    if args.config:
        read_from_file(args.config,config)
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
    if args.disable_log:
        config["disable_log"] = args.disable_log
    if args.log_file:
        config["log_file"] = args.log_file
    if args.cache_file:
        config["cache_file"] = args.cache_file

    #5 Sanity check
    if( config['mpd_host'] == "" or
        config['api_key'] == "" or
        config['api_secret'] == ""):
        logger.error("Error! Your config is missing some values. Please check your config. (Note: You can generate a config file with the '-g' flag.")
        logger.error(config)
        exit(1)

    #6 Write the config (if the user has requested it) - the config is final at this point
    if args.generate_config:
        write_config_to_file(config_path,config)
    #6.1 Lets do this after saving the config, as we don't ever really want to save this to disk
    if args.no_daemon:
        config['no_daemon']=args.no_daemon

    #7 Kill or not? (We're doing this all the way down here as the user might have defined a non-standard pid in their config file)
    if args.kill_daemon:
        kill(config['pid_file'])

   #8 Attach to a pre-existing log? watch_log ends the program when finished
    if args.attach:
        if is_pid_running(config):
            watch_log(config["log_file"])
        else:
            logger.error("Can't connect to running process of yams! Exiting...")
            exit(1)

    #9 Lets ensure we're not running a second instance of yams, this will kill the program if we are
    if is_pid_running(config):
        logger.error("YAMS is already running, kill it before running again!")
        exit(1)
    else:
        if os.path.exists(config["pid_file"]):
            os.remove(config["pid_file"])

    #10 Log file setup (specifically set after check_old_pid to ensure the previous log isn't deleted accidentally)
    if not args.kill_daemon and not config["disable_log"]:
        # The default
        path=config["log_file"]
        if os.path.exists(path):
            os.remove(path)
        set_log_file(path,log_level)

    return config





