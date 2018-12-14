#!/usr/bin/env python3

import requests, hashlib
import xml.etree.ElementTree as ET
from mpd import MPDClient
import select
from pathlib import Path
import time
import asyncio

SCROBBLE_THRESHOLD=50
SCROBBLE_MIN_TIME=10
WATCH_THRESHOLD=5

API_KEY="559cb22723e5ada5c41952cb087ad4b8"
API_SECRET="295e37f10a2521c9ecebfab886d3c9ad"

TEST_ARTIST="betamaxx"
TEST_TRACK="Contra"

BASE_URL="http://ws.audioscrobbler.com/2.0/"

SESSION_FILE="./.lastfm_session"

def sign_signature(parameters,secret=""):
    """
    Create a signature for a signed request
    :param secret: The API secret for your application
    :param parameters: The parameters being sent in the Last.FM request
    :type parameters: dict
    :type secret: str"""
    keys=parameters.keys()
    keys=sorted(keys)

    to_hash = ""

    hasher = hashlib.md5()
    for key in keys:
        hasher.update(str(key).encode("utf-8"))
        hasher.update(str(parameters[key]).encode("utf-8"))
        #to_hash += str(key)+str(parameters[key])
        #print("Hashing: {}".format(str(key)+str(parameters[key])))

    if len(secret) > 0:
        hasher.update(secret.encode("utf-8"))

    hashed_form = hasher.hexdigest()
    #print("Signature for call: {}".format(hashed_form))

    return hashed_form

def make_request(url,parameters):
    response = requests.get(url,parameters)
    if response.ok:
        try:
            xml = ET.fromstring(response.text)
            return xml
        except Exception as e:
            print("Something went wrong parsing the XML. Error: {}. Failing...".format(e))
            return None
    print("Got a fucked up response! Status: {}, Reason: {}".format(response.status_code, response.reason))
    print("Response: {}".format(response.text))
    return None

def get_token(url,api_key,api_secret):
    parameters = {
            "api_key":api_key,
            "method":"auth.gettoken",
            }
    parameters["api_sig"] = sign_signature(parameters,api_secret)

    xml = make_request(url, parameters)

    token = xml.find("token").text
    #print("Token: {}".format(token))

    return token

def get_session(url,token,api_key,api_secret):
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
    #print("Key: {},{}".format(username,session_key))

    return (username,session_key)

def authenticate(token,base_url,api_key,api_secret):

    while session is "":
        input("Press Enter after you've granted scrobble.py permission to access your account...")
        try:
            print("Grabbing session...")
            session_info = get_session(base_url,token,api_key,api_secret)
            print("User: {}".format(session_info[0]))
            print("Session: {}".format(session_info[1]))

            return session_info
        except Exception as e:
            print("Couldn't grab session, reason: {}".format(e))
            pass
    print("Something off went wrong...")
    exit(0)

def save_credentials(session_filepath, user_name, session_key):
    with open(session_filepath,"w+") as session_file:
        session_file.write(str(user_name)+"\n")
        session_file.write(str(session_key)+"\n")

def scrobble_track(track_info):
    print("Scrobbling!")
    pass

def mpd_wait_for_play(client):

    status = client.status()
    state = status["state"]
    if state == "play":
        return True

    try:

        changes = client.idle("player")

        print("Received event in subsytem: {}".format(changes)) # handle changes

        status = client.status()
        #print(status)
        state = status["state"]
        print("Received state: {}".format(state))

        if state == "play":
            return True
        return mpd_wait_for_play(client)

    except Exception as e:
        print("Something went wrong waiting on Idle: {}".format(e))
        print("Exiting...")
        exit(1)

def mpd_watch_track(client, allow_scrobble_same_song_twice_in_a_row=False, use_real_time=True):

    current_watched_track = ""
    reject_track=""

    # For use with `use_real_time` parameter
    start_time = time.time()
    reported_start_time = 0

    while mpd_wait_for_play(client):

        scrobble_threshold = SCROBBLE_THRESHOLD

        status = client.status()
        state = status["state"]

        if state == "play":

            # The time since the song claims it started, that we've been able to measure in python
            real_time_elapsed = reported_start_time + (time.time()-start_time)
            #print(real_time_elapsed)

            song = client.currentsong()
            #print("Song info: {}".format(song))

            song_duration = float(song["duration"])
            title = song["title"]

            elapsed = float(status["elapsed"])

            # The % between 0-100 that has completed so far
            percent_elapsed = elapsed / song_duration * 100

            if (current_watched_track != title and # Is this a new track to watch?
                title != reject_track and # And it's not a track to be rejected
                percent_elapsed < scrobble_threshold and # And it's below the scrobble threshold
                real_time_elapsed > WATCH_THRESHOLD and # And it's REALLY passed 5 seconds?
                elapsed > WATCH_THRESHOLD): # And it reports to be passed 5 seconds (sanity check)

                print("Starting to watch track: {}".format(title))
                current_watched_track = title
                reject_track = ""

                start_time = time.time()
                reported_start_time = elapsed

                if use_real_time and SCROBBLE_THRESHOLD < 50 and reported_start_time < song_duration * SCROBBLE_THRESHOLD:
                    # So, if we're using real time, and our SCROBBLE_THRESHOLD is less than 50, we need to do some math:
                    # Assuming we might have started late, how many real world seconds do I have to listen to to be able to say I've listened to N% (where N = SCROBBLE_THRESHOLD) of music? Take that amount of seconds and turn it into its own threshold (added to the aforementioned late start time) and baby you've got a stew going
                    scrobble_threshold = ( reported_start_time + song_duration * SCROBBLE_THRESHOLD/100 ) / song_duration * 100
                    print("While the scrobbling threshold would normally be {}%, since we're starting at {}, it's now {}%".format(SCROBBLE_THRESHOLD,reported_start_time,scrobble_threshold))
                else:
                    scrobble_threshold = SCROBBLE_THRESHOLD

                print("Reported start time: {}, real world time: {}".format(reported_start_time,start_time))

            elif current_watched_track == title:

                print("{}, at: {}%".format(title,percent_elapsed))

                # Are we above the scrobble threshold? Have we been listening the required amount of time?
                if percent_elapsed >= scrobble_threshold and elapsed > SCROBBLE_MIN_TIME:
                    # If we're using real time, lets ensure we've been listening this long:
                    if not use_real_time or real_time_elapsed >= (scrobble_threshold/100) * song_duration:
                        current_watched_track = ""
                        scrobble_track(song)
                        if not allow_scrobble_same_song_twice_in_a_row:
                            reject_track = title
                    else:
                        print("Rejected, time elapsed {} < duration {}".format(real_time_elapsed, 0.5*song_duration))

            time.sleep(0.5)



# SCRIPT STUFF
session = ""

if __name__ == "__main__":


    # Try to read a saved session...
    try:
        with open(SESSION_FILE) as session_file:
            lines=session_file.readlines()

            user_name=lines[0].strip()
            session=lines[1].strip()

            print("User: {}, Session: {}".format(user_name, session))

    # If not, authenticate again (no harm no foul)
    except Exception as e:
        print("Couldn't read token file: {}".format(e))
        print("Attempting new authentication...")
        token = get_token(BASE_URL,API_KEY,API_SECRET)
        print("Token received, navigate to http://www.last.fm/api/auth/?api_key={}&token={} to authenticate...".format(API_KEY,token))
        session_info = authenticate(token,BASE_URL,API_KEY,API_SECRET)

        user_name, session = session_info

        save_credentials(SESSION_FILE,user_name,session)

    client = MPDClient()
    client.connect("{}/.config/mpd/socket".format(str(Path.home())), 6600)
    print("Connected to mpd, version: {}".format(client.mpd_version))

    mpd_watch_track(client)


