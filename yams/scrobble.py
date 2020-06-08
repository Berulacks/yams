#!/usr/bin/env python3

import requests, hashlib
import xml.etree.ElementTree as ET
from mpd import MPDClient
from mpd.base import ConnectionError
import select
from pathlib import Path
import time
import logging
import yaml
import os
from sys import exit

from yams.configure import configure, remove_log_stream_of_type
import yams

MAX_TRACKS_PER_SCROBBLE = 50
SCROBBLE_RETRY_INTERVAL = 10
SCROBBLE_DISK_SAVE_INTERVAL = 1200

logger = logging.getLogger("yams")

SCROBBLES = str(Path(Path.home(), ".config/yams/scrobbles.cache"))


def save_failed_scrobbles_to_disk(path, scrobbles):
    logger.info("Writing scrobbles to disk...")
    if os.path.exists(path):
        os.remove(path)

    with open(path, "w+") as file_stream:
        yaml.dump(
            {"scrobbles": scrobbles},
            file_stream,
            default_flow_style=False,
            Dumper=yaml.Dumper,
        )
    logger.info("Failed scrobbles written to: {}".format(path))


def read_failed_scrobbles_from_disk(path):

    if os.path.exists(path):
        try:
            with open(path) as scrobbles_file_stream:
                scrobbles_file = yaml.load(
                    scrobbles_file_stream, Loader=yaml.FullLoader
                )

                logger.info("Scrobbles found, reading from file at {}...".format(path))
                if "scrobbles" in scrobbles_file:
                    for scrobble in scrobbles_file["scrobbles"]:
                        for key in scrobble.keys():
                            logger.debug("[{}]: {}".format(key, scrobble[key]))
                    return scrobbles_file["scrobbles"]
        except Exception as e:
            logger.warn("Couldn't read failed scrobbles file!: {}".format(e))
    return []


def sign_signature(parameters, secret=""):
    """
    Create a signature for a signed request
    :param parameters: The parameters being sent in the Last.FM request
    :param secret: The API secret for your application
    :type parameters: dict
    :type secret: str

    :return: The actual signature itself
    :rtype: str
    """
    keys = parameters.keys()
    keys = sorted(keys)

    to_hash = ""

    hasher = hashlib.md5()
    for key in keys:
        hasher.update(str(key).encode("utf-8"))
        hasher.update(str(parameters[key]).encode("utf-8"))
        # to_hash += str(key)+str(parameters[key])
        logger.debug("Hashing: {}".format(str(key) + str(parameters[key])))

    if len(secret) > 0:
        hasher.update(secret.encode("utf-8"))

    hashed_form = hasher.hexdigest()
    logger.debug("Signature for call: {}".format(hashed_form))

    return hashed_form


def make_request(url, parameters, POST=False):
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

    logger.debug("Making request to '{}':\n'{}'".format(url, parameters))

    if not POST:
        response = requests.get(url, parameters)
    else:
        response = requests.post(url, data=parameters)

    logger.debug("Response: {}".format(response.text))

    if response.ok:
        try:
            xml = ET.fromstring(response.text)
            return xml
        except Exception as e:
            logger.error(
                "Something went wrong parsing the XML. Error: {}. Failing...".format(e)
            )
            return None
    logger.info(
        "Got a fucked up response! Status: {}, Reason: {}".format(
            response.status_code, response.reason
        )
    )
    logger.info("Response: {}".format(response.text))
    return None


def get_token(url, api_key, api_secret):
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
        "api_key": api_key,
        "method": "auth.gettoken",
    }
    parameters["api_sig"] = sign_signature(parameters, api_secret)

    xml = make_request(url, parameters)

    token = xml.find("token").text
    logger.debug("Token: {}".format(token))

    return token


def get_session(url, token, api_key, api_secret):
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
    parameters = {"token": token, "api_key": api_key, "method": "auth.getsession"}
    parameters["api_sig"] = sign_signature(parameters, api_secret)

    xml = make_request(url, parameters)

    session = xml.find("session")
    username = session.find("name").text
    session_key = session.find("key").text
    logger.debug("Key: {},{}".format(username, session_key))

    return (username, session_key)


def authenticate(token, base_url, api_key, api_secret):
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

    input(
        "Press Enter after you've granted scrobble.py permission to access your account..."
    )
    try:
        logger.info("Grabbing session...")
        session_info = get_session(base_url, token, api_key, api_secret)
        logger.info("User: {}".format(session_info[0]))
        logger.info("Session: {}".format(session_info[1]))

        return session_info
    except Exception as e:
        logger.error("Couldn't grab session, reason: {}".format(e))

    # Keep looping forever, the program won't be able to do anything without a session, anyway.
    return authenticate(token, base_url, api_key, api_secret)


def save_credentials(session_filepath, user_name, session_key):
    """Save authentication credentials to disk.

    :param session_filepath: The path of the file to save to
    :param user_name: Your username
    :param session_key: Your session_key

    :type session_filepath: str
    :type user_name: str
    :type session_key: str
    """

    with open(session_filepath, "w+") as session_file:
        session_file.write(str(user_name) + "\n")
        session_file.write(str(session_key) + "\n")


def extract_single(container, key):
    """
    Sometimes mpd will report an array inside its track info (e.g. 3 artists instead of 1)
In cases like these it makes sense to always extract the first, this function does that.
    Also prevents crashing if something's gone wrong.

    :param container: The dictionary being searched
    :param key: The key to use in the dict

    :type container: dict
    :type key: object

    :rtype: object
    """

    if key in container:
        if isinstance(container[key], list):
            first_match = container[key][0]
            logger.warn(
                "Found multiple instances of key '{}', returning first match: {}".format(
                    key, first_match
                )
            )
            logger.debug(
                "Container of the key ('{}') in question: {}".format(key, container)
            )
            return first_match
        return container[key]
    return ""


def now_playing(track_info, url, api_key, api_secret, session_key):
    """
    Send your currently playing track's info to Last.FM

    :param track_info: The track's info from mpd
    :param url: The base Last.FM API url
    :param api_key: Your API key
    :param api_secret: Your API secret (given to you when you got your API key)
    :param session_key: Your Last.FM session key

    :type track_info: dict
    :type url: str
    :type api_key: str
    :type api_secret: str
    :type session_key: str
    """

    parameters = {
        "method": "track.updateNowPlaying",
        "artist": extract_single(track_info, "artist"),
        "track": extract_single(track_info, "title"),
        "context": "mpd",
        "api_key": api_key,
        "sk": session_key,
    }

    if "album" in track_info:
        parameters["album"] = extract_single(track_info, "album")
    if "track" in track_info:
        parameters["trackNumber"] = extract_single(track_info, "track")
    if "duration" in track_info:
        parameters["duration"] = extract_single(track_info, "duration")
    # We do this for older clients, such as mopidy, that use the "time" variable to send duration data
    # Which is deprecated according to the mpd protocol. Oh well. Bad mopidy, bad.
    elif "time" in track_info:
        parameters["duration"] = extract_single(track_info, "time")

    parameters["api_sig"] = sign_signature(parameters, api_secret)

    # logger.info(parameters)

    try:
        xml = make_request(url, parameters, True)
        # logger.info(xml.tag)
        # for child in xml[0]:
        #    logger.info(child.text)
        logger.info("Now playing was a success!")
    except Exception as e:
        logger.warn("Could not send now playing Last.FM!")
        logger.debug("Error: {}".format(e))


def scrobble_tracks(tracks, url, api_key, api_secret, session_key):
    """
    Attempts to scrobble multiple tracks at once to Last.FM

    :param tracks: The list of failed scrobbles, in the form of the scrobbles cache
    :param url: The base Last.FM API url
    :param api_key: Your API key
    :param api_secret: Your API secret (given to you when you got your API key)
    :param session_key: Your Last.FM session key

    :type tracks: list
    :type url: str
    :type api_key: str
    :type api_secret: str
    :type session_key: str

    :return: Returns a tuple of (accepted count of scrobbles, submitted count of scrobbles). This will not always be the same as the amount of scrobbles you sent in, so you should truncate your cache accordingly.
    :rtype: (int,int)
    """

    # Sanity check
    if len(tracks) < 1:
        logger.debug("Failed sanity check for scrobble tracks")
        return

    logger.info("Attempting mass scroble for {} tracks!".format(len(tracks)))
    parameters = {
        "method": "track.scrobble",
        "api_key": api_key,
        "sk": session_key,
    }

    max_scrobbles = (
        MAX_TRACKS_PER_SCROBBLE
        if len(tracks) > MAX_TRACKS_PER_SCROBBLE
        else len(tracks)
    )

    for i in range(0, max_scrobbles):
        logger.debug("Adding {} to mass scrobble request.".format(tracks[i]))
        # We probably don't need to use the extract_single's, here, but better safe than sorry!
        parameters["track[{}]".format(i)] = extract_single(tracks[i], "title")
        parameters["artist[{}]".format(i)] = extract_single(tracks[i], "artist")
        parameters["timestamp[{}]".format(i)] = extract_single(tracks[i], "timestamp")

        if "album" in tracks[i]:
            parameters["album[{}]".format(i)] = extract_single(tracks[i], "album")
        if "trackNumber" in tracks[i]:
            parameters["trackNumber[{}]".format(i)] = extract_single(
                tracks[i], "trackNumber"
            )

        if "duration" in tracks[i]:
            parameters["duration[{}]".format(i)] = extract_single(tracks[i], "duration")
        # We do this for older clients, such as mopidy, that use the "time" variable to send duration data
        # Which is deprecated according to the mpd protocol. Oh well. Bad mopidy, bad.
        elif "time" in track_info:
            parameters["duration[{}]".format(i)] = extract_single(tracks[i], "time")

    parameters["api_sig"] = sign_signature(parameters, api_secret)

    try:
        xml = make_request(url, parameters, True)
        if xml:
            logger.debug("Received response: [{}] - {}".format(xml.tag, xml.attrib))
            logger.debug(
                "XML Received for mass scrobble: {}".format(
                    ET.tostring(xml, encoding="utf-8").decode("utf-8")
                )
            )

            accepted = int(xml.find("scrobbles").get("accepted"))
            if accepted > 0:
                logger.info("Scrobbles accepted: {}".format(accepted))
                logger.info("Mass scrobbling was a success!")

                return accepted, max_scrobbles
            else:
                logger.warn(
                    "Failed to scrobble {num_tracks} tracks, queuing for later.".format(
                        num_tracks=len(tracks)
                    )
                )
        else:
            logger.warn(
                "Failed to scrobble {num_tracks} tracks, queuing for later.".format(
                    num_tracks=len(tracks)
                )
            )
    except Exception as e:
        logger.warn(
            "Failed to scrobble {num_tracks} tracks, queuing for later.".format(
                num_tracks=len(tracks)
            )
        )
        logger.debug("Error: {}".format(e))

    return 0, 0


def record_failed_scrobble(track_info, timestamp, failed_scrobbles, cache_file_path):
    """
    Adds a failed scrobble to the cached list of failed scrobbles, and writes them all to disk.

    :param track_info: A dictionary of track information from mpd
    :param timestamp: A UNIX timestamp of when this track was listened to
    :param failed_scrobbles: The list of failed scrobbles to append this to
    :param cache_file_path: The file path of the scrobbles cache (to write to disk)

    :type track_info: dict
    :type timestamp: str
    :type failed_scrobbles: list
    :type cache_file_path: str
    """

    failed_scrobble = {
        "artist": extract_single(track_info, "artist"),
        "title": extract_single(track_info, "title"),
        "timestamp": timestamp,
    }

    if "album" in track_info:
        failed_scrobble["album"] = extract_single(track_info, "album")
    if "track" in track_info:
        failed_scrobble["trackNumber"] = extract_single(track_info, "track")
    if "duration" in track_info:
        failed_scrobble["duration"] = extract_single(track_info, "duration")
    # We do this for older clients, such as mopidy, that use the "time" variable to send duration data
    # Which is deprecated according to the mpd protocol. Oh well. Bad mopidy, bad.
    elif "time" in track_info:
        failed_scrobble["duration"] = extract_single(track_info, "time")

    if failed_scrobble not in failed_scrobbles:
        failed_scrobbles.append(failed_scrobble)
        save_failed_scrobbles_to_disk(cache_file_path, failed_scrobbles)


def scrobble_track(track_info, timestamp, url, api_key, api_secret, session_key):
    """
    Scrobble your track with Last.FM

    :param track_info: The track's info from mpd
    :param timestamp: The starting time of the track, as a UTC Unix Timestamp (seconds since the Epoch)
    :param url: The base Last.FM API url
    :param api_key: Your API key
    :param api_secret: Your API secret (given to you when you got your API key)
    :param session_key: Your Last.FM session key

    :type track_info: dict
    :param timestamp: int
    :type url: str
    :type api_key: str
    :type api_secret: str
    :type session_key: str
    """
    logger.info("Scrobbling!")
    parameters = {
        "method": "track.scrobble",
        "artist": extract_single(track_info, "artist"),
        "timestamp": timestamp,
        "track": extract_single(track_info, "title"),
        "api_key": api_key,
        "sk": session_key,
    }

    if "album" in track_info:
        parameters["album"] = extract_single(track_info, "album")
    if "track" in track_info:
        parameters["trackNumber"] = extract_single(track_info, "track")
    if "duration" in track_info:
        parameters["duration"] = extract_single(track_info, "duration")
    # We do this for older clients, such as mopidy, that use the "time" variable to send duration data
    # Which is deprecated according to the mpd protocol. Oh well. Bad mopidy, bad.
    elif "time" in track_info:
        parameters["duration"] = extract_single(track_info, "time")

    parameters["api_sig"] = sign_signature(parameters, api_secret)

    try:
        xml = make_request(url, parameters, True)
    except Exception as e:
        logger.error("Something went wrong with the scrobble request.")
        logger.debug("Error: {}".format(e))
        xml = False

    if xml:
        logger.info(
            "Scrobbles accepted: {}".format(xml.find("scrobbles").get("accepted"))
        )
        logger.info("Scrobbling was a success!")

        logger.debug(
            "XML Received for scrobble: {}".format(
                ET.tostring(xml, encoding="utf-8").decode("utf-8")
            )
        )
        return True

    logger.warn(
        "Failed to scrobble {song_title}, queuing for later.".format(
            song_title=track_info["title"]
        )
    )
    return False


def truncate_pending_scrobbles_list(count, scrobbles, path_to_cache):
    """
    Removes 'count' number of scrobbles from the current cached list and then writes to disk if necessary.

    :param count: The number of scrobbles to remove
    :param scrobbles: The list of cached scrobbles to remove from
    :param path_to_cache: The path to the cached scrobbles file, if a write to disk is necessary

    :type count: int
    :type scrobbles: list
    :type path_to_cache: str

    :return: The truncated list of scrobbles, or an empty list (if the count to remove was larger than the length of the scrobbles list)
    :rtype: list
    """

    if count >= len(scrobbles):
        logger.debug(
            "Removing all ({}/{}) scrobbles from cache".format(count, len(scrobbles))
        )

        if os.path.exists(path_to_cache):
            logger.debug("Removing scrobble cache: {}".format(path_to_cache))
            os.remove(path_to_cache)

        return []
    else:
        scrobbles = scrobbles[count:]
        logger.debug(
            "Removed {} scrobbles from cache, {} left to submit.".format(
                count, len(scrobbles)
            )
        )
        save_failed_scrobbles_to_disk(path_to_cache, scrobbles)

        return scrobbles


def mpd_wait_for_play(client):
    """
    Block and wait for mpd to switch to the "play" action

    :param client: The MPD client object
    :type client: mpd.MPDClient

    :return: True when client is set to play - blocks otherwise
    :rtype: bool
    """

    # Track whether player blocks before entering play state
    blocked = False

    try:
        while True:
            status = client.status()
            # logger.info(status)
            state = status["state"]
            if blocked:
                logger.info("Received state: {}".format(state))

            # Block until a change if not in the play state
            if state != "play":
                blocked = True
                changes = client.idle("player")
                logger.info(
                    "Recieved event in subsystem: {}".format(changes)
                )  # handle changes
                continue

            # Here we check if duration is in the track_info and use it if we can
            # Storing duration info in "time" is deprecated, as per the mpd spec,
            # however some servers (namely mopidy) still do this. Bad mopidy, bad.
            # Use values from the status rather than the song, as duration is
            # missing when using mpd to play urls or local files
            song_duration = float(
                status["duration"]
                if "duration" in status
                else status["time"].split(":")[-1]
            )
            # Continue to block if listening to internet radio (ie. duration is 0)
            if song_duration == 0:
                logger.info("Can't scrobble track, it's duration is 0")
                blocked = True
                changes = client.idle("player")
                logger.info(
                    "Recieved event in subsystem: {}".format(changes)
                )  # handle changes
                continue
            # Don't log "Playing" message if mpd was already playing (ie. reduce verbosity)
            elif not blocked:
                return True

            song = client.currentsong()
            title = song["title"]
            elapsed = float(status["elapsed"])

            logger.info(
                "Playing {songname}, by {artist} (from {album})".format(
                    songname=title,
                    artist=extract_single(song, "artist"),
                    album=extract_single(song, "album"),
                )
            )
            logger.info(
                "{elapsed}/{duration}s ({percent_elapsed}%)".format(
                    elapsed=format(elapsed, ".0f"),
                    duration=format(song_duration, ".0f"),
                    percent_elapsed=format((elapsed / song_duration * 100), ".1f"),
                )
            )

            return True

    except Exception as e:
        logger.error("Something went wrong waiting on MPD's Idle event: {}".format(e))
        return False


def mpd_watch_track(client, session, config):
    """
    The main loop - watches MPD and tracks the currently playing song. Sends Last.FM updates if need be.

    :param client: The MPD client object
    :param session: The Session key for last.fm
    :param config: The global config file

    :type client: mpd.MPDClient
    :type session: str
    :type config: dict
    """

    base_url = config["base_url"]
    api_key = config["api_key"]
    api_secret = config["api_secret"]

    use_real_time = config["real_time"]
    allow_scrobble_same_song_twice_in_a_row = config[
        "allow_same_track_scrobble_in_a_row"
    ]

    default_scrobble_threshold = config["scrobble_threshold"]
    scrobble_min_time = config["scrobble_min_time"]
    watch_threshold = config["watch_threshold"]
    update_interval = config["update_interval"]

    current_watched_track = ""
    reject_track = ""

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
            if len(failed_scrobbles) > 0:
                accepted_count, submitted_count = scrobble_tracks(
                    failed_scrobbles, base_url, api_key, api_secret, session
                )
                if accepted_count > 0:
                    failed_scrobbles = truncate_pending_scrobbles_list(
                        submitted_count, failed_scrobbles, cache_file_path
                    )
            last_rescrobble_attempt_time = time.time()

        if state == "play":

            # The time since the song claims it started, that we've been able to measure in python
            real_time_elapsed = reported_start_time + (time.time() - start_time)
            # logger.info(real_time_elapsed)

            song = client.currentsong()
            # logger.debug("Song info: {}".format(song))

            # Here we check if duration is in the track_info and use it if we can
            # Storing duration info in "time" is deprecated, as per the mpd spec,
            # however some servers (namely mopidy) still do this. Bad mopidy, bad.
            # Use values from the status rather than the song, as duration is
            # missing when using mpd to play urls or local files
            song_duration = float(
                status["duration"]
                if "duration" in status
                else status["time"].split(":")[-1]
            )

            title = extract_single(song, "title")
            artist = extract_single(song, "artist")
            album = extract_single(song, "album")

            elapsed = float(status["elapsed"])

            # The % between 0-100 that has completed so far
            percent_elapsed = elapsed / song_duration * 100

            if (
                current_watched_track != title
                and title != ""  # Is this a new track to watch?
                and title != reject_track  # And this track actually has a title
                and percent_elapsed  # And it's not a track to be rejected
                < scrobble_threshold
                and real_time_elapsed  # And it's below the scrobble threshold
                > watch_threshold
                and elapsed > watch_threshold  # And it's REALLY passed 5 seconds?
            ):  # And it reports to be passed 5 seconds (sanity check)

                current_watched_track = title
                reject_track = ""

                start_time = time.time()
                reported_start_time = elapsed - watch_threshold

                if use_real_time:
                    # So, if we're using real time, and our default_scrobble_threshold is less than 50, we need to do some math:
                    # Assuming we might have started late, how many real world seconds do I have to listen to to be able to say I've listened to N% (where N = default_scrobble_threshold) of music? Take that amount of seconds and turn it into its own threshold (added to the aforementioned late start time) and baby you've got a stew going
                    scrobble_threshold = (
                        (
                            reported_start_time
                            + (song_duration - reported_start_time)
                            * (default_scrobble_threshold / 100)
                        )
                        / song_duration
                    ) * 100
                    logger.info(
                        "While the scrobbling threshold would normally be {}%, since we're starting at {}s (out of {}s, a.k.a. {}%), it's now {}%".format(
                            default_scrobble_threshold,
                            format(reported_start_time, ".1f"),
                            format(song_duration, ".1f"),
                            format(reported_start_time / song_duration * 100, ".1f"),
                            format(scrobble_threshold, ".1f"),
                        )
                    )
                    logger.debug(
                        "(start + ( total - start ) * threshold) / total =  ( {0} + ( {1} - {0} ) * {2} ) / {1}".format(
                            reported_start_time,
                            song_duration,
                            default_scrobble_threshold,
                        )
                    )
                else:
                    scrobble_threshold = default_scrobble_threshold

                logger.debug(
                    "Reported start time: {}, real world time: {}".format(
                        reported_start_time, start_time
                    )
                )
                logger.info(
                    "Starting to watch track: {} by {}, currently at: {}/{}s ({}%). Will scrobble in: {}s".format(
                        title,
                        artist,
                        format(elapsed, ".0f"),
                        format(song_duration, ".0f"),
                        format(percent_elapsed, ".1f"),
                        format(
                            (song_duration * scrobble_threshold / 100) - elapsed, ".0f"
                        ),
                    )
                )
                now_playing(song, base_url, api_key, api_secret, session)

            elif current_watched_track == title:

                # logger.debug("{}, at: {}%".format(title,format(percent_elapsed, '.2f')))

                # Are we above the scrobble threshold? Have we been listening the required amount of time?
                if (
                    percent_elapsed >= scrobble_threshold
                    and elapsed > scrobble_min_time
                ):
                    # If we're using real time, lets ensure we've been listening this long:
                    if (
                        not use_real_time
                        or real_time_elapsed
                        >= (scrobble_threshold / 100) * song_duration
                    ):
                        current_watched_track = ""
                        if len(failed_scrobbles) < 1:
                            # If we don't have any pending scrobbles, try to scrobble this
                            scrobble_succeeded = scrobble_track(
                                song, start_time, base_url, api_key, api_secret, session
                            )
                            # If we've failed, add it to the list for future scrobbles (and write it to the disk)
                            if not scrobble_succeeded:
                                record_failed_scrobble(
                                    song, start_time, failed_scrobbles, cache_file_path
                                )
                        else:
                            # If we have failed and queued up scrobbles, add this one to the list and try to do them all in one go
                            record_failed_scrobble(
                                song, start_time, failed_scrobbles, cache_file_path
                            )
                            accepted_count, submitted_count = scrobble_tracks(
                                failed_scrobbles, base_url, api_key, api_secret, session
                            )
                            if accepted_count > 0:
                                failed_scrobbles = truncate_pending_scrobbles_list(
                                    submitted_count, failed_scrobbles, cache_file_path
                                )

                        if not allow_scrobble_same_song_twice_in_a_row:
                            reject_track = title
                    else:
                        logger.warn(
                            "Can't scrobble yet, time elapsed ({}s) < adjustted duration ({}s)".format(
                                real_time_elapsed,
                                (scrobble_threshold / 100) * song_duration,
                            )
                        )

            time.sleep(update_interval)


def find_session(session_file_path, base_url, api_key, api_secret, interactive=True):
    """
    Try to read a saved last.fm session from disk, or create a new one.

    :param session_file_path: The path to the session file to be read or written to.
    :param base_url: The base_url of the scrobble 2.0 API
    :param api_key: This program's last.fm API key
    :param api_secret: This program's last.fm API secret
    :param interactive: Are we in an interactive shell where we can prompt the user for info?

    :type session_file_path: str
    :type base_url: str
    :type api_key: str
    :type api_secret: str
    :type interactive: bool
    """

    # Try to read a saved session...
    try:
        with open(session_file_path) as session_f_stream:
            lines = session_f_stream.readlines()

            user_name = lines[0].strip()
            session = lines[1].strip()

            logger.debug("User: {}, Session: {}".format(user_name, session))

    # If not, authenticate again (no harm no foul)
    except Exception as e:
        logger.error("Couldn't read session file: {}".format(e))

        if not interactive:
            logger.error(
                "Please run yams in an interactive shell to perform authentication. You only need to do this once."
            )
            exit(1)

        logger.info("Attempting new authentication...")
        token = get_token(base_url, api_key, api_secret)
        logger.info(
            "Token received, navigate to http://www.last.fm/api/auth/?api_key={}&token={} to authenticate...".format(
                api_key, token
            )
        )
        session_info = authenticate(token, base_url, api_key, api_secret)

        print(session_info)
        user_name, session = session_info

        save_credentials(session_file_path, user_name, session)

    return (user_name, session)


def save_pid(file_path, pid=None):
    """
    Save a given pid to disk

    :param file_path: The path to save the pid to
    :param pid: The (optional) pid to save. If no pid is provided we get the current running program's pid

    :type file_path: str
    :type pid: int
    """

    # If we're not being passed a pid to save, lets save the current process' pid
    if pid == None:
        pid = os.getpid()

    with open(file_path, "w+") as pid_file:
        pid_file.writelines(str(pid) + "\n")
        logger.info("Wrote PID to file: {}".format(file_path))


def fork(config):
    """
    Fork's the current running program into a new instance.

    :param config: The YAMS config file
    :type config: dict
    """

    try:
        pid = os.fork()
        if pid > 0:

            try:
                os.setsid()
            except:
                logger.warn("Could not call setsid()!")

            os.umask(0)
            os.chdir("/")

            try:
                pid_2 = os.fork()
                if pid_2 > 0:
                    if "pid_file" in config:
                        logger.debug("Forked yams, PID: {}".format(str(pid)))
                        save_pid(config["pid_file"], pid)
                        exit(0)
            except Exception as e_2:
                logger.exception(
                    "Could not perform second fork to pid! Error: {}".format(e_2)
                )
                exit(1)
            exit(0)

    except Exception as e:
        logger.exception("Could not fork to pid! Error: {}".format(e))
        exit(1)


def connect_to_mpd(host, port):
    """Connect to MPD, throws an exception if failed"""

    client = MPDClient()
    client.connect(host, port)
    logger.info("Connected to mpd, version: {}".format(client.mpd_version))
    return client


def cli_run():
    """ Command line entrypoint """

    session = ""
    config = configure()
    logger.info("Starting up YAMS v{}".format(yams.VERSION))

    session_file = config["session_file"]
    base_url = config["base_url"]
    api_key = config["api_key"]
    api_secret = config["api_secret"]

    mpd_host = config["mpd_host"]
    mpd_port = config["mpd_port"]

    interactive_shell_available = (
        not config["non_interactive"] if "non_interactive" in config else True
    )
    user_name, session = find_session(
        session_file, base_url, api_key, api_secret, interactive_shell_available
    )

    try:
        client = connect_to_mpd(mpd_host, mpd_port)
    except Exception as e:
        logger.error(
            "Could not connect to MPD! Check that your config is correct and that MPD is running. Error: {}".format(
                e
            )
        )
        exit(1)

    # If we're allowed to daemonize, do so
    if "no_daemon" in config:
        if not config["no_daemon"]:
            fork(config)
            remove_log_stream_of_type(logging.StreamHandler)
        # NOTE: Comment these 2 lines out if you don't want YAMS to save a pid file in no-daemon mode
        elif config["no_daemon"] and "pid_file" in config:
            save_pid(config["pid_file"])

    RECONNECT_TIMEOUT = 10

    while True:
        if client:
            try:
                mpd_watch_track(client, session, config)
            # User is in no-daemon mode and wants to exit
            except KeyboardInterrupt:
                print("")
                logger.info("Keyboard Interrupt detected - Exiting!")
                break
            # A connection error implies we lost connection with MPD - lets retry unless the user kills us
            except ConnectionError as e:
                logger.error("Received an MPD Connection error!: {}".format(e))
                logger.info(
                    "YAMS will keep trying to reconnect to MPD, every {} seconds.".format(
                        RECONNECT_TIMEOUT
                    )
                )
                client = None
            # If we receive an unknown exception lets exit, as this is undefined behaviour
            except Exception:
                logger.exception("Something went very wrong!")
                break
        else:
            time.sleep(RECONNECT_TIMEOUT)
            try:
                client = connect_to_mpd(mpd_host, mpd_port)
            except Exception as e:
                # Don't know if this is cached anywhere - could cause some large log files so I'm leaving it commented out until I know more.
                # logger.debug("Could not connect to MPD! Check that your config is correct and that MPD is running. Error: {}".format(e))
                pass

    try:
        client.close()
    except:
        logger.warn("Could not gracefully disconnect from Mpd...")

    logger.info("Shutting down...")
    exit(0)


if __name__ == "__main__":
    cli_run()
