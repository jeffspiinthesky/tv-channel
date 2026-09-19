# Raspberry PI TV Channel

A 24/7-style TV channel built on [ffplayout](https://github.com/ffplayout/ffplayout)
(this project uses [a fork](https://github.com/jeffspiinthesky/ffplayout) with a
couple of Raspberry Pi-specific fixes), with an optional real over-the-air DVB-T
transmit chain via a HackRF One. Built for the "Jeff's Pi in the Sky" YouTube
series; these scripts were created using Claude Code.

## Architecture

```
ffplayout (multicast MPEG-TS; DVB service name set in its own web UI)
  -> tv-channel-dvbt relay (null-padded, rate-paced, unicast loopback)
  -> GNU Radio DVB-T modulator (2K/QPSK/CR1-2/GI1-4)
  -> HackRF One
  -> antenna / attenuator
```

Two separate installable pieces, on purpose:

- **The ffplayout fork** (its own `.deb`) is the playout engine -- it builds
  the schedule, plays clips, and outputs a multicast MPEG-TS stream on the
  LAN. Useful entirely on its own if you only want to watch the channel over
  the network (VLC, etc.) with no radio hardware at all.
- **`tv-channel-dvbt`** (a separate `.deb`, this repo) is the RF delivery
  layer -- it only exists to take that same multicast stream and actually
  transmit it as DVB-T. It has its own dependencies (GNU Radio, HackRF
  tooling) that a LAN-only viewer doesn't need.

## Hardware requirements

Validated on a Raspberry Pi 4B running a Debian 13 (trixie)-based Raspberry
Pi OS, with a HackRF One, against these package versions: `hackrf` 2024.02.1,
`gnuradio` 3.10.12.0, `gr-osmosdr` 0.2.6. You also need an antenna, attenuator,
or dummy load appropriate for how you intend to use this legally -- see below.

## Legal / RF safety

**Transmitting on broadcast television frequencies without authorization is
illegal in most jurisdictions.** This is why both `tv-channel-dvbt` systemd
services ship disabled -- installing the package does not start any
transmission, and you have to explicitly enable it after reading this
section. Check with your country's spectrum regulator (e.g. Ofcom in the
UK) before connecting a real antenna or transmitting at any meaningful
range/power. This project takes no responsibility for how you use it --
that's on you.

## Install

1. **Install the ffplayout fork.** Build a local `.deb` on the Pi (native
   arm64, no cross-compilation) from the fork repo:
   ```
   cd ~/src/ffplayout
   cargo build --release -p ffplayout --no-default-features --features embed_frontend
   cargo install cargo-deb --locked   # one-time
   gzip -kf assets/ffplayout.1   # .gitignore excludes the compiled .gz on
                                  # purpose; no build hook regenerates it yet
   cargo deb -p ffplayout --manifest-path backend/app/Cargo.toml \
       --no-build --variant arm64 -o dist/ffplayout_<version>-1_arm64.deb
   sudo apt-get install ./dist/ffplayout_<version>-1_arm64.deb
   ```
   If you're replacing a manually-built ffplayout install from before this
   package existed, remove `/etc/systemd/system/ffplayout.service` first
   (`sudo systemctl daemon-reload` after) so systemd picks up the package's
   own unit at `/usr/lib/systemd/system/ffplayout.service` instead of the
   stale manual copy -- leave `/etc/systemd/system/ffplayout.service.d/`
   drop-ins in place, they still apply on top of either.
   Then configure it via its web UI (`http://<pi-address>:8787`), including
   setting your channel's DVB service name/provider under the output config
   (this is what shows up as the channel name on a real TV, instead of
   ffmpeg's default `Service01`).

2. **Install `tv-channel-dvbt`.** Build it the same way, natively on the Pi:
   ```
   cd ~/src/tv-channel/scripts
   sudo apt-get install debhelper dpkg-dev   # one-time
   dpkg-buildpackage -us -uc -a arm64
   sudo apt-get install ../tv-channel-dvbt_<version>_arm64.deb
   ```

3. **Edit `/etc/tv-channel-dvbt/dvbt.conf`** for your local bandwidth/
   frequency (see Config reference below) -- do this *before* enabling
   the transmit service.

4. **Enable it explicitly:**
   ```
   sudo systemctl enable --now tv-channel-dvbt-transmit.service
   ```
   This also starts `tv-channel-dvbt-relay.service` and, if it isn't
   already running, `ffplayout.service` -- the three are chained so that
   stopping any one of them stops everything downstream of it too.

## Config reference (`/etc/tv-channel-dvbt/dvbt.conf`)

| Key | Default | Meaning |
|---|---|---|
| `BANDWIDTH_HZ` | `8000000` | **Must match your country's real DVB-T broadcast standard, not an arbitrary choice.** 8MHz is the UK/most-of-Europe standard and is what this project validated end-to-end (GNU Radio -> HackRF -> a real TV). Only change this if your own country's terrestrial standard genuinely uses a different bandwidth -- this project's earlier 6MHz configuration was only ever confirmed against Kaffeine's non-standard channel definition, never a real TV. |
| `CENTER_FREQ_HZ` | `610000000` | Transmit center frequency in Hz. Must be a frequency you're legally permitted to use. |
| `TX_GAIN` | `40` | HackRF TX gain in dB. |
| `FFPLAYOUT_MULTICAST_ADDR` / `FFPLAYOUT_MULTICAST_PORT` | `239.1.1.1` / `5000` | Where the relay joins ffplayout's multicast output. Must match ffplayout's own stream output config. |
| `RELAY_LISTEN_PORT` | `6000` | Local loopback port the relay re-emits on and the flowgraph listens on. |
| `PACKETS_PER_DATAGRAM` | `40` | TS packets batched per UDP datagram between the relay and GNU Radio. See Troubleshooting. |
| `TARGET_BITRATE_BPS` | unset (auto) | Overrides the bitrate auto-derived from `BANDWIDTH_HZ`. Only needed if you change the modulation profile itself. |

## Troubleshooting

- **Continuous DVB-T underruns** (the flowgraph never settles, or you see
  it struggling to keep up): this project bisected a real underrun cliff at
  8MHz -- below 34-35 packets per UDP datagram it never settles, above it
  settles to a handful of harmless startup underruns and then runs clean.
  The shipped default of 40 has margin above that cliff on a Pi 4 + HackRF
  One; if different hardware or a different bandwidth underruns for you,
  raise `PACKETS_PER_DATAGRAM` in `dvbt.conf`.
- **Check logs**: `journalctl -u tv-channel-dvbt-relay -u tv-channel-dvbt-transmit`.
- **HackRF not found by the transmit service**: it needs the `plugdev`
  group (granted via the unit's own `SupplementaryGroups=`, not the
  `dvbtx` user's permanent group membership) -- confirm with
  `systemd-run --uid=dvbtx --property=SupplementaryGroups=plugdev hackrf_info`
  rather than a plain `sudo -u dvbtx hackrf_info`, which won't have it.
- **Real-time scheduling didn't engage**: GNU Radio logs a warning
  (`Error: failed to enable real-time scheduling`) if this fails, which
  causes exactly the same underrun symptoms as too-small a datagram batch.
  Confirm `systemctl show tv-channel-dvbt-transmit -p LimitRTPRIO` reports
  `95`, not `0`.

## Playlist / ad-break tooling

### Splitting adverts

`detect_ad_breaks.sh` and `split_ads.sh` help split a single video
collection of adverts into discrete files per ad.

```
./detect_ad_breaks.sh <ad break collection file> <cuts file>
```

Scans the collection for black frames or silence; each hit becomes an entry
in the cuts file with a timestamp. A suspiciously short (<8s) or long (>60s)
cut is flagged in the file for manual review -- view it in VLC to confirm the
cut point before proceeding, then remove all comments from the cuts file.

```
./split_ads.sh <ad break collection file> <cuts file> <target directory> <widthxheight>
```

Uses ffmpeg to split the original collection into individual ad files,
resized to the target width/height. SD sources are pillarboxed (black bars
left/right) to preserve the original aspect ratio.

### Building a Playlist

`build_playlist.py` constructs a JSON playlist for ffplayout. You supply an
ordered list of programme files plus markers for where the ident and ad
breaks go; it fills in the ident automatically and picks a random (but then
fixed/inspectable) clip from the Adverts folder for each ad-break marker.

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

`--push` requires a valid bearer token for that channel's admin/user account.
Getting that token isn't scripted here (log in via the ffplayout web UI and
check your browser's devtools network tab / settings page for it) -- this
tool only builds and optionally posts the JSON, it doesn't manage auth.
