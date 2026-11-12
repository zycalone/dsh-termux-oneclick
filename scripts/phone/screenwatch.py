#!/usr/bin/env python3
"""screenwatch.py —— 边播边看：采样手机屏幕 → 视觉模型读画面 → 出笔记
不需要下载视频，任何 App（学习通/雨课堂/网页）播放中的画面都能抓。

用法（在手机 Termux 里）：
  python dsh-phone/screenwatch.py --minutes 15 --interval 20
  python dsh-phone/screenwatch.py --minutes 3 --interval 8 --max 20

说明：
  - 用 adb exec-out screencap 抓屏；相同画面（md5 一样）自动跳过
  - 每帧交给 glm-5v-turbo 抄画面文字 + 一句话概括
  - 最后用 deepseek-v4-pro 汇总成本节笔记，存 ~/tmp/vid/屏幕笔记-<时间>.md
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.expanduser("~/dsh-phone"))
try:
    from vidnote import post, vision, SUMMARY_PROMPT  # 复用
except Exception as e:  # noqa: BLE001
    print("需要 vidnote.py 在 ~/dsh-phone/ 下:", e)
    raise

ADB = ["adb", "-s", "127.0.0.1:5556"]


def shot(path):
    with open(path, "wb") as f:
        p = subprocess.run(ADB + ["exec-out", "screencap", "-p"], stdout=f,
                           stderr=subprocess.DEVNULL, timeout=60)
    return p.returncode == 0 and os.path.getsize(path) > 20000


def shrink(path):
    """有 ffmpeg 就转成 720p jpg，省流量也省磁盘；没有就保留 png。"""
    if not shutil.which("ffmpeg"):
        return path
    jpg = path[:-4] + ".jpg"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", path, "-vf", "scale=-2:720", "-q:v", "3", jpg],
                       capture_output=True)
    if p.returncode == 0 and os.path.exists(jpg):
        os.remove(path)
        return jpg
    return path


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    minutes, interval, maxn = 15.0, 20.0, 40
    a = sys.argv[1:]
    i = 0
    while i < len(a):
        if a[i] == "--minutes":
            minutes = float(a[i + 1]); i += 2
        elif a[i] == "--interval":
            interval = float(a[i + 1]); i += 2
        elif a[i] == "--max":
            maxn = int(a[i + 1]); i += 2
        else:
            i += 1
    stamp = time.strftime("%m%d-%H%M")
    workdir = os.path.expanduser("~/tmp/vid/live-" + stamp)
    os.makedirs(workdir, exist_ok=True)
    print("开始抓屏：每 %.0fs 一张，共 %.1f 分钟 → %s" % (interval, minutes, workdir), flush=True)

    t0 = time.time()
    seen, rows, last = set(), [], None
    while time.time() - t0 < minutes * 60:
        n = len(rows)
        if n >= maxn:
            print("已到上限 %d 帧，停" % maxn, flush=True)
            break
        fp = os.path.join(workdir, "s_%03d.png" % n)
        if shot(fp):
            h = md5(fp)
            if h == last:
                os.remove(fp)
            else:
                last = h
                fp2 = shrink(fp)
                label = "%d:%02d" % (int((time.time() - t0) // 60), int((time.time() - t0) % 60))
                try:
                    txt = vision(fp2, "播放后第 %s" % label)
                except Exception as e:  # noqa: BLE001
                    txt = "ERROR %s" % e
                rows.append((label, txt))
                print("[%s] %s" % (label, txt.replace("\n", " ")[:110]), flush=True)
        time.sleep(interval)

    if not rows:
        print("没抓到有效画面")
        return
    joined = "\n\n".join("### %s\n%s" % (t, x) for t, x in rows)
    try:
        summary = post({"model": "deepseek-v4-pro", "messages": [
            {"role": "user", "content": SUMMARY_PROMPT + "\n\n" + joined}],
            "max_tokens": 2000, "temperature": 0.2}, timeout=300)
    except Exception as e:  # noqa: BLE001
        summary = "汇总失败: %s" % e
    out = os.path.join(workdir, "笔记.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# 屏幕观看笔记（%s）\n\n" % stamp)
        f.write(summary + "\n\n---\n\n## 逐屏原文\n\n" + joined + "\n")
    print("\n笔记已写入:", out, flush=True)
    print("帧数:", len(rows))


if __name__ == "__main__":
    main()
