#!/usr/bin/env python3

import requests, hashlib
import xml.etree.ElementTree as ET
from mpd import MPDClient
import select
from pathlib import Path
import time
import logging
import yaml
import os
from sys import exit

from yams.configure import configure, remove_log_stream_of_type
import yams

MAX_TRACKS_PER_SCROBBLE=50
SCROBBLE_RETRY_INTERVAL=10
SCROBBLE_DISK_SAVE_INTERVAL=1200

logger = logging.getLogger("yams")

SCROBBLES=str(Path(Path.home(),'.config/yams/scrobbles.cache'))

def save_failed_scrobbles_to_disk(path,scrobbles):
    logger.info("Writing scrobbles to disk...")
    if os.path.exists(path):
        os.remove(path)

    with open(path,"w+") as file_stream:
        yaml.dump({"scrobbles":scrobbles},file_stream,default_flow_style=False,Dumper=yaml.Dumper)
    logger.info("Failed scrobbles written to: {}".format(path))

def read_failed_scrobbles_from_disk(path):

    if os.path.exists(path):
        try:
            with open(path) as scrobbles_file_stream:
                scrobbles_file = yaml.load(scrobbles_file_stream)

                logger.info("Scrobbles found, reading from file at {}...".format(path))
                if "scrobbles" in scrobbles_file:
                    for scrobble in scrobbles_file["scrobbles"]:
                        for key in scrobble.keys():
                            logger.debug("[{}]: {}".format(key, scrobble[key]))
                    return scrobbles_file["scrobbles"]
        except Exception as e:
            logger.warn("Couldn't read failed scrobbles file!: {}".format(e))
    return []


def sign_signature(parameters,secret=""):
    """
    Create a signature for a signed request
    :param parameters: The parameters being sent in the Last.FM request
    :param secret: The API secret for your application
    :type parameters: dict
    :type secret: str

    :return: The actual signature itself
    :rtype: str
    """
    keys=parameters.keys()
    keys=sorted(keys)

    to_hash = ""

    hasher = hashlib.md5()
    for key in keys:
        hasher.update(str(key).encode("utf-8"))
        hasher.update(str(parameters[key]).encode("utf-8"))
        #to_hash += str(key)+str(parameters[key])
        logger.debug("Hashing: {}".format(str(key)+str(parameters[key])))

    if len(secret) > 0:
        hasher.update(secret.encode("utf-8"))

    hashed_form = hasher.hexdigest()
    logger.debug("Signature for call: {}".format(hashed_form))

    return hashed_form

def make_request(url,parameters,POST=False,debug=False):
    """
    Make a generic GET or POST request to an URL, and parse its resultant XML. Can throw an exception.
    :param url: The URL to make the request to
    :param parameters: A dictionary of data to send with your request
    :param POST: (Optional) A POST request will be sent (instead of GET) if this is True

    :type url: str
    :type parameters: dict
    :type POST: bool

    :return: The parsed XML object
    :rtype: xml.etree.ElementTree
    """

    if not POST:
        response = requests.get(url,parameters)
    else:
        response = requests.post(url,data=parameters)

    if debug:
        logger.debug(response.text)

    if response.ok:
        try:
            xml = ET.fromstring(response.text)
            return xml
        except Exception as e:
            logger.error("Something went wrong parsing the XML. Error: {}. Failing...".format(e))
            return None
    logger.info("Got a fucked up response! Status: {}, Reason: {}".format(response.status_code, response.reason))
    logger.info("Response: {}".format(response.text))
    return None

def get_token(url,api_key,api_secret):
    """
    Fetch a Last.FM authentication token from its servers

    :param url: The base Last.FM API url
    :param api_key: Your API key
    :param api_secret: Your AP secret (given to you when you got your API key)

    :type url: str
    :type api_key: str
    :type api_secret: str

    :return: The token received from the server
    :rtype: str
    """

    parameters = {
            "api_key":api_key,
            "method":"auth.gettoken",
            }
    parameters["api_sig"] = sign_signature(parameters,api_secret)

    xml = make_request(url, parameters)

    token = xml.find("token").text
    logger.debug("Token: {}".format(token))

    return token

def get_session(url,token,api_key,api_secret):
    """
    Try to grab a Last.FM session key for a given token. Note that this must be done after a user manually authenticates with Last.FM and confirms your token.

    :param url: The base Last.FM API url
    :param token: Your token
    :param api_key: Your API key
    :param api_secret: Your AP secret (given to you when you got your API key)

    :type url: str
    :type token: str
    :type api_key: str
    :type api_secret: str

    :return: The session key received from the server
    :rtype: str
    """
    parameters = {
            "token":token,
            "api_key":api_key,
            "method":"auth.getsession"
            }
    parameters["api_sig"]=sign_signature(parameters,api_secret)

    xml = make_request(url,parameters)

    session = xml.find("session")
    username = session.find("name").text
    session_key = session.find("key").text
    logger.debug("Key: {},{}".format(username,session_key))

    return (username,session_key)

def authenticate(token,base_url,api_key,api_secret):
    """
    Authenticate with Last.FM using a given token. Prompt and wait on the user to sign in to Last.FM. Keep trying to grab the session details afterwards.

    :param token: Your token
    :param url: The base Last.FM API url
    :param api_key: Your API key
    :param api_secret: Your AP secret (given to you when you got your API key)

    :type token: str
    :type url: str
    :type api_key: str
    :type api_secret: str

    :return: A tuple of the user's name and validated session key
    :rtype: (str,str)
    """

    input("Press Enter after you've granted scrobble.py permission to access your account...")
    try:
        logger.info("Grabbing session...")
        session_info = get_session(base_url,token,api_key,api_secret)
        logger.info("User: {}".format(session_info[0]))
        logger.info("Session: {}".format(session_info[1]))

        return session_info
    except Exception as e:
        logger.error("Couldn't grab session, reason: {}".format(e))

    # Keep looping forever, the program won't be able to do anything without a session, anyway.
    return authenticate(token,base_url,api_key,api_secret)

def save_credentials(session_filepath, user_name, session_key):
    """Save authentication credentials to disk.

    :param session_filepath: The path of the file to save to
    :param user_name: Your username
    :param session_key: Your session_key

    :type session_filepath: str
    :type user_name: str
    :type session_key: str
    """

    with open(session_filepath,"w+") as session_file:
        session_file.write(str(user_name)+"\n")
        session_file.write(str(session_key)+"\n")

def now_playing(track_info,url,api_key,api_secret,session_key):
    """
    Send your currently playing track's info to Last.FM

    :param track_info: The track's info from mpd
    :param url: The base Last.FM API url
    :param token: Your token
    :param api_key: Your API key
    :param api_secret: Your AP secret (given to you when you got your API key)

    :type track_info: dict
    :type url: str
    :type token: str
    :type api_key: str
    :type api_secret: str
    """

    parameters = {
            "method":"track.updateNowPlaying",
            "artist": track_info['artist'],
            "track": track_info["title"],
            "context": "mpd",
            "api_key": api_key,
            "sk": session_key,
            }

    if "album" in track_info:
        parameters["album"]=track_info["album"]
    if "track" in track_info:
        parameters["trackNumber"]=track_info["track"]
    if "time" in track_info:
        parameters["duration"]=track_info["time"]

    parameters["api_sig"] = sign_signature(parameters,api_secret)

    #logger.info(parameters)

    try:
        xml = make_request(url,parameters,True)
        #logger.info(xml.tag)
        #for child in xml[0]:
        #    logger.info(child.text)
        logger.info("Now playing was a success!")
    except Exception as e:
        logger.warn("Could not send now playing Last.FM!")
        logger.debug("Error: {}".format(e))

def scrobble_tracks(tracks,url,api_key,api_secret,session_key):

    # Sanity check
    if len(tracks) < 1:
        logger.debug("Failed sanity check for scrobble tracks")
        return

    logger.info("Attempting mass scroble for {} tracks!".format(len(tracks)))
    parameters = {
            "method":"track.scrobble",
            "api_key": api_key,
            "sk": session_key,
            }

    max_scrobbles = MAX_TRACKS_PER_SCROBBLE if len(tracks) > MAX_TRACKS_PER_SCROBBLE else len(tracks)

    for i in range(0,max_scrobbles):
        logger.debug("Adding {} to mass scrobble request.".format(tracks[i]))
        parameters["track[{}]".format(i)]= tracks[i]["title"]
        parameters["artist[{}]".format(i)]= tracks[i]["artist"]
        parameters["timestamp[{}]".format(i)]= tracks[i]["timestamp"]
        if "album" in tracks[i]:
            parameters["album[{}]".format(i)]= tracks[i]["album"]
        if "trackNumber" in tracks[i]:
            parameters["trackNumber[{}]".format(i)]= tracks[i]["trackNumber"]
        if "duration" in tracks[i]:
            parameters["duration[{}]".format(i)]= tracks[i]["duration"]

    parameters["api_sig"] = sign_signature(parameters,api_secret)

    try:
        xml = make_request(url,parameters,True)
        if xml:
            logger.debug("Received response: [{}] - {}".format(xml.tag,xml.attrib))
            logger.debug("XML Received for mass scrobble: {}".format(ET.tostring(xml, encoding="utf-8").decode("utf-8")))

            accepted = int(xml.find("scrobbles").get("accepted"))
            if accepted > 0:
                logger.info("Scrobbles accepted: {}".format(accepted))
                logger.info("Mass scrobbling was a success!")

                return True
            else:
                logger.warn("Failed to scrobble {num_tracks} tracks, queuing for later.".format(num_tracks=len(tracks)))
        else:
            logger.warn("Failed to scrobble {num_tracks} tracks, queuing for later.".format(num_tracks=len(tracks)))
    except Exception as e:
        logger.warn("Failed to scrobble {num_tracks} tracks, queuing for later.".format(num_tracks=len(tracks)))
        logger.debug("Error: {}".format(e))

    return False


def record_failed_scrobble(track_info,timestamp,failed_scrobbles,cache_file_path):
    failed_scrobble = {
            "artist": track_info['artist'],
            "title": track_info["title"],
            "timestamp":timestamp
            }

    if "album" in track_info:
        failed_scrobble["album"]=track_info["album"]
    if "track" in track_info:
        failed_scrobble["trackNumber"]=track_info["track"]
    if "time" in track_info:
        failed_scrobble["duration"]=track_info["time"]

    if failed_scrobble not in failed_scrobbles:
        failed_scrobbles.append(failed_scrobble)
        save_failed_scrobbles_to_disk(cache_file_path,failed_scrobbles)


def scrobble_track(track_info,timestamp,url,api_key,api_secret,session_key):
    """
    Scrobble your track with Last.FM

    :param track_info: The track's info from mpd
    :param timestamp: The starting time of the track, as a UTC Unix Timestamp (seconds since the Epoch)
    :param url: The base Last.FM API url
    :param token: Your token
    :param api_key: Your API key
    :param api_secret: Your AP secret (given to you when you got your API key)

    :type track_info: dict
    :param timestamp: int
    :type url: str
    :type token: str
    :type api_key: str
    :type api_secret: str
    """
    logger.info("Scrobbling!")
    parameters = {
            "method":"track.scrobble",
            "artist": track_info['artist'],
            "timestamp": timestamp,
            "track": track_info["title"],
            "api_key": api_key,
            "sk": session_key,
            }

    if "album" in track_info:
        parameters["album"]=track_info["album"]
    if "track" in track_info:
        parameters["trackNumber"]=track_info["track"]
    if "time" in track_info:
        parameters["duration"]=track_info["time"]

    parameters["api_sig"] = sign_signature(parameters,api_secret)

    try:
        xml = make_request(url,parameters,True)
    except Exception as e:
        logger.error("Something went wrong with the scrobble request.")
        logger.debug("Error: {}".format(e))
        xml = False

    if xml:
        logger.info("Scrobbles accepted: {}".format(xml.find("scrobbles").get("accepted")))
        logger.info("Scrobbling was a success!")

        logger.debug("XML Received for scrobble: {}".format(ET.tostring(xml, encoding="utf-8").decode("utf-8")))
        return True

    logger.warn("Failed to scrobble {song_title}, queuing for later.".format(song_title=track_info['title']))
    return False

def clear_pending_scrobbles_list(scrobbles,path_to_cache):
    logger.debug("Clearing scrobble queue")
    scrobbles.clear()
    if os.path.exists(path_to_cache):
        logger.debug("Removing scrobble cache: {}".format(path_to_cache))
        os.remove(path_to_cache)

def mpd_wait_for_play(client):
    """
    Block and wait for mpd to switch to the "play" action

    :param client: The MPD client object
    :type client: mpd.MPDClient

    :return: True when client is set to play - blocks otherwise
    :rtype: bool
    """

    status = client.status()
    state = status["state"]
    if state == "play":
        return True

    try:

        changes = client.idle("player")

        logger.info("Received event in subsytem: {}".format(changes)) # handle changes

        status = client.status()
        #logger.info(status)
        state = status["state"]
        logger.info("Received state: {}".format(state))

        if state == "play":
            song = client.currentsong()

            song_duration = float(song["duration"])
            title = song["title"]
            elapsed = float(status["elapsed"])

            logger.info("Playing {songname}, {elapsed}/{duration}s ({percent_elapsed}%)".format( songname = title, elapsed = format(elapsed,'.0f'), duration = format(song_duration,'.0f'),  percent_elapsed = format(( elapsed / song_duration * 100 ),'.1f') ))

            return True

        return mpd_wait_for_play(client)

    except Exception as e:
        logger.error("Something went wrong waiting on Idle: {}".format(e))
        logger.error("Exiting...")
        exit(1)

def mpd_watch_track(client, session, config):
    """
    The main loop - watches MPD and tracks the currently playing song. Sends Last.FM updates if need be.

    :param client: The MPD client object
    :param config: The global config file

    :type client: mpd.MPDClient
    :type config: dict
    """

    base_url = config["base_url"]
    api_key = config["api_key"]
    api_secret = config["api_secret"]

    use_real_time = config["real_time"]
    allow_scrobble_same_song_twice_in_a_row = config["allow_same_track_scrobble_in_a_row"]

    default_scrobble_threshold = config["scrobble_threshold"]
    scrobble_min_time = config["scrobble_min_time"]
    watch_threshold = config["watch_threshold"]
    update_interval = config["update_interval"]

    current_watched_track = ""
    reject_track=""

    cache_file_path = config["cache_file"]

    failed_scrobbles = read_failed_scrobbles_from_disk(cache_file_path)

    # For use with `use_real_time` parameter
    start_time = time.time()
    reported_start_time = 0

    last_rescrobble_attempt_time = time.time()

    while mpd_wait_for_play(client):

        scrobble_threshold = default_scrobble_threshold

        status = client.status()
        state = status["state"]

        # Check to see if we've got any tracks to scrobble (this is on a timer just in case)
        if time.time() - last_rescrobble_attempt_time > SCROBBLE_RETRY_INTERVAL:
            if len(failed_scrobbles)>0:
                scrobble_succeeded = scrobble_tracks(failed_scrobbles,base_url,api_key,api_secret,session)
                if scrobble_succeeded:
                    clear_pending_scrobbles_list(failed_scrobbles,cache_file_path)
            last_rescrobble_attempt_time = time.time()

        if state == "play":

            # The time since the song claims it started, that we've been able to measure in python
            real_time_elapsed = reported_start_time + (time.time()-start_time)
            #logger.info(real_time_elapsed)

            song = client.currentsong()
            #logger.debug("Song info: {}".format(song))

            song_duration = float(song["duration"])
            title = song["title"]

            elapsed = float(status["elapsed"])

            # The % between 0-100 that has completed so far
            percent_elapsed = elapsed / song_duration * 100

            if (current_watched_track != title and # Is this a new track to watch?
                title != reject_track and # And it's not a track to be rejected
                percent_elapsed < scrobble_threshold and # And it's below the scrobble threshold
                real_time_elapsed > watch_threshold and # And it's REALLY passed 5 seconds?
                elapsed > watch_threshold): # And it reports to be passed 5 seconds (sanity check)

                current_watched_track = title
                reject_track = ""

                start_time = time.time()
                reported_start_time = elapsed

                if use_real_time:
                    # So, if we're using real time, and our default_scrobble_threshold is less than 50, we need to do some math:
                    # Assuming we might have started late, how many real world seconds do I have to listen to to be able to say I've listened to N% (where N = default_scrobble_threshold) of music? Take that amount of seconds and turn it into its own threshold (added to the aforementioned late start time) and baby you've got a stew going
                    #scrobble_threshold = ( reported_start_time + song_duration * default_scrobble_threshold/100 ) / song_duration * 100
                    scrobble_threshold = (reported_start_time / song_duration * 100) + default_scrobble_threshold
                    logger.info("While the scrobbling threshold would normally be {}%, since we're starting at {}s (out of {}s, a.k.a. {}%), it's now {}%".format(default_scrobble_threshold,format(reported_start_time,'.1f'),format(song_duration,'.1f'), format(reported_start_time/song_duration*100,'.1f'), format(scrobble_threshold,'.1f')))
                else:
                    scrobble_threshold = default_scrobble_threshold

                logger.debug("Reported start time: {}, real world time: {}".format(reported_start_time,start_time))
                logger.info("Starting to watch track: {}, currently at: {}/{}s ({}%). Will scrobble in: {}s".format(title,format(elapsed, '.0f'),format(song_duration,'.0f'), format(percent_elapsed, '.1f'), format(( song_duration * scrobble_threshold / 100 ) - elapsed, '.0f'  ) ) )
                now_playing(song,base_url,api_key,api_secret,session)

            elif current_watched_track == title:

                #logger.debug("{}, at: {}%".format(title,format(percent_elapsed, '.2f')))

                # Are we above the scrobble threshold? Have we been listening the required amount of time?
                if percent_elapsed >= scrobble_threshold and elapsed > scrobble_min_time:
                    # If we're using real time, lets ensure we've been listening this long:
                    if not use_real_time or real_time_elapsed >= (scrobble_threshold/100) * song_duration:
                        current_watched_track = ""
                        if len(failed_scrobbles) < 1:
                            # If we don't have any pending scrobbles, try to scrobble this
                            scrobble_succeeded = scrobble_track(song,start_time,base_url,api_key,api_secret,session)
                            # If we've failed, add it to the list for future scrobbles (and write it to the disk)
                            if not scrobble_succeeded:
                                record_failed_scrobble(song,start_time,failed_scrobbles,cache_file_path)
                        else:
                            # If we have failed and queued up scrobbles, add this one to the list and try to do them all in one go
                            record_failed_scrobble(song,start_time,failed_scrobbles,cache_file_path)
                            scrobble_succeeded =  scrobble_tracks(failed_scrobbles, base_url, api_key, api_secret, session)
                            # If we were successful clean up the scrobble file
                            if scrobble_succeeded:
                                clear_pending_scrobbles_list(failed_scrobbles,cache_file_path)

                        if not allow_scrobble_same_song_twice_in_a_row:
                            reject_track = title
                    else:
                        logger.warn("Can't scrobble yet, time elapsed ({}s) < adjustted duration ({}s)".format(real_time_elapsed, 0.5*song_duration))

            time.sleep(update_interval)


def find_session(session_file_path,base_url,api_key,api_secret):
    # Try to read a saved session...
    try:
        with open(session_file_path) as session_f_stream:
            lines=session_f_stream.readlines()

            user_name=lines[0].strip()
            session=lines[1].strip()

            logger.debug("User: {}, Session: {}".format(user_name, session))

    # If not, authenticate again (no harm no foul)
    except Exception as e:
        logger.error("Couldn't read session file: {}".format(e))
        logger.info("Attempting new authentication...")
        token = get_token(base_url,api_key,api_secret)
        logger.info("Token received, navigate to http://www.last.fm/api/auth/?api_key={}&token={} to authenticate...".format(api_key,token))
        session_info = authenticate(token,base_url,api_key,api_secret)

        print(session_info)
        user_name, session = session_info

        save_credentials(session_file_path,user_name,session)

    return (user_name,session)

def fork(config):
    try:
        pid = os.fork()
        if pid > 0:

            os.setsid()
            os.umask(0)
            os.chdir("/")

            try:
                pid_2 = os.fork()
                if pid_2 > 0:
                    if "pid_file" in config:
                        logger.debug("Forked yams, PID: {}".format(str(pid)))
                        with open(config["pid_file"],"w+") as pid_file:
                            pid_file.writelines(str(pid)+"\n")
                            logger.info("Wrote PID to file: {}".format(config["pid_file"]))
                            exit(0)
            except Exception as e_2:
                logger.error("Could not perform second fork to pid! Error: {}".format(e_2))
            exit(0)

    except Exception as e:
        logger.error("Could not fork to pid! Error: {}".format(e))


def cli_run():

    session = ""
    config = configure()
    logger.info("Starting up YAMS v{}".format(yams.VERSION))

    session_file = config["session_file"]
    base_url = config["base_url"]
    api_key = config["api_key"]
    api_secret = config["api_secret"]

    mpd_host = config["mpd_host"]
    mpd_port = config["mpd_port"]


    user_name, session = find_session(session_file,base_url,api_key,api_secret)

    try:
        client = MPDClient()
        client.connect(mpd_host, mpd_port)
        logger.info("Connected to mpd, version: {}".format(client.mpd_version))
    except Exception as e:
        logger.error("Could not connect to MPD! Check that your config is correct and that MPD is running. Error: {}".format(e))
        exit(1)

    # If we're allowed to daemonize, do so
    if "no_daemon" in config and not config["no_daemon"]:
        fork(config)
        remove_log_stream_of_type(logging.StreamHandler)

    # This is just for the log
    logger.info("Connected to mpd, version: {}".format(client.mpd_version))

    try:

        mpd_watch_track(client,session,config)
    except KeyboardInterrupt:
        print("")
        logger.info("Keyboard Interrupt detected - Exiting!")

    client.disconnect()


if __name__ == "__main__":
    cli_run()
