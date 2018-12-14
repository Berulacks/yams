#!/usr/bin/env python3

import requests, hashlib
import xml.etree.ElementTree as ET
from mpd import MPDClient
import select
from pathlib import Path


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

# SCRIPT STUFF

API_KEY="559cb22723e5ada5c41952cb087ad4b8"
API_SECRET="295e37f10a2521c9ecebfab886d3c9ad"

TEST_ARTIST="betamaxx"
TEST_TRACK="Contra"

BASE_URL="http://ws.audioscrobbler.com/2.0/"

SESSION_FILE="./.lastfm_session"
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

        user_name = session_info[0]
        session = session_info[1]

        save_credentials(SESSION_FILE,user_name,session)

    client = MPDClient()
    client.connect("{}/.config/mpd/socket".format(str(Path.home())), 6600)
    print(client.mpd_version)


    client.send_idle()
    print("Sent idle, entering loop")
    while(1==1):
        # do this periodically, e.g. in event loop
        canRead = select.select([client], [], [], 60)[0]
        print("Selected.")
        if canRead:
            changes = client.fetch_idle()
            print("Received event in subsytem: {}".format(changes)) # handle changes
            print(client.status())
        client.send_idle() # continue idling

