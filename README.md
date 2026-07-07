# RK3588 HDMI RX audio capture

HDMI **input** audio capture for the mainline Synopsys DesignWare HDMI RX
driver (`synopsys-hdmirx`) on the Rockchip RK3588 (tested on an
**Orange Pi 5 Plus**, Ubuntu, kernel 7.0).

The mainline driver captures HDMI-input **video** only — audio is a known
"not yet supported" TODO. This project adds the missing **audio capture**
path: the audio embedded in the incoming HDMI stream shows up as a normal
ALSA capture device and can be recorded or played live alongside the video.

## What works

- HDMI IN video (1080p60, up to 4K per the RX)
- HDMI IN **audio** → ALSA card `rockchip,hdmiin` (`arecord`)
- Live video **+** audio together
- Clock drift tracking → clean, glitch-free audio for long capture

## How it works

The HDMI RX controller feeds the recovered audio to an on-SoC I2S
controller. The driver:

1. Registers the generic `hdmi-codec` as a child of the controller, so a
   `simple-audio-card` in the device tree binds the HDMI RX audio DAI
   (`cpu = <&i2s7_8ch>`, `codec = <&hdmirx 0>`).
2. Recovers the audio sample rate from the **ACR N/CTS** values and the
   measured TMDS character rate.
3. Runs a periodic worker that keeps the local audio reference clock
   **locked to the source** by nudging it in small ppm steps to hold the
   audio FIFO near its target level — avoiding FIFO under/overflow and
   dropped samples.

## Contents

| Path | What |
|------|------|
| `patches/` | Upstream-style patch series (dt-binding + driver), `checkpatch` clean |
| `scripts/hdmi-in` | Live HDMI IN **video** viewer (gstreamer, zero-copy) |
| `scripts/hdmi-in-av` | Live HDMI IN **video + audio** |
| `tools/patch_upstream.py` | Generates the driver/header changes on clean mainline source |
| `dts/rk3588-hdmirx-audio-example.dtsi` | Example device-tree changes (enable I2S + `simple-audio-card`) |

## Build the module

```sh
# needs kernel headers for the running kernel
mkdir build && cp <mainline v7.0>/drivers/media/platform/synopsys/hdmirx/*.{c,h} build/
python3 tools/patch_upstream.py          # apply the audio changes
cd build && make -C /lib/modules/$(uname -r)/build M=$PWD modules
```

Install `synopsys-hdmirx.ko` over the distro module, add the device-tree
bits (enable the capture-only I2S + a `simple-audio-card`), and reboot.

## Use

```sh
hdmi-in                 # video only
hdmi-in-av              # video + audio
arecord -D hw:CARD=rockchiphdmiin -f S16_LE -r 48000 -c 2 out.wav
```

## Upstream

The `patches/` series is prepared for submission to **linux-media**
(driver + DT binding). The board-specific device-tree enablement is a
separate patch through the Rockchip tree. Maintainers: Collabora
(Shreeya Patel, Dmitry Osipenko) — the mainline driver authors.

## License

Kernel changes are GPL-2.0 (matching the driver).
