# Raspberry PI TV Channel

## Purpose
These helper scripts, created using Claude Code, are used to help split a single video collection of adverts into discreet files per ad.

The detect_ad_breaks.sh file is run as:
```
./detect_ad_breaks.sh <ad break collection file> <cuts file>
```

When this is run, it scans the collection for black frames or silence. If it finds either, then it provides an entry in the cuts file specifying the timestamp for the cut point.

If there is a suspiciously short (<8secs) or long (>60s) cut, then this will be marked in the cuts file.

Once the cuts file is produced, it should be manually viewed and anywhere there's a suspicious cut point, the video should be reviewed using a player like VLC to determine if the cut point identified is correct or not.

Once you've corrected the cut points, remove all the comments from the file.

You can then actually perform the split operation with the command:
```
./split_ads.sh <ad break collection file> <cuts file> <target directory> <widthxheight>
```

This will then use FFMPEG to split the original collection into individual ad files and they'll be resized to the target width and height. If the original file was SD, it will be pillarboxed (have black bars placed left and right) so that the original aspect ratio is preserved for the visible image.

## Building a Playlist
If you wish to construct a JSON playlist for FFPlayout, this script can be useful. 

You supply an ordered list of programme files plus markers for where the
ident and ad breaks go; this fills in the ident automatically and picks a
random (but then fixed/inspectable) clip from the Adverts folder for each
ad-break marker.

Input is a plain text "block file", one entry per line:
```
    PROGRAM /mnt/share/Movies/A-D/Anora (2024).mp4
    IDENT
    AD
    PROGRAM /mnt/share/Video/Breaking Bad/Season 1/Breaking.Bad.S01E01.mkv
    AD
    ...
```

Output is ffplayout's playlist JSON:
    {"channel": "...", "date": "YYYY-MM-DD", "program": [{"source": "..."}, ...]}

Usage:
```
    build_playlist.py blocks.txt --date 2026-08-21 --channel "Main Channel" \\
        --out playlist.json
    build_playlist.py blocks.txt --date 2026-08-21 --channel "Main Channel" \\
        --push --channel-id 1 --base-url http://localhost:8787 --token "$FFPLAYOUT_TOKEN"
```

--push requires a valid bearer token for that channel's admin/user account.
Getting that token isn't scripted here (log in via the ffplayout web UI and
check your browser's devtools network tab / settings page for it) — this
tool only builds and optionally posts the JSON, it doesn't manage auth.

## FFPlayout fork Deployment Script

Since I now have my own fork of FFPlayout featuring a fix for the bitrate issue when using the hardware acceleration on a Raspberry PI 4, you need to replace the version installed via the .deb package with the one built from source. 

I've provided a script for doing that. It builds the forked FFPlayout, removes the .deb install, installs the freshly built version, re-registers the service and restarts it. 

You can run it simply with:
```
./replace-ffplayout-deb-with-fork.sh
```
