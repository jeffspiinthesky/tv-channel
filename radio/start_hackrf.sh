#!/usr/bin/env bash
set -e

# --target-bitrate must match the flowgraph being launched below: EN 300 744
# useful bitrate is 4,976,000bps at 8MHz vs 3,732,000bps at 6MHz.
python3 -u relay_to_hackrf.py --target-bitrate 4976000 &
#python3 -u dvbt_tx_2k_qpsk.py &
python3 -u dvbt_tx_2k_qpsk_8mhz_test.py &

exit 0
