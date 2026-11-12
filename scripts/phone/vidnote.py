#!/usr/bin/env python3
"""vidnote.py —— 手机端"看视频出笔记"流水线

流程：ffmpeg 抽帧（按画面变化抽，PPT 型课效率最高）→ 逐帧视觉模型抄画面文字
      → 文本模型汇总成章节笔记。不依赖云端音视频能力，只靠"看图"。

用法：
  python vidnote.py <视频路径> [--interval 30] [--max 24] [--out 输出.md]
  python vidnote.py test.mp4 --max 8

输出：
  ~/tmp/vid/frames/          抽出的帧
  ~/tmp/vid/<视频名>-笔记.md   逐帧文字 + 汇总笔记
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

GW = "http://127.0.0.1:8787/v1/chat/completions"
KEY = "local-noop"
VMODEL = "glm-5v-turbo"
TMODEL = "deepseek-v4-pro"

FRAME_PROMPT = (
    "这是网课视频在 {t} 处的画面截图。请只做两件事：\n"
    "1) 画面文字：逐字抄写画面里出现的所有文字（PPT 标题/正文/公式/字幕）；没有文字就写 无。\n"
    "2) 这一屏在讲什么：一句话概括（若只是人脸、空镜、logo，就写 无信息）。\n"
    "不要联想，不要补充画面外的内容。"
)

SUMMARY_PROMPT = (
    "下面是同一个网课视频按时间顺序抽帧后，每帧抄下的画面文字。\n"
    "请据此整理一份中文学习笔记，包含：\n"
    "一、本节内容主线（3-6 条）\n"
    "二、关键概念与定义（逐条，术语保留原文）\n"
    "三、可能被考到的点（5-10 条，判断/单选口吻）\n"
    "四、看不懂/信息缺失的地方（若某些时段无文字，指出需要回看的位置）\n"
    "只依据给定文字，不要编造。"
)


def post(payload, timeout=180):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(GW, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return (d["choices"][0]["message"].get("content") or "").strip()


def vision(img_path, t_label):
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return post({"model": VMODEL, "messages": [{"role": "user", "content": [
        {"type": "text", "text": FRAME_PROMPT.format(t=t_label)},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
    ]}], "max_tokens": 700, "temperature": 0.1})


def mmss(s):
    s = int(float(s))
    return "%02d:%02d" % (s // 60, s % 60)


def extract(video, outdir, interval, max_frames, scene=0.12):
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        os.remove(os.path.join(outdir, f))
    # 先按画面变化抽
    cmd = ["ffmpeg", "-hide_banner", "-i", video,
           "-vf", "scale=-2:720,select='gt(scene,%s)',showinfo" % scene,
           "-vsync", "vfr", "-q:v", "3", os.path.join(outdir, "f_%04d.jpg")]
    p = subprocess.run(cmd, capture_output=True, text=True)
    times = [float(m) for m in re.findall(r"pts_time:\s*([0-9.]+)", p.stderr)]
    frames = sorted(f for f in os.listdir(outdir) if f.endswith(".jpg"))
    if len(frames) < 3:  # 静态画面/幻灯片不变化 → 退回等间隔抽帧
        for f in os.listdir(outdir):
            os.remove(os.path.join(outdir, f))
        cmd = ["ffmpeg", "-hide_banner", "-i", video,
               "-vf", "fps=1/%s,scale=-2:720" % interval,
               "-q:v", "3", os.path.join(outdir, "f_%04d.jpg")]
        p = subprocess.run(cmd, capture_output=True, text=True)
        dur = 0.0
        m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", p.stderr)
        if m:
            dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        frames = sorted(f for f in os.listdir(outdir) if f.endswith(".jpg"))
        times = [i * float(interval) for i in range(len(frames))]
    # 超量则等间隔挑
    if len(frames) > max_frames:
        idx = [round(i * (len(frames) - 1) / (max_frames - 1)) for i in range(max_frames)]
        frames = [frames[i] for i in idx]
        times = [times[i] if i < len(times) else 0 for i in idx]
    return [os.path.join(outdir, f) for f in frames], times


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    video = sys.argv[1]
    interval, max_frames, out = 30, 24, None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--interval":
            interval = int(args[i + 1]); i += 2
        elif args[i] == "--max":
            max_frames = int(args[i + 1]); i += 2
        elif args[i] == "--out":
            out = args[i + 1]; i += 2
        else:
            i += 1
    base = os.path.splitext(os.path.basename(video))[0]
    workdir = os.path.expanduser("~/tmp/vid")
    outdir = os.path.join(workdir, "frames_" + base)
    frames, times = extract(video, outdir, interval, max_frames)
    print("抽帧 %d 张 → %s" % (len(frames), outdir), flush=True)
    rows = []
    for k, (fp, t) in enumerate(zip(frames, times)):
        label = mmss(t)
        try:
            txt = vision(fp, label)
        except Exception as e:  # noqa: BLE001
            txt = "ERROR %s" % e
        rows.append((label, txt))
        print("[%s] %s" % (label, txt.replace("\n", " ")[:110]), flush=True)
    joined = "\n\n".join("### %s\n%s" % (t, x) for t, x in rows)
    summary = ""
    try:
        summary = post({"model": TMODEL, "messages": [
            {"role": "user", "content": SUMMARY_PROMPT + "\n\n" + joined}],
            "max_tokens": 2000, "temperature": 0.2}, timeout=300)
    except Exception as e:  # noqa: BLE001
        summary = "汇总失败: %s" % e
    out = out or os.path.join(workdir, base + "-笔记.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# %s 视频笔记\n\n" % base)
        f.write(summary + "\n\n---\n\n## 逐屏原文（按时间）\n\n" + joined + "\n")
    print("\n笔记已写入:", out)


if __name__ == "__main__":
    main()
