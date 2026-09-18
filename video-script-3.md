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
