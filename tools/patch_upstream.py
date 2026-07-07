#!/usr/bin/env python3
# Upstream-quality: register offsets in .h (interleaved w/ bits), logic in .c.
import sys
D = "/home/sky/hdmirx-audio/upstream/"

# ---------- snps_hdmirx.h ----------
h = open(D + "snps_hdmirx.h").read()
def hrep(old, new, tag):
    global h
    if h.count(old) != 1: print(f"H FAIL {tag}: {h.count(old)}"); sys.exit(1)
    h = h.replace(old, new)

hrep("#define AFIFO_FILL_RESTART\t\t\tBIT(0)\n#define AFIFO_INIT_P\t\t\t\tBIT(0)\n",
     "#define AUDIO_FIFO_CONFIG\t\t\t0x0460\n"
     "#define AFIFO_FILL_RESTART\t\t\tBIT(0)\n"
     "#define AUDIO_FIFO_CONTROL\t\t\t0x0464\n"
     "#define AFIFO_INIT_P\t\t\t\tBIT(0)\n"
     "#define AUDIO_FIFO_THR_PASS\t\t\t0x0468\n"
     "#define AUDIO_FIFO_THR\t\t\t\t0x046c\n", "fifo-offsets")

hrep("#define AFIFO_THR_MUTE_LOW_QST_MASK\t\tGENMASK(25, 16)",
     "#define AUDIO_FIFO_MUTE_THR\t\t\t0x0470\n"
     "#define AFIFO_THR_MUTE_LOW_QST_MASK\t\tGENMASK(25, 16)", "mute-thr")

hrep("#define AFIFO_UNDERFLOW_ST\t\t\tBIT(25)",
     "#define AUDIO_FIFO_STATUS2\t\t\t0x0478\n"
     "#define AFIFO_UNDERFLOW_ST\t\t\tBIT(25)", "status2")

hrep("#define SPEAKER_ALLOC_OVR_EN\t\t\tBIT(16)",
     "#define AUDIO_PROC_CONFIG0\t\t\t0x0480\n"
     "#define SPEAKER_ALLOC_OVR_EN\t\t\tBIT(16)", "proc0")

hrep("#define AVPUNIT_ENABLE\t\t\t\tBIT(8)\n",
     "#define AVPUNIT_ENABLE\t\t\t\tBIT(8)\n#define AUDIO_ENABLE\t\t\t\tBIT(9)\n", "audio-en")
open(D + "snps_hdmirx.h", "w").write(h)

# ---------- snps_hdmirx.c ----------
s = open(D + "snps_hdmirx.c").read()
def rep(old, new, tag):
    global s
    if s.count(old) != 1: print(f"C FAIL {tag}: {s.count(old)}"); sys.exit(1)
    s = s.replace(old, new)

rep("#include <media/videobuf2-v4l2.h>\n\n#include \"snps_hdmirx.h\"",
    "#include <media/videobuf2-v4l2.h>\n\n#include <sound/hdmi-codec.h>\n\n#include \"snps_hdmirx.h\"", "inc")

rep("\tstruct hdmirx_cec *cec;\n",
    "\tstruct hdmirx_cec *cec;\n"
    "\tstruct platform_device *audio_pdev;\n"
    "\tstruct delayed_work audio_work;\n"
    "\tu32 audio_clkrate;\n"
    "\tu32 audio_fs;\n"
    "\tint audio_pre_state;\n", "fields")

block = r'''#define HDMIRX_AUDIO_INIT_FIFO_STATE	128
#define HDMIRX_AUDIO_INIT_STATE		(HDMIRX_AUDIO_INIT_FIFO_STATE * 4)

static const int hdmirx_supported_fs[] = {
	32000, 44100, 48000, 88200, 96000, 176400, 192000, 768000, -1
};

static int hdmirx_audio_closest_fs(int fs)
{
	int i = 0, fs_t = hdmirx_supported_fs[0];

	while (fs_t > 0) {
		if (abs(fs - fs_t) <= 2000)
			return fs_t;
		fs_t = hdmirx_supported_fs[++i];
	}
	return 0;
}

/* Recover the incoming audio sample rate from the ACR N/CTS + TMDS clock. */
static u32 hdmirx_audio_fs(struct snps_hdmirx_dev *hdmirx_dev)
{
	u64 tmds_clk, fs_audio = 0;
	u32 acr_cts, acr_n, tmdsqpclk_freq;
	u32 acr_pb7_4, acr_pb3_0;

	tmdsqpclk_freq = hdmirx_readl(hdmirx_dev, CMU_TMDSQPCLK_FREQ);
	hdmirx_readl(hdmirx_dev, PKTDEC_ACR_PH2_1);
	acr_pb7_4 = hdmirx_readl(hdmirx_dev, PKTDEC_ACR_PB3_0);
	acr_pb3_0 = hdmirx_readl(hdmirx_dev, PKTDEC_ACR_PB7_4);
	acr_cts = __be32_to_cpu(acr_pb7_4) & 0xfffff;
	acr_n = (__be32_to_cpu(acr_pb3_0) & 0x0fffff00) >> 8;
	tmds_clk = tmdsqpclk_freq * 4 * 1000U;
	if (acr_cts != 0) {
		fs_audio = div_u64((tmds_clk * acr_n), acr_cts);
		fs_audio /= 128;
		fs_audio = hdmirx_audio_closest_fs(fs_audio);
	}
	return (u32)fs_audio;
}

/* Nudge the audio reference clock by +/- ppm to keep the FIFO balanced. */
static void hdmirx_audio_clk_ppm_inc(struct snps_hdmirx_dev *hdmirx_dev, int ppm)
{
	int delta, inc;
	long rate = hdmirx_dev->audio_clkrate;

	if (ppm < 0) {
		ppm = -ppm;
		inc = -1;
	} else {
		inc = 1;
	}
	delta = (int)div64_u64((u64)rate * ppm + 500000, 1000000);
	delta *= inc;
	rate = hdmirx_dev->audio_clkrate + delta;
	clk_set_rate(hdmirx_dev->clks[1].clk, rate);
	hdmirx_dev->audio_clkrate = rate;
}

static int hdmirx_audio_clk_adjust(struct snps_hdmirx_dev *hdmirx_dev,
				   int total_offset, int single_offset)
{
	int schedule_time = 500;
	int ppm = 10;
	u32 offset_abs = abs(total_offset);

	if (offset_abs > 200) {
		ppm += 200;
		schedule_time -= 100;
	}
	if (offset_abs > 100) {
		ppm += 200;
		schedule_time -= 100;
	}
	if (offset_abs > 32) {
		ppm += 20;
		schedule_time -= 100;
	}
	if (offset_abs > 16)
		ppm += 20;
	if (total_offset > 16 && single_offset > 0)
		hdmirx_audio_clk_ppm_inc(hdmirx_dev, ppm);
	else if (total_offset < -16 && single_offset < 0)
		hdmirx_audio_clk_ppm_inc(hdmirx_dev, -ppm);
	return schedule_time;
}

static void hdmirx_audio_fifo_reinit(struct snps_hdmirx_dev *hdmirx_dev)
{
	hdmirx_writel(hdmirx_dev, AUDIO_FIFO_CONTROL, 1);
	usleep_range(200, 210);
	hdmirx_writel(hdmirx_dev, AUDIO_FIFO_CONTROL, 0);
}

/*
 * Periodic worker that locks the local audio clock to the source by keeping
 * the audio FIFO fill level close to its target, avoiding under/overflow.
 */
static void hdmirx_audio_work(struct work_struct *work)
{
	struct snps_hdmirx_dev *hdmirx_dev =
		container_of(to_delayed_work(work), struct snps_hdmirx_dev, audio_work);
	unsigned long delay = 200;
	int cur, total, single;
	u32 fifo, fs;

	fs = hdmirx_audio_fs(hdmirx_dev);
	fifo = hdmirx_readl(hdmirx_dev, AUDIO_FIFO_STATUS2);

	if (fifo & (AFIFO_UNDERFLOW_ST | AFIFO_OVERFLOW_ST)) {
		if (fs) {
			clk_set_rate(hdmirx_dev->clks[1].clk, fs * 128);
			hdmirx_dev->audio_clkrate = fs * 128;
			hdmirx_dev->audio_fs = fs;
		}
		hdmirx_audio_fifo_reinit(hdmirx_dev);
		hdmirx_dev->audio_pre_state = 0;
		goto out;
	}

	cur = fifo & 0xffff;
	total = cur - HDMIRX_AUDIO_INIT_STATE;
	single = cur - hdmirx_dev->audio_pre_state;

	if (fs && abs((int)fs - (int)hdmirx_dev->audio_fs) > 1000) {
		clk_set_rate(hdmirx_dev->clks[1].clk, fs * 128);
		hdmirx_dev->audio_clkrate = fs * 128;
		hdmirx_dev->audio_fs = fs;
		hdmirx_audio_fifo_reinit(hdmirx_dev);
		hdmirx_dev->audio_pre_state = 0;
		goto out;
	}

	if (cur != 0)
		delay = hdmirx_audio_clk_adjust(hdmirx_dev, total, single);
	hdmirx_dev->audio_pre_state = cur;
out:
	schedule_delayed_work(&hdmirx_dev->audio_work, msecs_to_jiffies(delay));
}

static int hdmirx_audio_hw_params(struct device *dev, void *data,
				  struct hdmi_codec_daifmt *fmt,
				  struct hdmi_codec_params *hparms)
{
	struct snps_hdmirx_dev *hdmirx_dev = dev_get_drvdata(dev);
	u32 fs;

	fs = hdmirx_audio_fs(hdmirx_dev);
	if (!fs)
		fs = hparms ? hparms->sample_rate : 48000;
	if (!fs)
		fs = 48000;

	hdmirx_dev->audio_fs = fs;
	hdmirx_dev->audio_clkrate = fs * 128;
	clk_set_rate(hdmirx_dev->clks[1].clk, fs * 128);

	hdmirx_audio_fifo_reinit(hdmirx_dev);
	hdmirx_writel(hdmirx_dev, AUDIO_FIFO_THR_PASS, HDMIRX_AUDIO_INIT_FIFO_STATE);
	hdmirx_writel(hdmirx_dev, AUDIO_FIFO_THR,
		      AFIFO_THR_LOW_QST(0x20) | AFIFO_THR_HIGH_QST(0x160));
	hdmirx_writel(hdmirx_dev, AUDIO_FIFO_MUTE_THR,
		      AFIFO_THR_MUTE_LOW_QST(0x8) | AFIFO_THR_MUTE_HIGH_QST(0x178));

	hdmirx_update_bits(hdmirx_dev, AUDIO_PROC_CONFIG0, I2S_EN, I2S_EN);
	hdmirx_update_bits(hdmirx_dev, GLOBAL_SWENABLE, AUDIO_ENABLE, AUDIO_ENABLE);

	hdmirx_dev->audio_pre_state = 0;
	mod_delayed_work(system_unbound_wq, &hdmirx_dev->audio_work,
			 msecs_to_jiffies(200));

	dev_dbg(dev, "audio hw_params: fs=%u\n", fs);
	return 0;
}

static void hdmirx_audio_shutdown(struct device *dev, void *data)
{
	struct snps_hdmirx_dev *hdmirx_dev = dev_get_drvdata(dev);

	cancel_delayed_work_sync(&hdmirx_dev->audio_work);
	hdmirx_update_bits(hdmirx_dev, GLOBAL_SWENABLE, AUDIO_ENABLE, 0);
}

static int hdmirx_audio_get_dai_id(struct snd_soc_component *component,
				   struct device_node *endpoint,
				   void *data)
{
	return 0;
}

static const struct hdmi_codec_ops hdmirx_audio_codec_ops = {
	.hw_params = hdmirx_audio_hw_params,
	.audio_shutdown = hdmirx_audio_shutdown,
	.get_dai_id = hdmirx_audio_get_dai_id,
};

static int hdmirx_register_audio_device(struct snps_hdmirx_dev *hdmirx_dev)
{
	struct hdmi_codec_pdata codec_data = {
		.ops = &hdmirx_audio_codec_ops,
		.i2s = 1,
		.no_i2s_playback = 1,
		.max_i2s_channels = 8,
		.data = hdmirx_dev,
	};
	struct platform_device_info pdevinfo = {
		.parent = hdmirx_dev->dev,
		.id = PLATFORM_DEVID_AUTO,
		.name = HDMI_CODEC_DRV_NAME,
		.data = &codec_data,
		.size_data = sizeof(codec_data),
		.dma_mask = DMA_BIT_MASK(32),
	};

	hdmirx_dev->audio_pdev = platform_device_register_full(&pdevinfo);

	return PTR_ERR_OR_ZERO(hdmirx_dev->audio_pdev);
}

'''
rep("static int hdmirx_probe(struct platform_device *pdev)\n{",
    block + "static int hdmirx_probe(struct platform_device *pdev)\n{", "block")

rep("\tINIT_DELAYED_WORK(&hdmirx_dev->delayed_work_res_change,\n\t\t\t  hdmirx_delayed_work_res_change);\n",
    "\tINIT_DELAYED_WORK(&hdmirx_dev->delayed_work_res_change,\n\t\t\t  hdmirx_delayed_work_res_change);\n"
    "\tINIT_DELAYED_WORK(&hdmirx_dev->audio_work, hdmirx_audio_work);\n", "probe-init")

rep("\n\treturn 0;\n\nerr_unreg_video_dev:",
    "\n\tret = hdmirx_register_audio_device(hdmirx_dev);\n"
    "\tif (ret)\n"
    "\t\tdev_warn(dev, \"failed to register HDMI audio codec: %d\\n\", ret);\n"
    "\n\treturn 0;\n\nerr_unreg_video_dev:", "probe-call")

rep("\tv4l2_debugfs_if_free(hdmirx_dev->infoframes);\n",
    "\tcancel_delayed_work_sync(&hdmirx_dev->audio_work);\n"
    "\tif (hdmirx_dev->audio_pdev)\n"
    "\t\tplatform_device_unregister(hdmirx_dev->audio_pdev);\n\n"
    "\tv4l2_debugfs_if_free(hdmirx_dev->infoframes);\n", "remove")

open(D + "snps_hdmirx.c", "w").write(s)
print("upstream patch OK (.h + .c)")
