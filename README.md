YAMS
====

*Yet Another Mpd Scrobbler*

YAMS is exactly what its name says it is.

#### Setup

YAMS will use the usual `$MPD_HOST` and `$MPD_PORT` environment variables to connect to `mpd`, if they exist.
Beyond that it looks for a configuration file named `yams.yml` placed in `$HOME/.config/yams` or `$HOME/.yams`
You can auto-generate this file by running the script with the `-g` flag.

You **need** to add an `API_KEY` and `API_SECRET` from Last.FM to the configuration file, or to the program's command line parameters, before running. Emphasis on *need*. Generate them [here](https://www.last.fm/api/account/create) if you haven't done so already.

Once run, it'll guide you through the authentication process and save its credentials to the same folder as its config.

#### Requirements

You'll need the `mpd` library installed through pip - do so with `pip install mpd` before running.
Also, Python3.5+. That's a must.
You might also need `yaml`, can't remember if that's a default library or not. Give `pip install yaml` a whirl, just to be safe.

#### Running

Execute the script with a simple `python3 scrobbler.py`. I recommend doing it behind a program like `screen` or at least piping the output somewhere else (e.g. `./scrobbler.py &`). Eventually I might add a logger + daemon mode to tidy up the project. But that day isn't today and I needed a _functional_ scrobbler, _now_, for `mpd` so here we are!

#### Help

Sorry for the not-so flushed out README, the program should be rather self explanatory.

Here's the output for `--help`:

```
usage: YAMS [-h] [-m 127.0.0.1] [-p 6600] [-s ./.lastfm_session]
            [--api-key wdoqwnd10j2903j013r] [--api-secret oegnapj390rj2q]
            [-t 50] [-r] [-d] [-c ~/my_config] [-g]

Yet Another Mpd Scrobbler

optional arguments:
  -h, --help            show this help message and exit
  -m 127.0.0.1, --mpd-host 127.0.0.1
                        Your MPD instance's host (default: None)
  -p 6600, --mpd-port 6600
                        Your MPD instance's port (default: None)
  -s ./.lastfm_session, --session-file-path ./.lastfm_session
                        Where to read in/save your session file to. Defaults
                        to inside your config directory. (default: None)
  --api-key wdoqwnd10j2903j013r
                        Your last.fm api key (default: None)
  --api-secret oegnapj390rj2q
                        Your last.fm api secret (default: None)
  -t 50, --scrobble-threshold 50
                        The minimum point at which to scrobble, defaults to 50
                        percent (default: None)
  -r, --real-time       Use real times when calculating scrobble times? (e.g.
                        how long you've been running the app, not the track
                        time reported by mpd). Default: True
  -d, --allow-duplicate-scrobbles
                        Allow the program to scrobble the same track multiple
                        times in a row? Default: False
  -c ~/my_config, --config ~/my_config
                        Your config to read (default: None)
  -g, --generate-config
                        Automatically save/update a configuration file. Good
                        for bootsrapping. (default: False)
                        ```
