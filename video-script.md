# Video script: setting up the ffplayout TV channel

Running log of every command used to build this, in order, for recording the
YouTube walkthrough. Update this file as we go — don't let it drift from
what was actually run.

Status key: ✅ done and verified · ⏳ template, not run for real yet · 🖱️ manual UI step (no command)

---

## 1. Install ffplayout ✅

```bash
cd /tmp
curl -LO https://github.com/ffplayout/ffplayout/releases/download/v2.1.1/ffplayout_v2.1.1-1_arm64.deb
sudo apt install -y /tmp/ffplayout_v2.1.1-1_arm64.deb
```

Creates the `ffpu` system user and the `ffplayout` systemd service.

```bash
sudo systemctl enable --now ffplayout
systemctl status ffplayout --no-pager
```

Note for the recording: ffmpeg 7.1.5 was already installed on this Pi, so
there's no separate ffmpeg install step to show — worth a quick `ffmpeg
-version` on camera to prove the prerequisite is already met.

---

## 2. Create the channel asset folders on the NAS ✅

```bash
mkdir -p "/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Idents" \
         "/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Adverts"

cp "/mnt/share/YouTube/JeffsPiInTheSky/Intro/PITS_Intro.mp4" \
   "/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Idents/PITS_Intro.mp4"
```

Sanity check that the ffplayout service user can actually read it:

```bash
sudo -u ffpu ffprobe -v error -show_entries format=duration \
  "/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Idents/PITS_Intro.mp4"
```

---

## 3. First-time ffplayout setup 🖱️ ✅

No command — this was a browser step, done live:

1. Browse to `http://<pi-ip>:8787`.
2. Complete the setup form: admin username/email/password.
3. Paths used:
   - **Storage** = `/mnt/share` (the NAS — this is the actual content library: Movies, Video, TV-Channel/Idents, TV-Channel/Adverts)
   - **Logs** = `/var/log/ffplayout` (default, local — kept local so a network hiccup can't stall/fail a log write)
   - **Playlists** = `/var/lib/ffplayout/playlists` (default, local — kept off the network since playlist JSON is read on the playout-critical path)
   - **Public (HLS)** = `/usr/share/ffplayout/public` (default, local — HLS segment writes happen every few seconds and need to be fast/reliable, which rules out SMB)

Caveat worth mentioning on camera: the NAS mount is `uid=1000,gid=1000`
(the `pi` user), and `ffpu` isn't uid 1000 — it can read everything under
Storage but can't write. Fine for our workflow (adverts/idents get placed
there directly as `pi`, playlists are just JSON), but ffplayout's built-in
upload/organize-media feature would fail against Storage if ever used.

(Setup schema, for reference if the CLI/API path is ever wanted instead of
the browser: `username`, `mail`, `password`, `two_factor` (bool), `logs`,
`playlists`, `public`, `storage`, `shared` (bool) — confirmed directly
against this instance's own `/api/setup` validation errors.)

---

## 4. Output config → local MPEG-TS 🖱️ ✅

In the channel's Playout/Output config screen in the web UI:

| Field | Value |
|---|---|
| Output Mode | `Stream` |
| Stream Type | `UDP` |
| Stream target URL | `udp://127.0.0.1:5000?pkt_size=1316` |
| Width / Height | `1920` / `1080` |
| FPS | `25` (matches the adverts, standard UK/PAL rate — the 30fps ident gets frame-rate-converted to match) |
| Video Codec | `h264_v4l2m2m` |

The video codec choice matters a lot: software `libx264` benchmarks too
slow on this Pi 4 for continuous 1080p live output (full numbers in step
5's advert-encoding benchmark below — 5.3x slower than realtime at medium
preset). Confirmed `h264_v4l2m2m` (the Pi 4's hardware H.264 encoder)
shows up as a selectable option here and selected it — this is what makes
the channel able to run continuously in real time at all.

*(Heads up for filming: this codec choice gets revisited later — see
step 8 — once a bitrate bug with `h264_v4l2m2m` surfaces. Worth
foreshadowing on camera rather than treating it as a final answer here.)*

Also found while digging into the UI code for this: ffplayout v2.1.1 *does*
have Width/Height/FPS as first-class output settings (I was wrong earlier
saying there's no resolution normalization — I'd only grepped for quoted
JSON string keys and missed the bare `.width`/`.height` property accesses
in the frontend JS). This likely means ffplayout already scales/pads every
source to the configured output resolution automatically. Doesn't undo the
work pre-conforming the adverts to 1920x1080 in step 5 — that was still
worth doing for the frame-accurate cuts alone — but it's good to know the
channel would probably have handled mismatched movie/TV-show resolutions
correctly either way.

---

## 5. Slice the adverts compilation into individual clips ✅

Compilation: `/mnt/share/adverts/ads.mp4` (640x480 h264/aac, ~62 min, 4:3).
Channel house format is 1920x1080 (16:9), so each clip gets scaled and
pillarboxed at slicing time rather than relying on ffplayout to normalize
mismatched resolutions live — checked the installed v2.1.1 web UI and
current docs directly, there's no exposed setting for that in this version,
so conforming to house format at ingest is the safe choice. Re-encoding
(instead of stream copy) also gives frame-accurate cuts as a side benefit.

```bash
/home/pi/src/tv-channel/scripts/detect_ad_breaks.sh /mnt/share/adverts/ads.mp4
```

✅ Ran this — 126 candidate cut points written to `/mnt/share/adverts/ads.cuts.txt`.
Median gap ~31s (plausible ad length), but 9 gaps under 8s (flagged as
possible false positives) and 9 gaps over 60s (flagged as possible missed
cuts) — needs a manual pass before splitting. Worth showing this review
step on camera — it's the honest reason this is "semi-automated" not fully
automatic.

✅ Manually reviewed every flagged timestamp in VLC:
- All 9 "SHORT" flags turned out to be genuine short cuts between ads, not
  detector glitches — left as-is.
- Of the 9 "LONG" ranges: 4 were genuinely one long ad (60.4–61.6s, no
  action). The other 5 had missed cuts — one had 2 missed ads inside it
  (43:26 and 43:57), the rest had 1 each. Added 7 new cut points by hand
  after scrubbing to the exact transition. Total is now 133 cut points
  (134 clips).

`/mnt/share/adverts/ads.cuts.txt` is reviewed and ready to split (132 cut
points -> 133 clips). It's also symlinked into the repo at
`scripts/ads.cuts.txt` for convenience.

**Hardware encoding**: benchmarked software libx264 (medium preset, crf 18)
against the Pi 4's hardware H.264 encoder (`h264_v4l2m2m`, exposed via
V4L2 M2M — NOT vaapi, which is Intel/AMD-only and doesn't exist on the
Broadcom VideoCore GPU) on a 20.7s test clip: software took 1m49s
(5.3x slower than realtime), hardware took 12.9s (faster than realtime,
~0.62x). ~8.5x speedup — the difference between roughly 5.5 hours and
under an hour for the full batch. `split_ads.sh` now uses
`-c:v h264_v4l2m2m -b:v 6M` instead of libx264.

**Local-then-sync**: to avoid writing 133 small files over SMB while the
hardware encoder is also under load, output goes to local SD storage first
(`/home/pi/Videos/Adverts`, plenty of headroom at 17GB free), then gets
synced to the NAS as a separate step once the batch finishes.

```bash
/home/pi/src/tv-channel/scripts/split_ads.sh \
  /mnt/share/adverts/ads.mp4 \
  /mnt/share/adverts/ads.cuts.txt \
  /home/pi/Videos/Adverts
```

✅ Ran this (in the background, ~40-55 min for 133 clips) — hit one bug
along the way worth mentioning on camera: the very first "cut" detected was
a black frame at t=0 (the compilation opens on black), which duplicated the
implicit start-of-file boundary and produced a zero-length first clip.
Fixed by removing that spurious entry from the cuts file, and hardened both
scripts (`awk '$1 > 0'` / `awk '$1 > 1'`) so a future compilation with the
same quirk doesn't hit it again.

Sync the finished clips to the NAS:

```bash
rsync -av --progress /home/pi/Videos/Adverts/ \
  "/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Adverts/"
```

✅ Done end to end — 133 clips, 2.2GB, all 1920x1080 h264/aac, confirmed
readable by `ffpu`. `advert-100.mp4` is only 0.68s — that's expected, it's
one of the short bumper cuts confirmed as legit during review, not an
error.

(Optional 4th arg to `split_ads.sh` overrides the target resolution,
default `1920x1080`.)

**Bug found and fixed**: in the ffplayout web UI, only the ident's play
button worked in the playlist preview — adverts errored as "wrong format".
Diagnosed directly (not guessed): our encode command was missing
`-movflags +faststart`, so the MP4 index (`moov` atom) landed at the end
of the file instead of the front — a well-known cause of browsers
rejecting progressive `<video>` playback. Confirmed by checking byte
offsets directly: `mdat` before `moov` on every advert clip. The ident
happened to "work" anyway only because it's tiny (346KB) — small enough
that the browser fetches the whole file regardless of index placement;
same underlying issue, just masked by size. Bug does *not* affect the real
playout engine (that's full ffmpeg, not a browser `<video>` tag) — this
was purely a web-preview issue, but a real one worth fixing regardless.

Fix: added `-movflags +faststart` to `split_ads.sh`'s ffmpeg command for
future runs, and remuxed all 133 existing clips in place (`-c copy
-movflags +faststart` — pure remux, no re-encode needed, fast) then
re-synced to the NAS. Verified: `moov` now at byte 36 on every sampled
clip, before `mdat`.

---

## 6. Build a day's playlist ✅ (test run)

Channel name confirmed: **"Jeffs PI in the Sky"**, channel ID 1.

Wrote a test running order at `scripts/blocks-test-2026-08-20.txt`:

```
IDENT
PROGRAM /mnt/share/Movies/A-D/Anora (2024).mp4
AD
PROGRAM /mnt/share/Video/Breaking Bad/Season 1/Breaking Bad S01E01 - Pilot.avi
AD
```

Then:

```bash
python3 scripts/build_playlist.py scripts/blocks-test-2026-08-20.txt \
  --date 2026-08-20 --channel "Jeffs PI in the Sky" --seed 42 \
  --out scripts/playlist-test-2026-08-20.json
```

**Turns out the web UI has no raw-JSON paste** — the day's playlist lives
on the top-level **Player** page (not under Configure), as a drop-pad you
build by dragging clips from the media browser, or via its **Import
text/m3u file** button. Used the latter: converted the same running order
to a standard `.m3u` at `scripts/playlist-test-2026-08-20.m3u`:

```
#EXTM3U
#EXTINF:-1,Ident
/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Idents/PITS_Intro.mp4
#EXTINF:-1,Anora (2024)
/mnt/share/Movies/A-D/Anora (2024).mp4
#EXTINF:-1,Advert 029
/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Adverts/advert-029.mp4
#EXTINF:-1,Breaking Bad S01E01 - Pilot
/mnt/share/Video/Breaking Bad/Season 1/Breaking Bad S01E01 - Pilot.avi
#EXTINF:-1,Advert 007
/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Adverts/advert-007.mp4
```

Confirmed: the import endpoint (`PUT /api/file/{id}/import`) is a
browser-side file upload, not a server-side path — the `.m3u` has to be
selectable from whichever machine's browser is driving the UI. Confirmed
**absolute filesystem paths work directly** in the m3u (no need for
storage-relative paths). Imported it for 2026-08-20, it populated the
drop-pad correctly as a formatted list, then **Save Playlist**.

Note for next time: `build_playlist.py`'s JSON output isn't actually
usable via the UI's import — only `.m3u` is. Worth adding an `.m3u` export
mode to that script since the UI is the real path in, not the JSON API
(still don't have an auth token to test `--push` against `/api/playlist`).

---

## 7. End-to-end test ✅ (real findings along the way; HEVC/CPU items deliberately deferred)

This step surfaced several genuine bugs/gotchas worth walking through on
camera, not just the happy path:

**Bug: `ffpu` couldn't access the hardware encoder.** First "Start"
attempt failed repeatedly with `[ERROR] Run channel 1 failed: Conflict:
Permission denied`. Root cause: `/dev/video11` (the `h264_v4l2m2m` device)
is owned by group `video`; `ffpu` wasn't a member. Fix:

```bash
sudo usermod -aG video ffpu
sudo systemctl restart ffplayout
```

**Gotcha: the "Start" button can silently no-op.** After the permission
fix, clicking Start showed no error but also spawned nothing — no ffmpeg
activity, no UDP traffic. Root cause: `day_start` was `05:59:25` (not
midnight) with `infinit: false` and a 24h `length`, but our test playlist
was only ~3 hours of content — so at evening wall-clock time, there was
nothing scheduled to play and no valid list. Fix: enabled **Infinite**
(loop the playlist to fill the day) in Playout config's Playlist Handling
section.

**Gotcha: `ss -uln` is the wrong tool to check UDP push output.** A UDP
*sender* doesn't bind/listen on the destination port, so `ss -uln | grep
<port>` will never show anything regardless of whether the stream is
flowing. Use `ffprobe udp://host:port` (or ffplay) to actually try
receiving instead.

**Bug: `.avi` files silently rejected.** Channel config has
`storage.extensions: ["mp4","mkv","webm"]` — `.avi` isn't in the list.
Swapping the Breaking Bad S01E01 `.avi` (Season 1 folder) for the
S04E02 `.mkv` (Season 4 folder, same show) fixed it. Worth remembering
when picking real content — check file extensions against this list.

**Confirmed working**: multicast output. Changed Stream target URL to
`udp://239.1.1.1:5000?pkt_size=1316` — reachable from another machine on
the LAN via VLC (`udp://@239.1.1.1:5000`), no need to reconfigure per
viewer. Also confirmed: `day_start` means ffplayout's "today" doesn't
follow midnight — a playlist saved for one date stops applying once the
clock crosses `day_start` into the next calendar day, and **Copy Playlist**
only copies the *currently loaded* list forward to another date, not a
past date to today — so re-importing the m3u for the new date was the
practical fix each morning during testing.

**Real, unresolved finding — desktop/VNC CPU contention.** First live
playback attempt showed "lego brick" corruption + `[h264] non-existing PPS
0 referenced` / `decode_slice_header error` on every probe. Root cause:
running a full desktop (labwc, VS Code with GPU process + multiple
renderers, Chromium) *and* a Raspberry Pi Connect / wayvnc remote-desktop
session *and* the live hardware-encoded transcode simultaneously
oversubscribed the Pi 4's 4 cores (load average peaked at 5.03, exceeding
core count). Disconnecting the Connect/VNC session measurably dropped
1-minute load average from 3.06 to 1.79. **Takeaway for the real
deployment**: don't run a full desktop + remote-desktop session on the Pi
during actual 24/7 operation — control it headless via the (lightweight)
web UI over plain HTTP instead.

**Real, unresolved finding — HEVC 1080p60 source content.** Even with the
desktop contention resolved, `ffplayout` sat at 129% CPU and playback was
still corrupted specifically while playing *Anora (2024).mp4*, which is
HEVC 1920x1080@60fps. No evidence ffplayout uses the Pi's hardware HEVC
decoder (`rpi-hevc-dec`, confirmed present as `/dev/video19`) for source
decoding — likely falls back to software HEVC decode, which is heavy at
1080p60 on any Pi. **Not fixed today** — flagged as a follow-up: the movie
library likely needs an audit for similarly demanding sources (HEVC,
high fps, 4K) that should be pre-transcoded to a lighter house format
before being added to real schedules, the same way the adverts were
already conformed to 1920x1080 h264.

Advert/Breaking Bad segments (H.264, SD/lightweight) played through
cleanly after skipping past *Anora*, at much lower CPU — good confirmation
that the earlier corruption was load-driven, not a fundamental pipeline
break. But it surfaced a second, separate, more serious finding:

**Confirmed bug: `h264_v4l2m2m` output is stuck at ~300-440kbps
regardless of config, and ffplayout gives no way to fix it.** Noticed via
VLC's stream stats showing ~300kbps for a 1920x1080 output — far too low
for that resolution, explaining the poor quality independent of any CPU
contention. Investigated directly using the API (see below):

- `GET /api/playout/codecs/1` shows `h264_v4l2m2m`'s *only* configurable
  setting is `maxrate` (despite `"uses_bitrate": true`) — no target
  bitrate field exists in ffplayout's schema for this codec, unlike
  `libx264`/`libx265`/`*_nvenc`/`*_vaapi`, which all get a full
  `preset`/`rate_control`/`quality`/`maxrate` set. Every V4L2 M2M hardware
  codec (`h264_v4l2m2m`, `hevc_v4l2m2m`, `mpeg4_v4l2m2m`) has this same gap.
- Tried adding a `b:v` key directly via `PUT /api/playout/config/1` to
  bypass the UI — server rejected it: `"unsupported video option \"b:v\"
  for codec \"h264_v4l2m2m\""`. The allowlist is enforced server-side, not
  just a UI limitation.
- Proved the actual cause empirically, outside ffplayout, on a real
  1920x1080 advert clip:
  - `-c:v h264_v4l2m2m -maxrate 2000k` (mirrors ffplayout's config) →
    **439kbps** actual output.
  - `-c:v h264_v4l2m2m -maxrate 20000k` (10x higher, still no `-b:v`) →
    **439kbps** — completely unchanged. `maxrate` alone is a no-op for
    this encoder.
  - `-c:v h264_v4l2m2m -b:v 6000k -maxrate 8000k` (explicit target rate)
    → **5.3Mbps** — proves the encoder works fine, it just needs `-b:v`,
    which ffplayout has no way to set for this codec.

**This is a real ffplayout limitation, not a config mistake on our part.**
Worth filing upstream (`github.com/ffplayout/ffplayout/issues`) — but
doesn't fix it today.

**Explored a resolution/software-encode workaround, benchmarked cleanly**
(with `ffplayout` stopped, to avoid contention skewing results):

| Test | Time for 10.88s clip | Realtime factor |
|---|---|---|
| 1080p, libx264 ultrafast, explicit bitrate | 15.85s | 1.46x — not viable |
| 540p, libx264 ultrafast, explicit bitrate | 11.30s | 1.04x — right at the edge |

`libx264` supports the full quality-control schema in ffplayout (unlike
the broken v4l2m2m path), so 540p software encode is a real potential
fix — but it means giving up the full-HD 1920x1080 target set at the
start of this project. **Decision at the time: keep 1080p + the broken
hardware encoder for now** rather than downgrade resolution; revisit as a
follow-up (either the libx264-at-540p path, or wait/patch for a working
v4l2m2m bitrate option).

*(This decision is reversed in step 8 below — worth landing that reversal
clearly on camera rather than let it look like the script contradicts
itself.)*

**Also learned along the way**: API tokens are worth using over passwords
for this kind of live debugging — got a bearer token from browser
DevTools (Network tab → any authenticated request → `Authorization`
header) rather than a real login, which let direct `curl`/API
investigation happen without ever handling an actual credential. Tokens
here are short-lived (~45 min) via JWT `exp`.

Also confirmed: `ss -uln` was never going to show a UDP *push* target
(sender doesn't bind the destination port) — `ffprobe udp://host:port` or
an actual receiver is the correct check, a mistake worth not repeating.

**Net result for this video**: the full pipeline — install, hardware
permissions, content library, faststart/extension gotchas, hand-authored
playlist with random-ad insertion, hardware-encoded multicast output
reachable from another machine on the LAN — genuinely works end to end.
Picture quality on the hardware encoder path is a known, well-characterized
open issue for a follow-up, not a mystery.

## 8. Follow-up: confirming the bitrate bug and fixing it with libx264 ✅

✅ Confirmed from the compiled binary itself, not just observation. Dumped
`ffplayout`'s string table and compared `audio_bitrate` (a real DB column
and API field, default 128) against video: no `video_bitrate`, no
`"bitrate"`, no `-b:v` literal anywhere in the binary. Video encoding is
entirely driven by a free-form `video_options` JSON blob whose known keys
(seen concatenated in the binary) are `preset`, `bufsize`, `rate_control`,
`minrate`, `maxrate`, `quality`/`crf`, plus hardware-specific extras
(`rc`, `cq`, `qp`, `async_depth`, `row-mt`, ...). No constant-bitrate key
exists for any codec — only rate-control caps and quality targets.

```bash
strings -n 4 /usr/bin/ffplayout > fp_strings.txt
grep -n -- '-b:v\|video_bitrate\|"bitrate"' fp_strings.txt   # nothing
grep -n -- '-b:a\|audio_bitrate' fp_strings.txt              # real hits
```

✅ Confirmed server-side (not just UI) that `h264_v4l2m2m`'s schema really
only exposes `maxrate` — tried forcing a `quality` key onto it directly
via the API to see if it'd be silently accepted:

```bash
curl -s http://127.0.0.1:8787/api/playout/codecs/1 \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' | less   # curated per-codec schema

curl -s -X PUT http://127.0.0.1:8787/api/playout/config/1 \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' -H 'Content-Type: application/json' \
  --data '{... "output": {..., "video_codec":"h264_v4l2m2m",
           "video_options":{"maxrate":"2000","quality":"20"}, ...}}'
# → HTTP 400: "unsupported video option \"quality\" for codec \"h264_v4l2m2m\""
```
Hard proof the allowlist is enforced per-codec on the server, not a UI gap.

🖱️ Manually tried dropping resolution to 1280x720 via the web UI (keeping
`h264_v4l2m2m` + `maxrate: 2000`) to see if fewer pixels would let the
encoder's fixed internal bitrate look better. **Still measured ~400kbps**
— confirms the encoder's default rate is a hard-coded fallback, completely
decoupled from both `maxrate` and resolution.

✅ **Fix applied and verified live**: switched the channel to software
`libx264` at 960x540, `rate_control: cbr` (the one mode where `maxrate`
becomes a real target, not just a cap), `preset: ultrafast`, `maxrate:
3000` (kbps). This is the config already benchmarked as realtime-viable.

```bash
curl -s http://127.0.0.1:8787/api/playout/config/1 -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -o config.json   # GET current config, edit output{} in place

curl -s -X PUT http://127.0.0.1:8787/api/playout/config/1 \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' -H 'Content-Type: application/json' \
  --data @config.json
# → {"requires_restart": true}

curl -s -X POST http://127.0.0.1:8787/api/control/1/process \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' -H 'Content-Type: application/json' \
  --data '{"command":"restart"}'
# → "Success"
```

Verified the real, on-the-wire bitrate by capturing 10s of the multicast
stream and measuring actual bytes received (container-reported `bit_rate`
from `ffprobe` alone isn't reliable on a live UDP join mid-GOP):

```bash
ffmpeg -y -i "udp://239.1.1.1:5000?pkt_size=1316" -t 10 -c copy -f mpegts capture540.ts
# size 3,560,532 bytes over 10s → ~2848 kbps measured (video ~3000kbps target + 130kbps AAC audio)
```

**Result: ~2.85Mbps actual throughput at 960x540, up from ~400kbps at
1920x1080 — roughly 7x the bitrate, and this time it's real, controllable
CBR rather than an ignored cap.** Trade-off made explicit: gave up the
full-HD target set at the start of the project in exchange for an encoder
that actually honors a bitrate. Picture quality still needs an eyeball
check on an actual DVB-T-bound receiver before calling this done, but the
"why does it look bad" mystery from the previous video is now fully
explained and fixed at the config layer.

🖱️ **Eyeballed live in VLC — confirmed superb.** User's verdict: "looking
absolutely superb... higher resolution would be nice but as-is, this is
absolutely fine." Closes out the bitrate investigation for this video —
960x540 `libx264` CBR @ 3000kbps is the accepted picture-quality config
going forward, until/unless a future video revisits resolution.

## 9. Console-mode switch broke the NAS mount at boot ✅ (found and fixed)

Switched the Pi to boot without a desktop, to save CPU for 24/7 playout:

```bash
sudo systemctl set-default multi-user.target
```

After a reboot, ffplayout was "running" but the web UI's progress bar
raced through the playlist far faster than real time, and nothing showed
up on the multicast UDP stream. Symptom pointed at ffplayout burning
through "missing" media rather than a genuine timing/clock bug.

Diagnosed directly: `/mnt/share` (the NAS holding all channel content —
idents, adverts, movies) was completely empty — never mounted at boot.

```bash
mount | grep -i share      # nothing
journalctl -b -u mnt-share.mount --no-pager
# mount error: could not resolve address for pve.local: Unknown error
```

**Root cause**: the fstab entry uses the NAS's mDNS name (`pve.local`).
systemd already orders CIFS mounts after `network-online.target`
automatically (confirmed via `systemctl show ffplayout... -p After`) —
but `network-online.target` only guarantees the network *link* is up, not
that Avahi/mDNS resolution is ready yet. Under the old desktop boot, the
extra time taken to reach a graphical session gave Avahi enough of a head
start that this never surfaced. Console-mode boots straight to
`multi-user.target` fast enough that the mount attempt loses the race,
fails once, and (with plain `_netdev`-style fstab options) never retries.
User confirmed the immediate fix live: unmounting and remounting by hand
brought the share straight back.

**Real fix — remove the mDNS dependency entirely**, plus make ffplayout
depend on the mount so this fails loudly instead of silently next time:

```bash
# fstab: swap the mDNS hostname for the NAS's static IP
sudo sed -i 's|//pve.local/share|//192.168.0.100/share|' /etc/fstab
# also added x-systemd.mount-timeout=30 to the mount options

# ffplayout.service drop-in: wait for the share before starting
sudo tee -a /etc/systemd/system/ffplayout.service.d/override.conf <<'EOF'

[Unit]
RequiresMountsFor=/mnt/share
EOF

sudo systemctl daemon-reload
sudo umount /mnt/share
sudo mount -a
sudo systemctl restart ffplayout
```

Verified: mount now resolves by IP (no Avahi involved), and
`systemctl show ffplayout.service -p After -p Requires` lists
`mnt-share.mount` in both — ffplayout is now ordered after, and
dependent on, the share being mounted.

Worth calling out on camera: this is the concrete cost of switching to
console mode for real 24/7 operation — things that "just worked" because
a slower, more permissive desktop boot papered over a race condition can
break the moment the boot gets leaner and faster. Good example of why
headless deployments need their dependency ordering made explicit rather
than accidental.

## 10. Follow-up: "No clip is playing" / Play button did nothing ✅

After the mount fix above, the web UI still showed "No clip is playing"
and clicking Play did nothing — no error toast, no obvious failure.
Two distinct bugs stacked on top of each other, both stemming from the
earlier reboot/mount outage:

**Bug A — corrupted playhead state.** Queried playout state directly:

```bash
curl -s http://127.0.0.1:8787/api/control/1/media/current \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
# {"elapsed":6249.4,"index":5,"media":{"source":""},"shift":6237.07,...}
```

`index: 5` is out of range (today's playlist only has indices 0-4), and
`shift` (the channel's persisted `time_shift`, stored in
`/usr/share/ffplayout/db/ffplayout.db`, table `channels`) was frozen at
~6237s. Root cause: while the NAS was unmounted (step 9), ffplayout's
progress bar was racing through "missing" files and inflated this stored
shift value far past the real position, landing on a playlist index that
doesn't exist. `start`/`stop`/`restart` via `/api/control/1/process` all
returned `"Success"` but were silent no-ops — the engine already believed
it was "playing" this broken state.

Fix: found an undocumented (not in the web UI, but present in the
compiled frontend JS) reset endpoint via `strings` on the frontend
bundle — different from `/process`, uses field name `control` not
`command`:

```bash
curl -s -X POST http://127.0.0.1:8787/api/control/1/playout \
  -H "Authorization: Bearer <ACCESS_TOKEN>" -H 'Content-Type: application/json' \
  --data '{"control":"reset"}'
# {"operation":"reset_playout_state"}
```

Confirmed via `media/current` immediately after: `shift` dropped to
`0.0`.

**Bug B — missing filler/fallback clip.** Even after the reset, the next
`start` attempt logged a real error for the first time:

```
[ERROR] Run channel 1 failed: Conflict: failed to generate fallback for  | Retry in 1 seconds
```

The channel config's `storage_filler` is `filler/filler.mp4` (relative to
Storage = `/mnt/share`), and that path had simply never existed — nobody
had created it. ffplayout tries to generate/verify this fallback clip on
every channel start (used to fill any gap in a playlist), and when that
fails, the whole start attempt aborts, leaving the engine in the same
"thinks it's running, nothing spawned" no-op state as Bug A.

Fix: generated a real filler clip matching the channel's house format
(960x540/25fps, same as the libx264 output config from step 8):

```bash
mkdir -p /mnt/share/filler
ffmpeg -y -f lavfi -i color=c=black:s=960x540:r=25 \
  -f lavfi -i anullsrc=r=48000:cl=stereo \
  -t 30 -c:v libx264 -preset ultrafast -c:a aac -b:a 128k -movflags +faststart \
  /mnt/share/filler/filler.mp4
```

Then explicit stop → start via the API (not just relying on the UI's
Play button, to watch each step directly):

```bash
curl -s -X POST http://127.0.0.1:8787/api/control/1/process \
  -H "Authorization: Bearer <ACCESS_TOKEN>" -H 'Content-Type: application/json' \
  --data '{"command":"stop"}'
curl -s -X POST http://127.0.0.1:8787/api/control/1/process \
  -H "Authorization: Bearer <ACCESS_TOKEN>" -H 'Content-Type: application/json' \
  --data '{"command":"start"}'
```

**Verified end to end**: `media/current` correctly showed
`index: 1, source: ".../Anora (2024).mp4"` with a sane `elapsed`/`in`, no
more errors in the journal, and a direct 8s capture of the multicast
stream confirmed clean 960x540 h264/aac at ~2.7Mbps — matching the
settled step-8 config exactly.

Also worth noting for the API-debugging toolbox: `/api/control/{id}/playout`
(commands like `reset`/`next`/`back`, field name `control`) is a
*separate* endpoint from `/api/control/{id}/process` (commands
`status`/`start`/`stop`/`restart`, field name `command`) — found by
`strings`-dumping the compiled frontend bundle inside `/usr/bin/ffplayout`
for API call sites, same technique as the bitrate investigation in step 8.

## 11. Reboot test — confirming the console-mode boot fixes hold ⏳

Everything above was fixed live, in a running session, one piece at a
time — never actually proven to survive a cold boot. Rebooting now to
confirm the whole chain (NAS mount by IP, `ffplayout.service` waiting on
that mount, and the filler clip existing) comes up clean with no manual
intervention.

```bash
sudo reboot
```

Expect on the next session: `mount | grep share` shows `/mnt/share`
mounted via `192.168.0.100` with no manual `mount -a` needed,
`systemctl status ffplayout` active, and the channel actually playing
(check `/api/control/1/media/current` and/or VLC on
`udp://@239.1.1.1:5000`) without needing the `/playout` reset trick or
any other manual poke from step 10. If any of that isn't true
automatically, the fix from earlier today wasn't actually complete.

**Result: ✅ confirmed clean.** Cold boot came up with `/mnt/share`
mounted by IP, `ffplayout.service` active on its own, and the stream
visible in VLC — no manual intervention needed. The boot-race fix holds.

## 12. Diagnosing VLC stutter (audio skips, dropped frames) after the reboot ✅

Stream was up and confirmed working, but VLC playback was occasionally
stuttery — audio skips and frame drops. Checked system health rather
than ffplayout's own logs first, since the journal showed nothing (no
drop/underrun/error lines at all):

```bash
uptime
vcgencmd measure_temp
vcgencmd get_throttled
ps aux --sort=-%cpu | head -15
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

Findings:
- `ffplayout` alone: **241% CPU**, load average 4.21 on this 4-core Pi,
  just ~3 minutes after boot with nothing else meaningfully running.
- `vcgencmd measure_temp`: **83.7°C**. `get_throttled`: **`0x80008`** —
  bit 19 (soft temperature limit *currently active*) + bit 3 (has
  occurred). No under-voltage bits set, so this is purely thermal, not
  a power-supply problem.
- User confirmed: **passive heatsink/case only, no fan.**

**Root cause**: the step-8 bitrate fix swapped the output encoder from
`h264_v4l2m2m` (hardware, cheap) to software `libx264` (`ultrafast`,
960x540, CBR 3000kbps) to get a real controllable bitrate. That software
encode is heavy enough on a Pi 4B to push the SoC into its ~80°C soft
throttle point during sustained 24/7 encoding, which throttles the clock
speed right when the realtime encode loop needs it most — producing the
audio skips/frame drops seen in VLC. Passive cooling alone isn't enough
to dissipate that sustained load.

**Fixed**: user took the case lid off (temp 83.7°C → 81.8°C, immediate
help but still right at the throttle edge), then got an external fan
blowing on the board. Sampled temp/throttle/CPU every 15s for 2 minutes
right after:

```bash
for i in $(seq 1 8); do
  ts=$(date +%H:%M:%S)
  temp=$(vcgencmd measure_temp)
  throttled=$(vcgencmd get_throttled)
  cpu=$(ps -o %cpu= -p $(pgrep -f '/usr/bin/ffplayout') | tr -d ' ')
  echo "$ts  $temp  $throttled  ffplayout_cpu=${cpu}%"
  sleep 15
done
```

Temp fell from 61.8°C to ~48-50°C over the 2 minutes and held there,
`get_throttled` stayed at `0xe0000` throughout (only the historical
"has occurred" bits — no "currently throttled" bit set at any sample),
while `ffplayout` kept its usual ~235-240% CPU the whole time. Fan is
genuinely carrying the software-encode load now. **Takeaway for future
24/7 operation on this hardware: an external/case fan is required
whenever running the `libx264` software encode from step 8** — passive
cooling alone throttles under sustained load.

## 13. Bumped output to 50fps (still 960x540) ✅

User tried raising the frame rate from 25fps to 50fps in the output
config (resolution/encoder unchanged: `libx264`, 960x540, CBR
`maxrate: 3000`, `preset: ultrafast`). Checked temp/throttle/CPU right
after with the fan running:

```bash
vcgencmd measure_temp
vcgencmd get_throttled
ps -o %cpu=,cmd= -p $(pgrep -f '/usr/bin/ffplayout')
```

48.2°C, `get_throttled` still only showing historical bits (no active
throttling), `ffplayout` at ~214% CPU, load average 3.31 — only
marginally higher than the 25fps numbers, comfortably within what the
fan can carry. **50fps at 960x540 is now the running config.**

## 14. Folded ad-hoc cut-annotation logic into detect_ad_breaks.sh ✅

Ran `detect_ad_breaks.sh` on a second PC and got the old raw-detector-log
format back, instead of the clean SHORT/LONG-annotated format from the
original Pi run. Root cause, traced through the session transcript from
2026-08-20: the annotated format was never part of the script — after the
first raw run, a one-off inline `python3 << 'PYEOF'` heredoc (never saved
as a file) rewrote `ads.cuts.txt` in place, computing the gap between each
pair of cut points and flagging any clip `<8s` (`SHORT`) or `>60s`
(`LONG`) with its computed duration and `HH:MM:SS.mmm` range. That
one-time transformation was applied directly to the output file and never
folded back into the script, so `scripts/detect_ad_breaks.sh` (and its
symlinked copy on the NAS at `/mnt/share/Video/TV Channel/adverts/`) kept
producing the old raw-dump format the whole time — not a memory gap, a
genuine script/output mismatch.

**Fix**: rewrote `detect_ad_breaks.sh` to compute the annotations itself
(via an embedded `python3` heredoc, using `ffprobe` for total duration
instead of the old run's hardcoded value) so the SHORT/LONG-flagged
format is now what the script always produces, on any machine. Dropped
the old "raw detector hits" log dump from the header, matching the
cleaned-up format the user actually reviewed against.

Verified by re-running against `/mnt/share/adverts/ads.mp4` (scratch
output, not overwriting the real reviewed `ads.cuts.txt`): output matched
the original reviewed file's SHORT/LONG flags exactly at every point that
survived review, plus correctly re-flagged the 4 additional `LONG` gaps
that had been manually fixed by adding cut points last time — confirming
the script now reproduces that original run's logic faithfully. Synced
the fixed script to both the repo copy and the NAS copy so they match.

## 15. Built the HackRF/GNU Radio DVB-T transmit chain, confirmed working in Kaffeine ✅

**Note:** the detailed step-by-step for this build (between 2026-09-02
and 2026-09-18) was never folded into this log — worth backfilling from
session transcripts separately. Headline result: `relay_to_hackrf.py`
(`scripts/relay/`, `scripts/radio/`) repacks ffplayout's multicast
MPEG-TS output into a HackRF-ready feed, a GNU Radio flowgraph
(`scripts/radio/dvbt_tx_2k_qpsk.grc`/`.py`, 2K FFT/QPSK/CR1-2/GI1-4)
builds the DVB-T OFDM signal and drives the HackRF One, and the
resulting broadcast was confirmed decoding cleanly in **Kaffeine** (on a
separate PC with a USB DVB-T tuner) at **610MHz, 6MHz channel
bandwidth**. This is where the previous video ended.

The next challenge — bumping this from the working 6MHz profile up to
the UK/EU-standard 8MHz channel bandwidth so a normal TV can actually
tune it — turned into its own investigation, picked up fresh in the
next video.
