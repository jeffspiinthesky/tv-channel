#!/usr/bin/env python3
"""Relay ffplayout's multicast MPEG-TS to a local, null-padded, fixed-bitrate
feed that GNU Radio's dvbt_tx_2k_qpsk.grc flowgraph can consume.

Two problems this solves:
  1. GNU Radio's network.udp_source block has no multicast-join support, so
     it can never see udp://239.1.1.1:5000 directly -- this script joins the
     multicast group itself and re-emits on a plain unicast loopback port.
  2. DVB-T needs a *constant* bitrate matching the chosen modulation profile
     -- 2K FFT, QPSK, code rate 1/2, guard interval 1/4. At 8MHz bandwidth
     that's 4.976 Mbit/s per EN 300 744's useful-bitrate table; dropped to
     6MHz (to cut GNU Radio's CPU load enough for the Pi 4 to keep up) it
     scales linearly to ~3.732 Mbit/s (only the sample clock changes between
     bandwidth variants -- FFT size, carrier count and code rate don't).
     ffplayout's actual content stream (~2.81Mbps) falls short of that, so
     this pads the gap with real null TS packets (PID 0x1FFF), paced in
     real time.

(TSDuck's `tsp -P mux` was tried first for the padding step, but its
--inter-packet insertion rate didn't behave predictably when chained -- an
extra stage measurably *reduced* the output rate instead of increasing it.
This does the pacing directly instead: send one real TS packet if one is
buffered, otherwise a null packet, once every packet_interval seconds.)
"""

import argparse
import signal
import socket
import struct
import sys
import time

TS_PACKET_SIZE = 188
TS_SYNC_BYTE = 0x47
NULL_PACKET = bytes([0x47, 0x1F, 0xFF, 0x10]) + bytes([0xFF] * (TS_PACKET_SIZE - 4))
# At 8MHz, GNU Radio's dvbt_reference_signals block only settles into steady,
# non-underrunning operation once each UDP datagram carries enough data --
# bisected 2026-09-19: 7 packets/1316 bytes underruns continuously forever,
# the cliff to "settles after a handful of startup underruns" is at 34-35
# packets/~6.4-6.6KB, and 40 gives real margin above that cliff (confirmed
# clean over repeated 60s+ runs). 6MHz/7MHz never needed this, but a bigger
# batch doesn't hurt them either -- they have far more headroom to begin with.
PACKETS_PER_DATAGRAM = 40  # 40*188 = 7520 bytes -- must match the flowgraph's udp_source payload_size


def resync(buf):
    """Drop leading bytes until buf[0] is a genuine TS sync byte.

    A dropped UDP datagram (confirmed happening in practice -- `netstat -su`
    shows nonzero UDP receive buffer errors) shifts every packet boundary
    that follows it by an arbitrary number of bytes. Without this check, the
    naive fixed-188-byte slicing below just keeps confidently handing GNU
    Radio garbage forever, one lost packet permanently corrupting the whole
    rest of the run instead of just the moment it happened.
    """
    while len(buf) >= 2 * TS_PACKET_SIZE:
        if buf[0] == TS_SYNC_BYTE and buf[TS_PACKET_SIZE] == TS_SYNC_BYTE:
            return 0  # buf[0] checks out as a real packet boundary
        # not aligned -- scan forward for the next byte that looks like one
        try:
            candidate = buf.index(TS_SYNC_BYTE, 1)
        except ValueError:
            del buf[:-1]  # keep just the last byte in case it's a real 0x47
            return -1
        del buf[:candidate]
        if len(buf) < 2 * TS_PACKET_SIZE:
            return -1
    return -1


def open_multicast_source(addr, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind(("", port))
    mreq = struct.pack("4sl", socket.inet_aton(addr), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.setblocking(False)
    return sock


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src-addr", default="239.1.1.1")
    ap.add_argument("--src-port", type=int, default=5000)
    ap.add_argument("--dst-port", type=int, default=6000)
    ap.add_argument("--target-bitrate", type=float, default=3_732_000,
                     help="EN 300 744 useful bitrate for the chosen DVB-T profile (bps)")
    args = ap.parse_args()

    # Backgrounding this script with `&` inside a non-interactive shell (as
    # start_hackrf.sh does) makes bash set SIGINT/SIGQUIT to be ignored for
    # it -- without an explicit handler here, `kill -INT` on this process is
    # a silent no-op and it runs forever.
    def _exit(signum, frame):
        sys.exit(0)
    signal.signal(signal.SIGINT, _exit)
    signal.signal(signal.SIGTERM, _exit)

    in_sock = open_multicast_source(args.src_addr, args.src_port)
    out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dst = ("127.0.0.1", args.dst_port)

    packet_interval = (TS_PACKET_SIZE * 8) / args.target_bitrate
    buf = bytearray()
    batch = bytearray()
    real_count = 0
    null_count = 0
    resync_count = 0
    last_report = time.monotonic()
    next_send_time = time.monotonic()

    print(f"Relaying {args.src_addr}:{args.src_port} -> 127.0.0.1:{args.dst_port} "
          f"at {args.target_bitrate:.0f} bps ({packet_interval * 1e6:.1f}us/packet)")

    while True:
        try:
            while True:
                data, _ = in_sock.recvfrom(65536)
                buf.extend(data)
        except BlockingIOError:
            pass

        now = time.monotonic()
        if now < next_send_time:
            time.sleep(next_send_time - now)

        if len(buf) >= TS_PACKET_SIZE:
            if buf[0] != TS_SYNC_BYTE:
                resync(buf)
                resync_count += 1

        if len(buf) >= TS_PACKET_SIZE and buf[0] == TS_SYNC_BYTE:
            packet = bytes(buf[:TS_PACKET_SIZE])
            del buf[:TS_PACKET_SIZE]
            real_count += 1
        else:
            packet = NULL_PACKET
            null_count += 1

        batch.extend(packet)
        if len(batch) >= PACKETS_PER_DATAGRAM * TS_PACKET_SIZE:
            out_sock.sendto(bytes(batch), dst)
            batch.clear()

        next_send_time += packet_interval

        if now - last_report >= 5:
            total = real_count + null_count
            null_pct = (null_count / total * 100) if total else 0
            print(f"  {total} packets sent, {null_pct:.1f}% null, "
                  f"{resync_count} resyncs "
                  f"(buffered backlog: {len(buf)} bytes)")
            real_count = null_count = 0
            resync_count = 0
            last_report = now


if __name__ == "__main__":
    main()
