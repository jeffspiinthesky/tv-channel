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
