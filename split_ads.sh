#!/usr/bin/env bash
# Cut an adverts compilation into individual clips at reviewed timestamps,
# re-encoding each clip to the channel's house format (default 1920x1080)
# with the source scaled and pillarboxed/letterboxed to fit. Re-encoding
# (rather than stream copy) also gives frame-accurate cuts, since -c copy
# can only cut on keyframe boundaries. Uses the Pi 4's hardware H.264
# encoder (h264_v4l2m2m) — ~8x faster than software libx264 on this board.
#
# Usage: split_ads.sh <compilation-file> <timestamps-file> <output-dir> [WxH]
#
# timestamps-file: one cut point per line (seconds or HH:MM:SS.mmm),
# lines starting with # are ignored. These are the *boundaries* between
# ads — N timestamps produce N+1 clips (start-of-file to end-of-file).

set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "Usage: $0 <compilation-file> <timestamps-file> <output-dir> [WxH]" >&2
    exit 1
fi

input="$1"
timestamps_file="$2"
output_dir="$3"
target_res="${4:-1920x1080}"
target_w="${target_res%x*}"
target_h="${target_res#*x}"

if [[ ! -f "$input" ]]; then
    echo "Error: input file not found: $input" >&2
    exit 1
fi
if [[ ! -f "$timestamps_file" ]]; then
    echo "Error: timestamps file not found: $timestamps_file" >&2
    exit 1
fi

mkdir -p "$output_dir"

mapfile -t cuts < <(sed 's/#.*//' "$timestamps_file" | sed 's/[[:space:]]*$//' | grep -vE '^\s*$' | awk '$1 > 0')

duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input")

bounds=("0" "${cuts[@]}" "$duration")
count=${#bounds[@]}
clip_num=1

for ((i = 0; i < count - 1; i++)); do
    start="${bounds[i]}"
    end="${bounds[i + 1]}"
    out_file=$(printf "%s/advert-%03d.mp4" "$output_dir" "$clip_num")

    echo "Clip $clip_num: $start -> $end  =>  $out_file"
    ffmpeg -y -loglevel error -ss "$start" -to "$end" -i "$input" \
        -vf "scale=${target_w}:${target_h}:force_original_aspect_ratio=decrease,pad=${target_w}:${target_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p" \
        -c:v h264_v4l2m2m -b:v 6M \
        -c:a aac -b:a 192k \
        -movflags +faststart \
        "$out_file"

    clip_num=$((clip_num + 1))
done

echo "Done: $((count - 1)) clips written to $output_dir"
