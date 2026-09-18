#!/usr/bin/env bash
set -e

python3 -u relay_to_hackrf.py &
#python3 -u dvbt_tx_2k_qpsk.py &
python3 -u dvbt_tx_2k_qpsk_8mhz_test.py &

exit 0
