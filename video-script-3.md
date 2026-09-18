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
- Not a CPU/processing bottleneck — the Pi is nowhere near maxed out
  while this happens (comfortably idle, on both an RT and non-RT
  kernel).
- Not the HackRF or the USB connection to it — a raw, direct test at
  the exact same data rate 8MHz needs runs perfectly cleanly, sustained,
  no drops.
- Not missing real-time scheduling — the relevant processing threads
  already run at real-time priority.
- Not the kernel — installing a real-time (PREEMPT_RT) Linux kernel
  made no measurable difference.

**What's still open:**
- The problem is now narrowed down to somewhere *inside* the GNU
  Radio processing chain itself (not the hardware, not the OS) — but
  the exact cause within it isn't nailed down yet.
- One concrete lead: GNU Radio is silently overriding a buffer-size
  setting we tried to increase, capping it much lower than requested —
  worth understanding why, and whether that's actually the culprit.
- Simpler, unrelated loose end: the *receiver* side is still configured
  to expect 6MHz, not 8MHz — worth double-checking that isn't
  contributing to "nothing shows up" independent of the transmit-side
  investigation above.

---
