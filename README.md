YAMS
====

*Yet Another Mpd Scrobbler (For Last.FM)*

YAMS is exactly what its name says it is.


#### Requirements
`PyYAML` and `python-mpd2` are required.

#### Installation
Clone this repo and run `pip3 install -e <path_to_repo>` (omit the `-e` flag if you don't want changes in the repo to be reflected in your local installation)

#### Running

The script includes a `yams` script that should be installed with pip. If not found, `python3 -m yams` will do the trick.

`yams` runs as a daemon by default (`yams -N` will run it in the foreground).

`yams -k` will kill the current running instance. 

`yams -a` will attach to the current running instance's log file, allowing you to watch the daemon's output.

`yams -h` will print all the options (also available below)

#### Setup

YAMS will use the usual `$MPD_HOST` and `$MPD_PORT` environment variables to connect to `mpd`, if they exist.

If it can't find one by default, YAMS will create a config file, log, and session file in `$HOME/.config/yams`, however it will also accept config files in `$HOME/.yams` or `./.yams` (theoretically configs in `$HOME` or the current working directory will be read in, as well - but don't do that). 

YAMS will only create its own directory/configuration file if none of the previous directories exist.

Once run, it'll guide you through the Last.FM authentication process and save its credentials to the same folder as its config.

#### Help

Here's the output for `--help`:

```
usage: YAMS [-h] [-m 127.0.0.1] [-p 6600] [-s ./.lastfm_session]
            [--api-key API_KEY] [--api-secret API_SECRET] [-t 50] [-r] [-d]
            [-c ~/my_config] [-g] [-l /path/to/log] [-N] [-D] [-k]
            [--disable-log] [-a]

Yet Another Mpd Scrobbler, v0.2. Configuration directories are either
~/.config/yams, ~/.yams, or your current working directory. Create one of
these paths if need be.

optional arguments:
  -h, --help            show this help message and exit
  -m 127.0.0.1, --mpd-host 127.0.0.1
                        Your MPD instance's host
  -p 6600, --mpd-port 6600
                        Your MPD instance's port
  -s ./.lastfm_session, --session-file-path ./.lastfm_session
                        Where to read in/save your session file to. Defaults
                        to inside your config directory.
  --api-key API_KEY     Your last.fm api key
  --api-secret API_SECRET
                        Your last.fm api secret
  -t 50, --scrobble-threshold 50
                        The minimum point at which to scrobble, defaults to 50
                        percent
  -r, --real-time       Use real times when calculating scrobble times? (e.g.
                        how long you've been running the app, not the track
                        time reported by mpd). Default: True
  -d, --allow-duplicate-scrobbles
                        Allow the program to scrobble the same track multiple
                        times in a row? Default: False
  -c ~/my_config, --config ~/my_config
                        Your config to read
  -g, --generate-config
                        Save the entirety of the running configuration to the
                        config file, including command line arguments. Use
                        this if you always run yams a certain fashion and want
                        that to be the default. Default: False
  -l /path/to/log, --log-file /path/to/log
                        Full path to a log file. If not set, a log file called
                        "yams.log" will be placed in the current config
                        directory.
  -N, --no-daemon       If set to true, program will not be run as a daemon
                        (e.g. it will run in the foreground) Default: False
  -D, --debug           Run in Debug mode. Default: False
  -k, --kill-daemon     Will kill the daemon if running - will fail otherwise.
                        Default: False
  --disable-log         Disable the log? Default: False
  -a, --attach          Runs "tail -F" on a running instance of yams' log
                        file. "Attaches" to it, for all intents and purposes.
                        NB: You will still need to kill it by hand. Default:
                        False
```
