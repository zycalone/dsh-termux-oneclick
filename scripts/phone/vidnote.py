#!/usr/bin/env python3
"""vidnote.py —— 手机端"看视频出笔记"流水线

流程：ffmpeg 抽帧（按画面变化抽，PPT 型课效率最高）→ 逐帧视觉模型抄画面文字
      → 文本模型汇总成章节笔记。不依赖云端音视频能力，只靠"看图"。
      端点与模型走 llm.py 的回退链，一个挂了自动换下一个。

用法：
  python vidnote.py <视频路径或链接> [--kind note|lecture|meeting|auto]
                    [--interval 30] [--max 24] [--out 输出.md]
  python vidnote.py ~/tmp/课.mp4 --max 8
  python vidnote.py "https://www.bilibili.com/video/BVxxxx" --kind lecture --max 12

  给链接时先用 yt-dlp 下载（装法：python -m pip install -U yt-dlp），再照常抽帧。
  --kind lecture/meeting 复用 minutetool.py 的笔记/纪要结构；默认 note 是学习笔记老格式。

输出：
  ~/tmp/vid/frames/          抽出的帧
  ~/tmp/vid/<视频名>-笔记.md   逐帧文字 + 汇总笔记
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm  # 多端点回退链，见 docs/12

# 仅作为提示；真正的端点/模型配置在 ~/dsh-phone/endpoints.json
GW = os.environ.get("DSH_GW", "http://127.0.0.1:8787/v1/chat/completions")
KEY = os.environ.get("DSH_KEY", "local-noop")
VMODEL = os.environ.get("DSH_VISION_MODEL", "glm-5v-turbo")
TMODEL = os.environ.get("DSH_TEXT_MODEL", "deepseek-v4-pro")

FRAME_PROMPT = (
    "这是视频在 {t} 处的画面截图。请只做两件事：\n"
    "1) 画面文字：逐字抄写画面里出现的所有文字（标题/正文/公式/字幕/弹幕）；没有文字就写 无。\n"
    "2) 这一屏在讲什么：一句话概括（若只是人脸、空镜、logo 或纯装饰，就写 无信息）。\n"
    "不要联想，不要根据标题、推荐栏、搜索词推测视频讲了什么。"
)

SUMMARY_PROMPT = (
    "下面是同一个网课视频按时间顺序抽帧后，每帧抄下的画面文字。\n"
    "请据此整理一份中文学习笔记，包含：\n"
    "一、本节内容主线（3-6 条）\n"
    "二、关键概念与定义（逐条，术语保留原文）\n"
    "三、可能被考到的点（5-10 条，判断/单选口吻）\n"
    "四、看不懂/信息缺失的地方（若某些时段无文字，指出需要回看的位置）\n"
    "只依据给定文字，不要编造。\n"
    "特别注意：如果逐帧文字里主要是界面元素（标题栏、推荐列表、播放数据、进度条），\n"
    "那说明这个视频没有可用的文字内容，直接说明这一点，不要用标题去推测视频内容。"
)


def post(payload, timeout=180):
    """兼容旧签名：吃 {model, messages, max_tokens, temperature}，内部走回退链。

    指定模型全挂时会放开模型限制再试一遍（端点还活着但模型下线的情况）。
    """
    r = llm.chat(
        payload["messages"],
        model=payload.get("model"),
        max_tokens=int(payload.get("max_tokens", 800)),
        temperature=float(payload.get("temperature", 0.2)),
        fallback_any_model=True,
    )
    return r["text"]


def vision(img_path, t_label):
    """逐帧读画面：走视觉模型回退链（记不住的话会说 ERROR，但不会整段崩）。"""
    return llm.ask(
        FRAME_PROMPT.format(t=t_label),
        image_path=img_path,
        max_tokens=700,
        temperature=0.1,
    )["text"]


def download(url, workdir):
    """给链接就用 yt-dlp 下载（手机端 yt-dlp 在 Termux 的 PATH 里）。"""
    dl_dir = os.path.join(workdir, "dl")
    os.makedirs(dl_dir, exist_ok=True)
    if not shutil.which("yt-dlp"):
        raise SystemExit("给链接需要 yt-dlp：python -m pip install -U yt-dlp")
    print("下载中（yt-dlp）：%s" % url, flush=True)
    cmd = ["yt-dlp", "--no-playlist", "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
           "--merge-output-format", "mp4", "-o", os.path.join(dl_dir, "%(title).60s.%(ext)s"),
           url]
    p = subprocess.run(cmd, capture_output=True, text=True)
    line = ""
    for l in (p.stdout or "").splitlines():
        if "[download] " in l and "%" in l:
            line = l.strip()
        if "Destination:" in l or "Merging formats into" in l:
            line = l.strip()
    out_all = (p.stderr or "") + (p.stdout or "")
    if p.returncode != 0:
        tail = out_all.strip().splitlines()[-3:]
        msg = " | ".join(tail)
        hint = ""
        low = (msg + url).lower()
        if "drm" in low or "widevine" in low:
            hint = ("\n提示：这个片源是加密的（DRM），yt-dlp 下不了 —— 腾讯/爱奇艺/优酷的会员片源基本都是这样。\n"
                    "      换免费公开片源，或先在别处下好 mp4 再传进手机用本地视频模式。")
        elif "v.qq.com" in low or "iqiyi" in low or "youku" in low:
            hint = ("\n提示：这几个平台的播放页经常要求登录/会员，或者给的是整部剧的列表页。\n"
                    "      给「单集播放页」链接，且是免费可看的片源；加密片源技术上拿不到。")
        elif "playlist" in low and "0 items" in low:
            hint = "\n提示：这是剧集/列表页，不是单集。请在浏览器里点开要解析的那一集，复制那一集的播放页链接。"
        raise SystemExit("下载失败：%s%s" % (msg, hint))
    cand = [os.path.join(dl_dir, f) for f in os.listdir(dl_dir) if f.lower().endswith((".mp4", ".mkv", ".webm"))]
    if not cand:
        raise SystemExit("下载完成但没找到视频文件\n"
                         "提示：如果是剧集/列表页，请给单集播放页链接；加密片源（DRM）拿不到。")
    newest = max(cand, key=os.path.getmtime)
    print("下载完成：%s（%.1f MB）" % (os.path.basename(newest), os.path.getsize(newest) / 1048576), flush=True)
    return newest


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
    interval, max_frames, out, kind = 30, 24, None, "note"
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--interval":
            interval = int(args[i + 1]); i += 2
        elif args[i] == "--max":
            max_frames = int(args[i + 1]); i += 2
        elif args[i] == "--out":
            out = args[i + 1]; i += 2
        elif args[i] == "--kind":
            kind = args[i + 1]; i += 2
        else:
            i += 1
    workdir = os.path.expanduser("~/tmp/vid")
    if video.startswith(("http://", "https://")):
        video = download(video, workdir)
    if not os.path.exists(video):
        raise SystemExit("找不到视频：%s" % video)
    base = os.path.splitext(os.path.basename(video))[0]
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
        if kind == "auto":
            try:
                import minutetool
                probe = llm.ask(minutetool.KIND_PROBE.format(sample=joined[:2500]),
                                max_tokens=120, temperature=0.1, trace=False)["text"]
                kind = "lecture" if ("讲座" in probe or "lecture" in probe) else "meeting"
            except Exception:  # noqa: BLE001
                kind = "lecture"
            print("自动判断：%s" % kind, flush=True)
        if kind in ("lecture", "meeting"):
            import minutetool
            tpl = minutetool.MERGE_LECTURE if kind == "lecture" else minutetool.MERGE_MEETING
            summary = llm.ask(tpl.format(body=joined), max_tokens=2200, temperature=0.3, trace=False)["text"]
        else:
            summary = post({"model": TMODEL, "messages": [
                {"role": "user", "content": SUMMARY_PROMPT + "\n\n" + joined}],
                "max_tokens": 2000, "temperature": 0.2}, timeout=300)
    except Exception as e:  # noqa: BLE001
        summary = "汇总失败: %s" % e
    out = out or os.path.join(workdir, base + "-笔记.md")
    with open(out, "w", encoding="utf-8") as f:
        _label = {"note": "视频笔记", "lecture": "学习笔记", "meeting": "会议纪要"}.get(kind, "视频笔记")
        f.write("# %s %s\n\n" % (base, _label))
        f.write(summary + "\n\n---\n\n## 逐屏原文（按时间）\n\n" + joined + "\n")
    print("\n笔记已写入:", out)


if __name__ == "__main__":
    main()
