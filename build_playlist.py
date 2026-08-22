#!/usr/bin/env python3
"""Build a hand-authored ffplayout playlist JSON for one day.

You supply an ordered list of programme files plus markers for where the
ident and ad breaks go; this fills in the ident automatically and picks a
random (but then fixed/inspectable) clip from the Adverts folder for each
ad-break marker.

Input is a plain text "block file", one entry per line:
    PROGRAM /mnt/share/Movies/A-D/Anora (2024).mp4
    IDENT
    AD
    PROGRAM /mnt/share/Video/Breaking Bad/Season 1/Breaking.Bad.S01E01.mkv
    AD
    ...

Output is ffplayout's playlist JSON:
    {"channel": "...", "date": "YYYY-MM-DD", "program": [{"source": "..."}, ...]}

Usage:
    build_playlist.py blocks.txt --date 2026-08-21 --channel "Main Channel" \\
        --out playlist.json
    build_playlist.py blocks.txt --date 2026-08-21 --channel "Main Channel" \\
        --push --channel-id 1 --base-url http://localhost:8787 --token "$FFPLAYOUT_TOKEN"

--push requires a valid bearer token for that channel's admin/user account.
Getting that token isn't scripted here (log in via the ffplayout web UI and
check your browser's devtools network tab / settings page for it) — this
tool only builds and optionally posts the JSON, it doesn't manage auth.
"""

import argparse
import json
import random
import sys
import urllib.request
from pathlib import Path

DEFAULT_IDENT = "/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Idents/PITS_Intro.mp4"
DEFAULT_ADVERTS_DIR = "/mnt/share/YouTube/JeffsPiInTheSky/TV-Channel/Adverts"


def load_blocks(path):
    blocks = []
    for lineno, raw in enumerate(Path(path).read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        kind = parts[0].upper()
        if kind == "PROGRAM":
            if len(parts) < 2:
                sys.exit(f"line {lineno}: PROGRAM needs a file path")
            blocks.append(("PROGRAM", parts[1]))
        elif kind in ("IDENT", "AD"):
            blocks.append((kind, None))
        else:
            sys.exit(f"line {lineno}: unknown block type {kind!r}")
    return blocks


def pick_advert(adverts_dir, rng):
    candidates = sorted(p for p in Path(adverts_dir).iterdir() if p.is_file())
    if not candidates:
        sys.exit(f"no advert clips found in {adverts_dir}")
    return str(rng.choice(candidates))


def build_program(blocks, ident_path, adverts_dir, seed):
    rng = random.Random(seed)
    program = []
    for kind, value in blocks:
        if kind == "PROGRAM":
            program.append({"source": value})
        elif kind == "IDENT":
            program.append({"source": ident_path})
        elif kind == "AD":
            program.append({"source": pick_advert(adverts_dir, rng)})
    return program


def push_playlist(base_url, channel_id, token, playlist):
    url = f"{base_url.rstrip('/')}/api/playlist/{channel_id}"
    data = json.dumps(playlist).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        print(f"POST {url} -> {resp.status}")
        print(resp.read().decode())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blocks_file", help="text file describing the day's running order")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--channel", required=True, help="channel name to embed in the playlist JSON")
    ap.add_argument("--ident", default=DEFAULT_IDENT)
    ap.add_argument("--adverts-dir", default=DEFAULT_ADVERTS_DIR)
    ap.add_argument("--seed", type=int, default=None, help="fix the advert RNG for a reproducible run")
    ap.add_argument("--out", help="write playlist JSON here")
    ap.add_argument("--push", action="store_true", help="also POST the playlist to a running ffplayout instance")
    ap.add_argument("--base-url", default="http://localhost:8787")
    ap.add_argument("--channel-id", type=int, help="ffplayout channel id, required with --push")
    ap.add_argument("--token", help="bearer token, required with --push (or set FFPLAYOUT_TOKEN)")
    args = ap.parse_args()

    blocks = load_blocks(args.blocks_file)
    program = build_program(blocks, args.ident, args.adverts_dir, args.seed)
    playlist = {"channel": args.channel, "date": args.date, "program": program}

    text = json.dumps(playlist, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"Wrote {args.out}")
    else:
        print(text)

    if args.push:
        import os

        token = args.token or os.environ.get("FFPLAYOUT_TOKEN")
        if not args.channel_id or not token:
            sys.exit("--push requires --channel-id and --token (or FFPLAYOUT_TOKEN)")
        push_playlist(args.base_url, args.channel_id, token, playlist)


if __name__ == "__main__":
    main()
