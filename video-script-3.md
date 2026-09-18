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
