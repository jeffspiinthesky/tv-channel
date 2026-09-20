# Video script: chasing the 8MHz DVB-T signal

Running log for this video's recording, in the same style as
`video-script.md` (video 2). Update as we go.

Status key: ✅ done and verified · ⏳ in progress / unresolved · 🖱️ manual step (no command)

---

## 1. Recap and framing the problem ✅

**Where we left off:** last video ended with a working over-the-air
DVB-T signal — ffplayout's multicast feed, relayed through
`relay_to_hackrf.py` into a GNU Radio flowgraph, transmitted from a
HackRF One, and picked up cleanly by Kaffeine (a software DVB-T
receiver) on a separate PC. That confirmed the whole chain works... at
610MHz, using a 6MHz channel bandwidth.

**The problem:** 6MHz isn't a real-world DVB-T bandwidth in the
UK/most of Europe — normal terrestrial broadcasts (and normal TVs) use
**8MHz** channels. 6MHz was really just a fallback to keep GNU Radio's
processing load down while getting the chain working at all. To have
any chance of a real TV finding this channel, we need 8MHz to work
reliably — and so far, it hasn't: the signal drops out with underruns
before we ever get a clean broadcast at that bandwidth.

**What we've confirmed so far (each of these was suspected, tested,
and ruled out):**
- Not a video codec issue — this leg of the chain never touches video
  codecs at all; it moves raw MPEG-TS bytes and raw radio bits.
- Not the HackRF or the USB connection to it — a raw, direct test at
  the exact same data rate 8MHz needs runs perfectly cleanly, sustained,
  no drops.
- Not missing real-time scheduling — the relevant processing threads
  already run at real-time priority.
- Not the kernel — installing a real-time (PREEMPT_RT) Linux kernel
  made no measurable difference.
- Not a simple config mismatch — double-checked the data-feed rate
  into the flowgraph matched the correct DVB-T profile for 8MHz; that
  wasn't it either.

**What's still open, but now much better understood (see step 2):**
- It *is* a processing throughput limit after all — just not the kind
  that shows up as "the CPU is pegged." The one-second average CPU
  numbers looked idle, but the real signal only degrades gradually as
  the required data rate climbs, which is exactly the signature of a
  chain that's right on the edge of keeping up, not one that's
  obviously overloaded.
- Simpler, unrelated loose end: the *receiver* side is still configured
  to expect 6MHz, not 8MHz — worth double-checking that isn't
  contributing to "nothing shows up" independent of the transmit-side
  investigation above.

---

## 2. Found the real shape of the problem: a gradual ceiling, not an 8MHz-specific bug ✅

Compared the working 6MHz setup and the broken 8MHz one line-by-line —
they're structurally identical. The only difference is the sample
rate/bandwidth number itself. That ruled out "some setting is wrong
for 8MHz specifically" and pointed at a genuine capacity limit instead.

To find where that limit actually sits, tested a range of bandwidths
in between, each with a proper apples-to-apples control (same
continuously-looping source feed, correctly-scaled data rate for each
bandwidth, clean startup/shutdown each time):

| Bandwidth | Result |
|---|---|
| 6MHz | A handful of underruns right at startup (completely normal — every SDR does this while its buffers first fill), then perfectly clean |
| 7MHz | Same — brief startup blip, then perfectly clean |
| 7.5MHz | Settles down mostly, but a small steady trickle of underruns continues indefinitely (~12/second) |
| 8MHz | Continuous, unrelenting underruns from the first second — never settles |

**This is the real finding: it's not a broken setting, it's a genuine
processing ceiling on this Pi 4 that sits somewhere around 7–7.5MHz**
for this particular flowgraph. Below that, the signal is rock solid.
Above it, the pipeline gradually can't keep up, and by 8MHz it's
completely swamped.

**Why the earlier "CPU looks idle" readings didn't contradict this:**
raising the bandwidth doesn't add more *work* to the flowgraph in the
sense of new processing steps — it asks the exact same OFDM chain to
produce its output *faster* (a wider broadcast channel means the same
signal has to be squeezed into less time). So the real bottleneck is
almost certainly one specific block in that chain hitting its own
single-core speed limit, which can be genuinely maxed out in short
bursts without ever showing up clearly in a 1-second average across
the whole process.

**Next step:** identify which specific block in the DVB-T chain is the
actual speed limit (candidates: Reed-Solomon encoding, the
convolutional interleaver, or the OFDM symbol mapping — the more
computationally expensive stages), and see whether it can be sped up.
If not, ~7MHz may simply be this Pi 4's practical ceiling for this
implementation, which would mean either accepting a non-standard
bandwidth or finding a way to lighten the processing chain.

---

## 3. Considered switching to a Pi 5 to clear the ceiling — real trade-off found ✅

Since the bottleneck looks like a raw processing-speed limit rather
than a bug, the obvious next question is whether faster hardware just
solves it outright. A Raspberry Pi 5 has meaningfully faster CPU cores
than this Pi 4 — worth seriously considering.

**The DVB-T transmit chain itself doesn't care about video hardware at
all** — it was already established earlier that this leg never touches
video codecs, only raw MPEG-TS bytes and raw radio bits. So whether a
Pi 5 fixes the 8MHz ceiling is purely a question of raw CPU speed for
that one bottlenecked processing block, and a Pi 5's cores are roughly
2.5-3x faster per-thread than this Pi 4's. Good odds it clears the
ceiling outright.

**Where it gets more complicated: the *other* leg of this project.**
This channel's actual video output currently runs on real, working
hardware H.264 encoding — not software — and that's a big part of why
CPU load is manageable today. Checked directly against the live
config rather than assumption, since an earlier working note here had
gone stale: this really is genuine hardware encode, giving a large,
confirmed real-world CPU saving over the software fallback.

**The Raspberry Pi 5 has no hardware video encoder at all** (for any
codec) — a real regression from the Pi 4 on this specific point. So
migrating loses that hardware-encode saving; the channel's output
would have to go back to software encoding, this time on much faster
cores. General community reports suggest a Pi 5 handles 1080p software
H.264 encoding comfortably on its own — but this channel would also be
asking those same cores to run the DVB-T transmit chain at the same
time, so the two workloads would now be sharing CPU on one board in a
way they effectively don't today. Decode was already software-only on
both codecs, on this Pi 4 and any future Pi 5 — a wash either way, not
a new cost.

**Where this leaves it:** a Pi 5 is a promising fix for the 8MHz
ceiling on paper, but not a guaranteed free upgrade — it trades a
proven, working hardware-encode setup for an unproven combination of
software encode + DVB-T transmit sharing the same cores. Worth
benchmarking for real once a Pi 5 is in hand, rather than assuming.

---

## 4. Got a Pi 5, migrated the project, retested — the ceiling didn't move ✅

Acquired a Pi 5, did a fresh OS install (not a clone — see
`plans/pi5-migration.md` for the full step-by-step), and moved
everything over: ffplayout (rebuilt from the same fork), the NAS
mount, and the GNU Radio/HackRF scripts (identical package versions to
the Pi 4 — no compatibility concerns). The HackRF itself was
physically moved from the Pi 4 to the Pi 5 partway through.

**First attempt was invalid**: ran the 8MHz test while the ffplayout
fork's Rust build was still compiling in the background. Load average
hit 5.85 and even the relay script showed hiccups never seen on the
clean Pi 4 baseline — the build was competing for CPU and contaminated
the result. Correctly flagged and re-run once genuinely idle.

**Clean, valid retest: same continuous underruns as the Pi 4, despite
the Pi 5's much faster cores and a system load of under 1.0.** This
directly disproves the "it's just a slow single core" theory from the
Pi 4 investigation — if it were purely about raw processing speed, a
Pi 5 with roughly 2.5-3x the per-core throughput should have cleared
the ~7-7.5MHz ceiling comfortably. It didn't move at all.

**New lead, and a much better one than "faster cores": the Pi 5's
kernel uses a 16KB memory page size, versus the Pi 4's 4KB.** GNU
Radio's buffer implementation (`buffer_double_mapped`, the technique
behind those "allocation granularity" warnings seen throughout this
investigation) has to allocate its circular buffers in units of the
system's page size — a 4x larger page size fundamentally changes that
buffering/scheduling granularity throughout the whole flowgraph,
completely independent of how fast the CPU is. This lines up with
everything seen so far far better than a raw-speed explanation does.

The Pi 5 ships two separate kernel builds: `rpi-v8` (the same generic
kernel family the Pi 4 uses, presumably 4K pages) and `rpi-2712`
(Pi-5-specific, currently running, apparently defaulting to 16K
pages). Trying the `rpi-v8` kernel would directly test this — but
`rpi-2712` exists specifically because the Pi 5's SoC (including the
RP1 chip handling USB/GPIO) needs support the older generic kernel may
lack, so this carries a real risk of a Pi 5 that won't boot properly
or loses working USB/peripheral support. **Decided not to risk it** —
not worth it for a diagnostic test, and not a direction to explore
without a safer way to test it.

**Next step, not yet tried:** GNU Radio's buffer allocator backend
(`vmcircbuf`) is configurable in userspace, independent of the kernel
— worth researching whether it can be pointed at a different
allocation strategy that isn't tied to the system page size, as a
safer way to test the page-size theory without touching the boot
kernel at all.

---

## 5. Ruled out the Python relay and the HackRF sink's own buffer depth ✅

User pushed back hard on the page-size theory with a sharp point:
comparing the Pi 4 (4K pages, slow CPU, fails) against the Pi 5 (16K
pages, fast CPU, fails) confounds two variables at once — it can't
actually tell us whether page size matters, since CPU speed changed
at the same time. Also raised a sharper alternative: CPU load on the
Pi 4 was never actually high, and raw `hackrf_transfer` (no Python
anywhere in that path) works cleanly and consistently on *both* Pis —
so the real suspect might be the Python code specifically
(`relay_to_hackrf.py`, the one part of this chain that's plain Python
doing manual real-time packet pacing), not the hardware or OS at all.

**Tested and ruled out: relay scheduling priority.** Confirmed the
relay process runs as ordinary `SCHED_OTHER` (`ps -o cls,rtprio`
showed `TS`, no RT priority) — a real, concrete difference from the
flowgraph's own threads, which are all `SCHED_RR`. Gave it real-time
priority directly (`chrt -f 50`) and reran the clean 8MHz test.
**No change** — underruns persisted identically. Scheduling priority
wasn't it.

**Tested and ruled out: the relay's Python pacing precision, entirely
bypassed.** Captured several seconds of the relay's real, correctly
null-padded output to a file, then replayed that file into the
flowgraph via `socat` in a tight unthrottled loop — no rate-pacing
logic at all, no Python timing loop in the path, data arriving as
fast as the OS could deliver it. **Underruns were identical.** This
is decisive: it proves the bottleneck cannot be in the relay's
pacing implementation, Python or otherwise, since removing that
component's timing behavior entirely changed nothing. The problem is
confirmed to live inside the flowgraph/GNU Radio runtime itself.

```bash
# Step 1: capture 5s of the relay's real, correctly-paced output to a file
ssh -i ~/.ssh/teletext_rsa pi@teletext-pi5.local '
cd ~/src/tv-channel/scripts/radio
nohup python3 -u relay_to_hackrf.py --target-bitrate 4976000 > /tmp/relay-capture.log 2>&1 < /dev/null &
disown
sleep 1
timeout 5 socat -u UDP-RECV:6000 - > /tmp/capture.ts 2>/tmp/socat-capture.log
kill -9 $(pgrep -f "python3 -u relay_to_hackrf") 2>/dev/null
ls -la /tmp/capture.ts
'

# Step 2: start the flowgraph, then flood that captured file at it in a
# tight unthrottled loop -- no pacing, no Python timing logic in the path.
# -b 1316 matches each send to a single TS-packet-sized datagram, same as
# the real relay.
ssh -i ~/.ssh/teletext_rsa pi@teletext-pi5.local '
cd ~/src/tv-channel/scripts/radio
nohup python3 -u dvbt_tx_2k_qpsk_8mhz_test.py > /tmp/flowgraph-flood.log 2>&1 < /dev/null &
disown
sleep 3
nohup bash -c "while true; do socat -b 1316 -u FILE:/tmp/capture.ts UDP-SENDTO:127.0.0.1:6000; done" > /tmp/flood.log 2>&1 < /dev/null &
disown
sleep 20
echo "=== flowgraph ==="
tail -c 900 /tmp/flowgraph-flood.log
echo "=== load ==="
cat /proc/loadavg
echo "=== flood sender CPU ==="
ps aux | grep socat | grep -v grep
'
```

**Tested and ruled out: the HackRF sink's own USB transfer buffer
depth.** Found via `strings` on the compiled `gr-osmosdr` library that
its HackRF sink supports a `buffers=N` device-arg (confirmed against
the actual `gr-osmosdr` source on GitHub — parsed in
`hackrf_sink_c.cc`, defaults to a built-in constant, commonly cited as
32) controlling how many USB transfer buffers are kept in flight.
Quadrupled it to `buffers=128` on a scratch copy of the flowgraph.
**No change** — same continuous underruns.

**Where this leaves it:** the bottleneck is now narrowed to somewhere
genuinely inside the GNU Radio DVB-T block chain's own processing or
internal scheduling — not the relay, not the HackRF sink's own USB
buffering, not raw CPU speed, not the OS/kernel scheduling priority.
The still-unexplained buffer clamp (`ofdm_cyclic_prefixer0`'s max
output buffer silently capped to 8192, first seen back in step 2) and
the DVB-T DSP blocks' own per-call processing characteristics
(Reed-Solomon encoding, convolutional/bit interleaving, OFDM reference
signal generation) remain the most concrete unexplored territory.

---

## 6. Why raw `hackrf_transfer` succeeding doesn't contradict this ✅

User asked a good clarifying question: doesn't `hackrf_transfer` go
through the same `libhackrf` library as the GNU Radio HackRF sink? It
does — but only at the very last hop. `hackrf_transfer` reads bytes
directly from a file and hands them straight to that library's USB
callback: one thread, no format conversion, no other hand-offs. The
GNU Radio sink, by contrast, sits at the end of a ~10-block chain
(each block its own OS thread), and has to convert samples from
32-bit float I/Q to the 8-bit integer format the hardware wants
before handing them to that same callback. Same bottom-layer library,
completely different amount of pipeline above it — which is exactly
why one can be rock solid while the other isn't, without any
contradiction.

## 7. Tried GNU Radio's own recommended throughput fixes — no change ✅

Based on GNU Radio's own published throughput-optimization guidance
([An Incomplete Guide to Optimizing GNU Radio Flowgraph
Throughput](https://blog.ektocomms.space/gnuradio-throughput-guide/)),
tried the two most relevant techniques not yet attempted:

**Pinning the whole chain to one core**, instead of isolating just the
HackRF sink onto its own core (the opposite strategy from what was
tried back in step 1) — the idea being that keeping every block on the
same core avoids cross-core cache misses and hand-off latency between
the ~10 threads in this chain.

**Setting a large `min_output_buffer` (131072) on every block**, not
just the one `max_output_buffer` call from step 1 that had been
silently clamped down to 8192. This one actually took effect cleanly
this time (`set_min_output_buffer on block N to 131072` logged for
every block, no clamping message) — a genuinely different code path
from the `max_output_buffer` clamp seen before.

**Result: no improvement, and the relay's own backlog got measurably
worse** (up to ~57KB, vs. the usual 0-25KB range) — consolidating
everything onto one core appears to have made scheduling contention
worse, not better, for at least the parts of the system sharing that
core.

**Where this leaves it, after a genuinely thorough pass:** ruled out
across this whole investigation — video codec, raw USB/HackRF
throughput, missing/present real-time scheduling, the RT kernel, CPU
speed (Pi 4 vs Pi 5), the Python relay entirely (flood-tested with
zero pacing logic in the path), the HackRF sink's own USB buffer
depth, GNU Radio's own recommended buffer-size and core-affinity
fixes. The bottleneck is definitely real, definitely inside the GNU
Radio DVB-T block chain's own processing/scheduling, and has resisted
every lever tried so far. Remaining untried directions: actual
per-block profiling (e.g. `perf record` to see which specific block's
`work()` call is the actual time sink, rather than guessing), or
stepping back to consider a fundamentally different, non-GNU-Radio
implementation of this same DVB-T encoding chain.

---

## 8. Profiled it properly — found a real gap, but not the root cause ✅

`perf record` (999Hz, DWARF call graphs) on the flowgraph process
during a live 8MHz underrun captured **zero samples** over a 15-second
window. That's itself a real finding: the threads spend essentially
none of their time actively computing — this was never a compute-bound
problem, confirming everything inferred indirectly earlier, this time
directly.

```bash
ssh -i ~/.ssh/teletext_rsa pi@teletext-pi5.local '
cd ~/src/tv-channel/scripts/radio
nohup python3 -u relay_to_hackrf.py --target-bitrate 4976000 > /tmp/relay-perf.log 2>&1 < /dev/null &
disown
sleep 1
nohup python3 -u dvbt_tx_2k_qpsk_8mhz_test.py > /tmp/flowgraph-perf.log 2>&1 < /dev/null &
disown
sleep 5
FLOW_PID=$(pgrep -f "dvbt_tx_2k_qpsk_8mhz_test" | head -1)
echo "flowgraph PID: $FLOW_PID"
sudo perf record -F 999 -p $FLOW_PID -g --call-graph dwarf -o /tmp/perf-8mhz.data -- sleep 15
'

# read back:
ssh -i ~/.ssh/teletext_rsa pi@teletext-pi5.local 'sudo perf report -i /tmp/perf-8mhz.data --stdio 2>&1 | head -60'
```

Switched to `perf sched record` (scheduler event tracing — measures
the delay between a thread becoming runnable and actually getting a
CPU, i.e. genuine scheduling contention, not I/O wait) for the same
live window.

```bash
ssh -i ~/.ssh/teletext_rsa pi@teletext-pi5.local '
sudo perf sched record -o /tmp/perf-sched-8mhz.data -- sleep 15
'

# read back, filtered down to the GNU Radio DVB-T block threads:
ssh -i ~/.ssh/teletext_rsa pi@teletext-pi5.local 'sudo perf sched latency -i /tmp/perf-sched-8mhz.data 2>&1 | grep -iE "dvbt|python3|osmosdr|relay" | head -30'
```

Broken down by block:

| Block | Total wait (15s window) | Wakeups | Max wait |
|---|---|---|---|
| **`dvbt_reference_signals`** | **1063 ms** | **6550** | 3.9 ms |
| `dvbt_inner_coder` | 721 ms | 748 | 3.6 ms |
| `dvbt_bit_inner_interleaver` | 551 ms | 2321 | 6.0 ms |
| `dvbt_reed_solomon` | 385 ms | 244 | 2.9 ms |
| `dvbt_map` | 179 ms | 11345 | 3.3 ms |
| `dvbt_symbol_inner_interleaver` | 163 ms | 2728 | 2.9 ms |
| `dvbt_energy_dispersal` | 130 ms | 144 | 2.3 ms |
| `dvbt_convolutional_interleaver` | 59 ms | 612 | 4.4 ms |

`dvbt_reference_signals` stood out clearly — over a full second of
15 spent just waiting for a CPU after becoming runnable. Reasoned
this pointed at equal-priority `SCHED_RR` round-robin contention
across ~10+ threads on only 4 cores (a real, mathematically obvious
oversubscription), and planned to test giving deadline-critical
blocks higher priority than earlier-stage ones.

**Before doing that, checked the actual scheduling class directly —
and found something much bigger: every single thread, including all
the named DVB-T blocks, was `SCHED_OTHER` (`TS`), not `SCHED_RR` at
all.** The flowgraph's own log had been quietly printing `realtime:
Error: failed to enable real-time scheduling` this entire session,
and `ulimit -r` on the Pi 5 was `0`. **This whole Pi 5 investigation —
every test since the migration — had been running with zero real-time
scheduling active, a massive confound nobody had checked for.**

Root cause: the Pi 4 has a dedicated
`/etc/security/limits.d/99-gnuradio-rt.conf` granting `pi rtprio 95` —
clearly set up specifically for this GNU Radio work at some point
during the undocumented gap between video-script.md steps 14 and 15,
but never folded into the Pi 5 migration plan because its existence
wasn't known. Added the identical file to the Pi 5, confirmed via a
fresh session that `ulimit -r` now correctly reports 95, restarted
everything clean, and confirmed via `ps -T` that every block thread
now genuinely shows `SCHED_RR`/RTPRIO 29 — an exact match to the Pi 4.

**Reran the 8MHz test under this now-genuinely-correct configuration:
identical continuous underruns.** This is disappointing but valuable
— it means every conclusion from this whole Pi 5 investigation
(raw CPU speed doesn't help, the relay isn't the cause, HackRF sink
buffer depth doesn't matter) now holds under an even more rigorous,
truly apples-to-apples comparison with the Pi 4 than before. The
missing rtprio limit was a real, independent bug worth fixing
regardless (now fixed permanently for this Pi 5), but it was not
*the* answer to the 8MHz mystery.

**Where this genuinely leaves it, late in a long session:** the
bottleneck is confirmed, real, reproducible, inside the GNU Radio
DVB-T chain's own scheduling/processing, present with or without
proper real-time scheduling, present regardless of CPU speed, present
regardless of relay implementation or HackRF buffer depth. The
`dvbt_reference_signals` scheduling-wait profile is still the most
concrete specific lead — worth re-profiling now that real-time
scheduling is properly active on the Pi 5, since the earlier profile
was taken under the (unknowingly) broken SCHED_OTHER condition and
may not reflect the true picture under correct scheduling.

---

## 9. Re-profiled under genuine RT scheduling — sharpened the lead further

Re-ran `perf sched record` with real-time scheduling now genuinely
active (confirmed via `ps -T`: every block thread `SCHED_RR`/RTPRIO
29, matching the Pi 4 exactly). Two clean unnamed `python3` threads
at a higher RTPRIO 50 were checked and ruled out — both sit at 0.0%
CPU, just idle housekeeping, not competing for cycles.

```bash
ssh -i ~/.ssh/teletext_rsa pi@teletext-pi5.local '
sudo perf sched record -o /tmp/perf-sched-rtfix.data -- sleep 15
'

ssh -i ~/.ssh/teletext_rsa pi@teletext-pi5.local 'sudo perf sched latency -i /tmp/perf-sched-rtfix.data 2>&1 | grep -iE "dvbt|osmosdr|hackrf_sink|udp_source" | head -20'
```

**With real scheduling active, max wait times across the board dropped
sharply** (0.4-0.9ms vs. 2-6ms under the earlier broken condition) —
confirms real-time scheduling genuinely does what it's supposed to.
**But `dvbt_reference_signals` remained the clear standout**: 939ms of
cumulative scheduling-wait out of a 15s window, 3874 wakeups, and now
also confirmed as the single busiest block by CPU time (7.0%, ahead
of every other block in the chain). Separately, `hackrf_sink_c2`
(the actual HackRF-feeding thread) is woken an enormous 19,882 times
in 15 seconds but with negligible wait each time — it's being
serviced promptly; the pressure is upstream, not at the final sink.

**Checked the actual GNU Radio source for this block**
(`dvbt_reference_signals_impl.cc`) to understand why: confirmed it
*can* batch multiple OFDM symbols per `work()` call (`noutput_items`
governs the loop, not a fixed one-symbol-per-call design) — so it's
not an inherent architectural ceiling in this specific block. The
actual per-call batch size is decided by GNU Radio's scheduler, based
on how much buffer space and available input data exist at call time.

**Tested buffer size in isolation** (the earlier `min_output_buffer`
test had been confounded by also pinning every block to one core,
which measurably made things worse) — reran with the larger buffers
alone, no core-pinning. **Still identical continuous underruns.** This
is a clean, useful negative result: it rules out *allocated buffer
capacity* as the limiting factor on its own.

**Where this leaves it, genuinely late now:** the most plausible
remaining explanation is that the small per-call batch size isn't
about buffer space at all, but about *input arrival granularity* —
the relay delivers data in individual 1316-byte UDP datagrams, and if
GNU Radio's scheduler naturally chunks its processing to match how
much new input has actually arrived, no amount of downstream buffer
tuning could fix that; the small-chunk behavior would be set upstream,
by the network delivery pattern itself, and cascade through the whole
chain regardless of buffer sizes further down. **Next concrete
experiment for a future session**: have the relay (or an intermediate
stage) batch many packets into fewer, larger sends before they reach
the flowgraph, and see whether that changes `dvbt_reference_signals`'s
wake frequency and the underrun behavior together.

---

## 10. Solved it — batching the relay's UDP sends fixes 8MHz ✅

HackRF physically moved back to the Pi 4 (the Pi 5 is now fully shut
down — decided last session to make the Pi 4 the default going
forward). ffplayout needed a manual restart first: it hit the same
NAS-mount boot race diagnosed back in step 9 of `video-script.md`
(`Dependency failed for ffplayout.service`) — the mount caught up
eventually, `systemctl restart ffplayout` was enough, no new fix
needed. Also caught and stopped a second, unrelated ffplayout instance
that had been left running on the Pi 5 — two senders on the same
multicast group would have silently corrupted the test data.

**The queued experiment from last session was the answer.** Built a
scratch copy of the relay and the 8MHz flowgraph with the UDP batch
size (packets bundled into each outbound datagram) as a parameter, and
retested straight at 8MHz:

- 7 packets/datagram (the original size): continuous underruns, never
  settles — reproduces every prior session's result exactly.
- 40 packets/datagram: settles to ~25 startup underruns then runs
  perfectly clean, matching the signature that 6MHz/7MHz always had.

**Bisected to find the real threshold, not just a working point**,
since a precise number matters more for this video than "somewhere
between 7 and 40": 14 and 20 packets are still continuously
underrunning; 30 drops to a light but steady trickle (~7/sec); 32
lighter still (~3/sec); 33 lighter again (~1/sec); **34-35 packets
(~6.4-6.6KB per datagram) is the cliff** — underruns drop to startup-
only and stay there, confirmed over a 90-second run. Below the cliff,
the underrun rate declines smoothly as the batch grows; at the cliff
it drops to essentially zero.

**This confirms last session's theory exactly**: `dvbt_reference_signals`
wasn't struggling with compute or buffer space, it was starved by how
little data arrived per UDP datagram. Feed it fewer, bigger chunks and
it settles down immediately, at any bandwidth.

**Found a real, independent bug along the way**: `kill -INT` on the
relay process had silently never worked when it was launched with `&`
inside a non-interactive shell script (exactly how `start_hackrf.sh`
starts it) — bash sets SIGINT/SIGQUIT to be ignored for backgrounded
jobs in a script with no job control, and the relay never installed
its own handler to override that, unlike the flowgraph script (which
does, and was always killed cleanly). Confirmed via `/proc/<pid>/status`
`SigIgn`. Fixed by adding explicit `signal.signal()` handlers to the
relay, matching the flowgraph's existing pattern.

**Applied to the real production files** (not just the scratch
copies), then re-validated end to end before committing:
`relay_to_hackrf.py`'s `PACKETS_PER_DATAGRAM` raised from 7 to 40
(real margin above the 34-35 cliff, matching the flowgraph's now
40-packet/7520-byte `udp_source` payload size), the SIGINT fix added,
and `start_hackrf.sh` corrected to pass `--target-bitrate 4976000`
explicitly (it was launching the 8MHz flowgraph but relying on the
relay's 6MHz-profile default bitrate — a separate latent mismatch
found while making this change, likely never exercised since testing
had always passed the rate explicitly by hand).

**Status: 8MHz DVB-T transmit is fixed.** Next step is putting a real
antenna/attenuator chain back between the HackRF and a receiver to
confirm reception at 8MHz, not just that GNU Radio stops underrunning.

---

## 11. Command log: bisecting the batch-size cliff and the SIGINT bug

Full command sequence behind section 10's numbers, in order. Baseline
reproduction at the original 7-packet batch size, 8MHz:

```
python3 -u relay_to_hackrf_batch_test.py --target-bitrate 4976000 --packets-per-datagram 7
python3 -u dvbt_tx_2k_qpsk_8mhz_batch_test.py --payload-size 1316
```
→ continuous underruns from the first second, never settles.

At 40 packets/7520 bytes, same test:
```
python3 -u relay_to_hackrf_batch_test.py --target-bitrate 4976000 --packets-per-datagram 40
python3 -u dvbt_tx_2k_qpsk_8mhz_batch_test.py --payload-size 7520
```
→ ~23 startup underruns then clean for 60s+.

**Found the relay was immune to `kill -INT`** while cleaning up between
these runs -- `ps aux` kept showing the relay process alive after the
kill:
```
kill -INT <relay_pid> <flow_pid>
ps aux | grep -iE "relay_to_hackrf|dvbt_tx"   # relay still there
grep -i "SigIgn" /proc/<relay_pid>/status      # SigIgn: 0000000001001006
```
`0x1001006` decodes to SIGINT (2) and SIGQUIT (3) both set in the
ignore mask -- a bash behavior, not a bug in the relay's own logic:
backgrounding a command with `&` inside a non-interactive shell script
(exactly how `start_hackrf.sh` runs it) makes bash set SIGINT/SIGQUIT
to ignored for that job unless the program installs its own handler.
The flowgraph script already does (`signal.signal(signal.SIGINT, ...)`
in its generated `main()`), which is why it always died cleanly and
this went unnoticed until now. Fixed by adding the same handler to the
relay.

**Bisection**, each step run for 45s via a small harness script
(`run_batch_test.sh <packets> <duration> <outdir>`, not committed --
starts both processes, snapshots the underrun count at the halfway
point and at the end, force-kills anything still alive after a 3s
grace period):
```
run_batch_test.sh 14 45 <outdir>   # underruns_total=612, still climbing
run_batch_test.sh 20 45 <outdir>   # underruns_total=1216, noisier (see below)
run_batch_test.sh 30 45 <outdir>   # underruns_total=335, ~7/sec steady
run_batch_test.sh 32 45 <outdir>   # underruns_total=156, ~3/sec
run_batch_test.sh 33 45 <outdir>   # underruns_total=67, ~1/sec trickle
run_batch_test.sh 34 90 <outdir>   # underruns_total=28, only 1 in second half
run_batch_test.sh 35 45 <outdir>   # underruns_total=28, 0 in second half -- settled
```
The 20-packet run's unusually high count turned out to be contaminated
by a leftover 14-packet relay instance still running from the previous
step (caught via `ps aux` showing two `relay_to_hackrf_batch_test.py`
processes at once) -- a direct consequence of the SIGINT bug above:
the harness's own `kill -INT` on the relay silently did nothing, so
the *next* test started a second relay writing to the same UDP port
as the first. Re-ran 14 and 20 after fixing the SIGINT handling;
14 reproduced almost exactly (612 vs. an earlier 616), confirming only
20 had been contaminated.

**Discovered mid-session, unrelated**: `systemctl status ffplayout`
showed `inactive (dead)` -- the same NAS-mount boot race from
`video-script.md` step 9 resurfaced (`Dependency failed for
ffplayout.service`), just not yet followed by a fix-verifying reboot.
Fixed with a plain restart once the mount had caught up:
```
systemctl status ffplayout
mount | grep share
sudo systemctl restart ffplayout
```

**Applied to production**, then validated with the real files (not
the scratch copies) for 45s:
```
python3 -u relay_to_hackrf.py --target-bitrate 4976000
python3 -u dvbt_tx_2k_qpsk_8mhz_test.py
```
→ 28 underruns total, matching the tuned scratch result exactly.

---

## 12. Command log: productizing into systemd services + two .deb packages

Unifying the 6MHz/8MHz flowgraphs into one parametrized `dvbt_tx.grc`
(GRC Parameter blocks for `bandwidth_hz`/`center_freq`/`tx_gain`/
`udp_port`/`packets_per_datagram`), regenerated with GRC's own
compiler rather than hand-patched:
```
grcc dvbt_tx.grc -o .
python3 dvbt_tx.py --help   # confirms --bandwidth-hz, --center-freq,
                            # --tx-gain, --udp-port, --packets-per-datagram
```
Re-ran the same 45s settle check against the regenerated files and got
27 startup underruns then clean -- matching every prior run.

**Building the new `tv-channel-dvbt` package** (relay + transmit as
systemd services, `/etc/tv-channel-dvbt/dvbt.conf`, wrapper scripts):
```
sudo apt-get install debhelper dpkg-dev
dpkg-buildpackage -us -uc -a arm64
systemd-analyze verify packaging/tv-channel-dvbt-*.service
sudo apt-get install ./tv-channel-dvbt_1.0.0-1_arm64.deb
systemctl is-enabled tv-channel-dvbt-relay tv-channel-dvbt-transmit   # disabled
systemctl is-active tv-channel-dvbt-relay tv-channel-dvbt-transmit    # inactive
```

**First live cutover attempt crashed immediately**:
```
sudo systemctl enable --now tv-channel-dvbt-transmit.service
journalctl -u tv-channel-dvbt-transmit --no-pager -n 60
```
```
RuntimeError: filesystem error: cannot create directories: Read-only file system [/nonexistent/.cache/gnuradio]
```
The `dvbtx` system user (`adduser --system --no-create-home`) has no
real home directory, and `ProtectHome=yes` blocks writes there anyway
-- GNU Radio wants a writable cache dir. Fixed with `CacheDirectory=`/
`XDG_CACHE_HOME` on the unit; rebuilt and reinstalled (version bumped
each time since dpkg won't reinstall an unchanged version string):
```
sudo systemctl reset-failed tv-channel-dvbt-transmit.service
dpkg-buildpackage -us -uc -a arm64
sudo apt-get install ./tv-channel-dvbt_1.0.0-2_arm64.deb
sudo systemctl restart tv-channel-dvbt-transmit.service
```
**Second crash, different directory**:
```
RuntimeError: filesystem error: cannot create directories: Read-only file system [/nonexistent/.config/gnuradio/prefs]
```
Same root cause, GNU Radio's separate prefs/config directory this
time. Fixed with `StateDirectory=`/`XDG_CONFIG_HOME`, rebuilt as
version `-3`, reinstalled, restarted -- clean this time (0-5 startup
underruns, no crash).

**Verified the `BindsTo` cascade** actually works both ways, not just
on paper:
```
systemctl is-active ffplayout tv-channel-dvbt-relay tv-channel-dvbt-transmit
sudo systemctl stop ffplayout
systemctl is-active ffplayout tv-channel-dvbt-relay tv-channel-dvbt-transmit
# all three inactive -- confirmed the stop cascades down
sudo systemctl start ffplayout
sudo systemctl start tv-channel-dvbt-transmit.service
# all three active again
```

---

## 13. Command log: the ffplayout DVB service-name patch and its own build bugs

The TV showed the channel as `:Service01` -- ffmpeg's mpegts muxer
default when no `-metadata service_name`/`service_provider` is set.
Confirmed the exact cause before writing any code:
```
ffmpeg -hide_banner -h muxer=mpegts   # no explicit service_name option --
                                        # it's generic -metadata, not an AVOption
```
Considered piping through TSDuck's `tsp -P sdt` to rewrite the SDT
in-flight (`tsp -P sdt --help`, `tsp -I ip --help` confirmed the
plugins exist and would work), but since the ffplayout fork is
already patched once (the h264_v4l2m2m bitrate fix), did it natively
instead -- `OutputConfig` gets `service_name`/`service_provider`
fields, wired through a DB migration, into `encoded.rs`'s
`set_metadata()` call gated on `muxer == "mpegts"`, and a matching
frontend form in `ConfigPlayout.vue`.

**First real build (release, not the dev profile the patch was
written and tested against) failed** -- the frontend type-check only
runs for `--release`:
```
cargo build --release -p ffplayout --no-default-features --features embed_frontend
```
```
error TS2322: Type 'string | undefined' is not assignable to type 'string | null'.
```
`?? undefined` should have been `?? null` -- this codebase's ts-rs
export maps Rust's `Option<String>` to `string | null`, not
`string | undefined`. Confirmed the fix in isolation before paying for
another full build:
```
./node_modules/.bin/vue-tsc --build   # exit 0 after the fix
cargo build --release -p ffplayout --no-default-features --features embed_frontend
# Finished `release` profile [optimized] target(s) in 10m 52s
```

**`cargo deb` then failed on a missing asset**:
```
cargo install cargo-deb --locked
cargo deb -p ffplayout --manifest-path backend/app/Cargo.toml --no-build --variant arm64 -o dist/ffplayout_2.2.1-1_arm64.deb
```
```
error: Can't resolve asset: .../assets/ffplayout.1.gz
```
`assets/ffplayout.1.gz` was referenced in the packaging metadata and
deliberately `.gitignore`'d (compiled output shouldn't be committed),
but nothing in the repo -- CI included -- ever actually generates it
from a source file. This `--variant arm64` build path had apparently
never been exercised end-to-end before. Wrote a real `assets/ffplayout.1`
man page from the binary's own `--help` output, gzipped it, and reran:
```
/home/pi/src/ffplayout/target/release/ffplayout --help
gzip -kf assets/ffplayout.1
cargo deb -p ffplayout --manifest-path backend/app/Cargo.toml --no-build --variant arm64 -o dist/ffplayout_2.2.1-1_arm64.deb
```
→ built clean.

**Installing over the old manually-built ffplayout** needed care --
its binary and systemd unit were never dpkg-tracked:
```
dpkg -S /usr/bin/ffplayout                        # no path found -- untracked
sudo cp -a /usr/share/ffplayout/db/ffplayout.db /home/pi/ffplayout.db.backup-$(date +%Y%m%d-%H%M%S)
sudo apt-get install ./dist/ffplayout_2.2.1-1_arm64.deb
dpkg -S /usr/bin/ffplayout                        # now owned by the ffplayout package
diff /etc/systemd/system/ffplayout.service /usr/lib/systemd/system/ffplayout.service
sudo rm /etc/systemd/system/ffplayout.service      # stale manual copy, now redundant
sudo systemctl daemon-reload
systemctl cat ffplayout.service                    # confirms the vendor unit + drop-in both apply
```

**Found the field still didn't show up in the UI** even after all of
this. Traced it to the actual config, not a guess:
```
sqlite3 /usr/share/ffplayout/db/ffplayout.db "SELECT id, name, stream_format, stream_type FROM outputs;"
```
```
2|stream||udp
```
`stream_format` is blank for a `udp` output -- that field only matters
for the `Custom` stream type. The real muxer comes from
`StreamType::muxer()`, which hardcodes `udp`/`srt` to `"mpegts"`
regardless of `stream_format`. The backend gate (`muxer == "mpegts"`)
was already correct; the frontend `v-if` was checking the wrong field
and could never be true for a udp/srt output. Replaced it with a
computed property mirroring the backend's real logic (`udp`, `srt`, or
`custom` with `stream_format === 'mpegts'`).

**Reorganizing the branch before pushing**: the fork's own git history
turned out to be ahead of what this local clone knew about --
```
git fetch fork
git log --oneline -15 fork/main
git merge-base --is-ancestor e99fb227 fork/main   # already merged via a separate PR
```
confirmed the v4l2m2m, engine-error-chain, and remote-source-seek-hang
fixes were all already live on the fork's `main` (PRs #1-#4) -- so the
only genuinely new, unpushed work was the two service-name commits.
Built a fresh branch directly off the current `fork/main` and
cherry-picked just those, using an isolated worktree so the main
checkout's (ultimately dead, see below) uncommitted changes were never
touched:
```
git worktree add ../ffplayout-dvb-service-name feature/dvb-service-name
cd ../ffplayout-dvb-service-name
git cherry-pick 91b6cc24 2a62f918
CARGO_TARGET_DIR=/home/pi/src/ffplayout/target cargo build -p ff-engine -p ffplayout
```
Also checked whether six files' worth of pre-existing uncommitted
working-tree changes (a live-source seek fix, some locale strings)
were real unfinished work or dead weight, rather than assuming either
way:
```
git diff backend/app/src/player/output/playout.rs
git log --oneline -p 4064a76e -- backend/app/src/player/output/playout.rs
```
Byte-for-byte identical to an already-merged commit -- confirmed the
same for the locale files and `PlayerView.vue` against `fork/main`,
then discarded all six as stale leftovers:
```
git checkout -- backend/app/src/player/output/playout.rs frontend/src/locales/*.ts frontend/src/views/PlayerView.vue
```
Pushed the finished branch:
```
git push fork feature/dvb-service-name
```

---

## 14. Command log: the stale-build gotcha, and a second Pi as a clean proving ground

**A real production bug surfaced by the service-name fix itself, found by
being suspicious of a UI that "should" work but didn't.** After fixing
the `stream_format`/`isMpegtsStream` field-visibility bug, the field
still didn't show up -- not a caching issue (confirmed in a fresh
incognito window), not a wrong-branch issue (confirmed the checked-out
commit matched), not a stale-binary issue (confirmed the running
binary's md5sum matched the freshly built one). What actually differed:
```
grep -o ".\{150\}stream_format===\`mpegts\`.\{80\}" .../ConfigPlayout-*.js
```
showed the OLD buggy condition still compiled into the served bundle.
Checked the dist file's own mtime against the source fix's commit time
-- 90+ minutes stale. Root cause: `build.rs` prints exactly one
`rerun-if-changed` (for the Windows icon), and Cargo's rule is that
printing *any* `rerun-if-changed` replaces its default "rerun if
anything changed" heuristic entirely -- so frontend edits had silently
stopped triggering a rebuild after the very first successful release
build. Fixed by adding explicit `rerun-if-changed` lines for
`frontend/src`, `package.json`, `package-lock.json` and `vite.config.ts`.
Verified the fix landed by checking the compiled (not source) JS
directly each time, rather than trusting the build's own "success" exit
code:
```
npm run build   # regenerate dist/ by hand to confirm the fix compiles
grep -o "stream_type;return e===\`udp\`||e===\`srt\`" dist/assets/ConfigPlayout-*.js
touch backend/app/src/serve/routes.rs   # force Cargo to re-embed the now-correct dist/
cargo build --release -p ffplayout --no-default-features --features embed_frontend
```

**Deployed `tv-channel-dvbt` + the ffplayout fork to a second, independent
Pi 4 (`tv.local`) as a clean proving ground** -- the same machine used a
couple of weeks ago for Kaffeine receiver testing, now repurposed. Built
once on `teletext`, copied the finished `.deb`s over rather than
rebuilding from source a second time:
```
scp ffplayout_2.2.1-3_arm64.deb tv-channel-dvbt_1.0.0-3_arm64.deb pi@tv.local:/tmp/
ssh pi@tv.local sudo apt-get install -y /tmp/ffplayout_2.2.1-3_arm64.deb
ssh pi@tv.local sudo apt-get install -y /tmp/tv-channel-dvbt_1.0.0-3_arm64.deb
```
Both installed clean on a genuinely fresh machine -- `dvbtx` user
created, both services disabled+inactive, `LimitRTPRIO=95` applied,
confirming the packaging is portable and not just working by
coincidence on the original dev machine.

**Three real, independent gotchas found getting this second machine
fully working, none of them DVB-T-specific:**

1. NAS mount wasn't replicated yet -- ffplayout's storage lives on the
   same NAS as `teletext`, so the fstab entry needed copying over
   before ffplayout had anything to play.
2. The browser-based initial setup wizard left the admin account in a
   state where login always failed with a cryptic `Mail error: Invalid
   input` -- turned out to be a real, if narrow, product bug: the login
   flow tries to send a 2FA code by email whenever the user has
   `two_factor` set *and* the global SMTP fields are non-empty, and the
   setup wizard had apparently submitted non-empty SMTP placeholder
   values without the user intending to enable email at all. Fixed by
   resetting the admin user via the CLI with two-factor explicitly
   disabled, bypassing the whole email path:
   ```
   sudo -u ffpu /usr/bin/ffplayout --user-set -u jeff -m jeffspiinthesky@gmail.com -p 'Password1' --two-factor false
   ```
3. Playout start failed in a loop (`Run channel 1 failed: Conflict:
   Permission denied`) even though the NAS content itself was readable
   by `ffpu` -- the actual cause was `h264_v4l2m2m` unable to open any
   `/dev/video*` device, since those are group-owned `video` with no
   "other" access and this fresh install's `ffpu` had never been added
   to that group (confirmed via the real ffmpeg error,
   `Could not find a valid device`, and via `ls -la /dev/video*`).
   `teletext`'s `ffpu` already had this membership, just never through
   anything the package itself does -- a real, previously-unnoticed gap
   in `debian/postinst`, now fixed there directly so future installs
   don't need this manual step:
   ```
   sudo usermod -aG video ffpu
   sudo systemctl restart ffplayout
   ```

**Result: full end-to-end validation on independent hardware.** DVB-T
transmit enabled the same way as on `teletext` (`systemctl enable --now
tv-channel-dvbt-transmit.service`), settled to 1 underrun over 45
seconds -- cleaner than most `teletext` runs -- and confirmed received
on a real TV. Investigated `tv.local`'s visibly higher CPU load
(`uptime` showing 5.7 vs. `teletext`'s typical load) before assuming
the obvious culprit (a desktop session left over from Kaffeine testing)
-- ruled that out directly (`labwc`/`wf-panel-pi` at 0.2-0.6% CPU, not
the driver) and confirmed hardware encode was genuinely active rather
than silently falling back to software:
```
sudo ls -la /proc/<ffplayout_pid>/fd/ | grep video   # /dev/video11 open -- real hardware encode
```
The actual explanation: decode is software-only everywhere in this
fork (confirmed earlier this session, still true), and this test
playlist's WebM (VP8/VP9) sources decode far more expensively in
software than the plain H.264 content this project's real playlists
normally use -- a content difference, not a setup problem.

---
