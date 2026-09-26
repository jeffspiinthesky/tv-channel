#!/bin/sh
# Sources /etc/tv-channel-dvbt/dvbt.conf and execs dvbt_tx.py with the
# resulting flags. See that conf file's header for why this is a plain
# shell wrapper rather than systemd EnvironmentFile substitution.
set -eu

CONF="${DVBT_CONF:-/etc/tv-channel-dvbt/dvbt.conf}"
if [ ! -r "$CONF" ]; then
    echo "transmit-wrapper: cannot read $CONF" >&2
    exit 1
fi
. "$CONF"

exec python3 -u /usr/lib/tv-channel-dvbt/dvbt_tx.py \
    --udp-port "${RELAY_LISTEN_PORT:?RELAY_LISTEN_PORT not set in $CONF}" \
    --center-freq "${CENTER_FREQ_HZ:?CENTER_FREQ_HZ not set in $CONF}" \
    --tx-gain "${TX_GAIN:?TX_GAIN not set in $CONF}" \
    --bandwidth-hz "${BANDWIDTH_HZ:?BANDWIDTH_HZ not set in $CONF}" \
    --packets-per-datagram "${PACKETS_PER_DATAGRAM:-40}"
