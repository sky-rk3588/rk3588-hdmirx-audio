# HDMI IN on Orange Pi 5 Plus (RK3588) — complete guide

Everything done to get **HDMI input** (video **and** audio) working on an
Orange Pi 5 Plus, Ubuntu, mainline-based kernel `7.0.0-rk3588-hdr+`.
Two parts: video capture (already in mainline) and an audio-capture
**driver we wrote from scratch** (mainline has none).

---

## Hardware / environment

- Board: Orange Pi 5 Plus (RK3588), Mali-G610 / Panthor, KDE Plasma Wayland.
- HDMI RX block: `snps_hdmirx` (mainline Synopsys DW HDMI RX driver),
  node `hdmi_receiver@fdee0000`, V4L2 device **`/dev/video5`**.
  (NB: `/dev/video0` is the v4l2loopback virtual camera, **not** HDMI IN.)
- Kernel `7.0.0-rk3588-hdr+` (Ubuntu mainline + Collabora HDR/OC patches),
  boots via EDK2 UEFI → custom GRUB entry that loads a device tree with
  `devicetree /boot/rk3588-orangepi-5-plus-collabora-oc.dtb`.

---

## Part 1 — Video capture (works out of the box)

Format from the RX is raw **BGR3** (24-bit, uncompressed) — there is no
codec on the input; nothing to decode.

Detect the incoming signal, then view it:

```sh
v4l2-ctl -d /dev/video5 --query-dv-timings        # is there a signal?
v4l2-ctl -d /dev/video5 --set-dv-bt-timings query # lock to it
```

Helper scripts (`scripts/`):

| Command | What |
|---|---|
| `hdmi-in` | Windowed live view (gtkwaylandsink, zero-copy, decorations) |
| `hdmi-in fs` | Fullscreen |
| `hdmi-in fps` | Live FPS/dropped counter in the terminal |
| `hdmi-in info` | Resolution, rate, format, bandwidth, quantization, HDR |
| `hdmi-in-av` | Live video **+ audio** together |

Smooth, zero-copy pipeline (the core of the scripts):

```sh
gst-launch-1.0 v4l2src device=/dev/video5 io-mode=dmabuf ! gtkwaylandsink sync=false
```

Notes learned:
- `videoconvert + xvimagesink` is CPU-bound (~25-30 fps at 1080p60);
  use `gtkwaylandsink`/`waylandsink` for full 60.
- `kmssink` only works from a bare TTY (compositor holds DRM master).
- `mpv`/`ffplay` **cannot** open `/dev/video5`: hdmirx is *multiplanar*
  V4L2 and their V4L2 demuxer is single-planar only. Use GStreamer.

### EDID / resolution ceiling

The default hdmirx EDID caps at HDMI 1.4 (300 MHz TMDS → 4K30, no 1440p).
A custom **4K60 + 1440p + HDR EDID** was built (`tools/`-generated,
`edid-decode`-validated) and flashed with
`v4l2-ctl -d /dev/video5 --set-edid=file=...`.

Result: **both phones tested (Honor Magic8 Pro and Samsung S25 Ultra DeX)
top out at 1080p60 over USB-C** — the ceiling is the phone, not the Pi.
A PC/console source would use the higher EDID modes.

---

## Part 2 — Audio capture (the driver we wrote)

Mainline `synopsys-hdmirx` is **video only**; audio + HDCP are an
unimplemented TODO upstream (confirmed by Collabora). The RK3588 hardware
does deliver the embedded HDMI audio to an on-SoC I2S controller — so we
ported/wrote the audio path into the driver.

### How it works

1. **hdmi-codec child** — the driver registers the generic ASoC
   `hdmi-codec` as a child platform device of the controller. Because ASoC
   falls back to the *parent's* `of_node`, a `simple-audio-card` can bind
   the HDMI RX audio DAI via `<&hdmirx_ctrler 0>` (needs
   `#sound-dai-cells = <1>` on the node).
2. **Sample-rate recovery** — `hdmirx_audio_fs()` computes the rate from
   the **ACR N/CTS** values and the measured TMDS character rate.
3. **Enable path** — on `hw_params`: set the audio reference clock to
   `fs * 128`, init the audio FIFO + thresholds, set `I2S_EN` and
   `AUDIO_ENABLE`.
4. **Clock drift tracking** — a periodic `delayed_work` reads the audio
   FIFO fill level (`AUDIO_FIFO_STATUS2`) and nudges the audio clock in
   small **ppm** steps to hold it near target. This locks the local
   capture clock to the source and eliminates dropped samples.

Audio path: HDMI RX → internal I2S → **`i2s7_8ch`** (`i2s@fddf8000`,
`rockchip,capture-only`, DMA) → ALSA capture card **`rockchip,hdmiin`**.

### Milestones (how we got there)

| # | What | Result |
|---|---|---|
| M1 | DT design (enable i2s7 + `simple-audio-card` + `#sound-dai-cells`) | card node ready |
| M2b | driver: register `hdmi-codec` | ALSA card `rockchiphdmiin` appears |
| M3a | driver: enable audio (fs + FIFO + I2S_EN + clock) | real sound captured |
| M3b | driver: FIFO drift tracking | clean, glitch-free sound |
| M4 | package as upstream patch series | `patches/`, checkpatch clean |

---

## Part 3 — Build & deploy

```sh
# fetch clean mainline v7.0 driver into build/, then:
python3 tools/patch_upstream.py         # apply audio changes to .c/.h
cd build && make -C /lib/modules/$(uname -r)/build M=$PWD modules
```

Deploy on this board:
1. Install `synopsys-hdmirx.ko` over
   `/usr/lib/modules/<ver>/kernel/drivers/media/platform/synopsys/hdmirx/`.
2. Add the device-tree bits (`dts/rk3588-hdmirx-audio-example.dtsi`) into
   the DTB that **GRUB actually loads** — here that is
   `/boot/rk3588-orangepi-5-plus-collabora-oc.dtb` (the OC entry). The
   live tree has no `__symbols__`, so a runtime overlay can't reference
   base nodes — the base DTB must be edited.
3. `sudo depmod -a` and **reboot** (module is refcount-held; no hot-swap).

Gotchas hit along the way:
- The GRUB default entry loads the **`-oc.dtb`**, not the plain
  `collabora.dtb` — editing the wrong one has no effect.
- The **ALSA card number changes across reboots** — always address it by
  name: `hw:CARD=rockchiphdmiin`, not `hw:2`.
- `KERNEL TAINTED` (`O`+`E`) is normal for an out-of-tree/unsigned module.
- Slow reboots here are the `ath12k` Wi-Fi 7 driver + `NetworkManager-
  wait-online`, unrelated to this module.

---

## Part 4 — Use

```sh
hdmi-in-av                                  # video + audio, live
arecord -D hw:CARD=rockchiphdmiin -f S16_LE -r 48000 -c 2 out.wav
aplay out.wav
```

The phone must enable "play sound on connected display" (DeX / projection)
for audio to be sent. Verified capturing 44.1/48 kHz stereo, clean.

---

## Part 5 — Upstream

`patches/` is a `git format-patch` series (DT binding + driver), ready for
**linux-media** (email, not a GitHub PR). Send as `[RFC]` — Collabora
(Shreeya Patel, Dmitry Osipenko) authors the driver and may be working on
audio already. Board DT enablement is a separate patch via the Rockchip
tree.
