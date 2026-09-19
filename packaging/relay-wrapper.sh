#!/bin/sh
# Sources /etc/tv-channel-dvbt/dvbt.conf and execs relay_to_hackrf.py with
# the resulting flags. See that conf file's header for why this is a plain
# shell wrapper rather than systemd EnvironmentFile substitution.
set -eu

CONF="${DVBT_CONF:-/etc/tv-channel-dvbt/dvbt.conf}"
if [ ! -r "$CONF" ]; then
    echo "relay-wrapper: cannot read $CONF" >&2
    exit 1
fi
. "$CONF"

set -- \
    --src-addr "${FFPLAYOUT_MULTICAST_ADDR:?FFPLAYOUT_MULTICAST_ADDR not set in $CONF}" \
    --src-port "${FFPLAYOUT_MULTICAST_PORT:?FFPLAYOUT_MULTICAST_PORT not set in $CONF}" \
    --dst-port "${RELAY_LISTEN_PORT:?RELAY_LISTEN_PORT not set in $CONF}" \
    --bandwidth-hz "${BANDWIDTH_HZ:?BANDWIDTH_HZ not set in $CONF}" \
    --packets-per-datagram "${PACKETS_PER_DATAGRAM:-40}"

if [ -n "${TARGET_BITRATE_BPS:-}" ]; then
    set -- "$@" --target-bitrate "$TARGET_BITRATE_BPS"
fi

exec python3 -u /usr/lib/tv-channel-dvbt/relay_to_hackrf.py "$@"
