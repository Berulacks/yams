YAMS
====

*Yet Another Mpd Scrobbler*

YAMS is exactly what its name says it is.

YAMS will use the usual `$MPD_HOST` and `$MPD_PORT` environment variables to connect to `mpd`, if they exist
Beyond that it looks for a configuration file named `yams.yml` placed in `$HOME/.config/yams` or `$HOME/.yams`
You can auto-generate this file by running the script with the `-g` flag.

Once run, it'll guide you through the authentication process and save its credentials to the same folder as its config.

You're need the `mpd` library installed through pip - do so with `pip install mpd` before running.

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
                        time reported by mpd). Default: True (default: False)
  -d, --allow-duplicate-scrobbles
                        Allow the program to scrobble the same track multiple
                        times in a row? Default: False (default: False)
  -c ~/my_config, --config ~/my_config
                        Your config to read (default: None)
  -g, --generate-config
                        Automatically save/update a configuration file. Good
                        for bootsrapping. (default: False)
                        ```
