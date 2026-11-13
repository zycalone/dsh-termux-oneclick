#!/usr/bin/env python3
"""meetnote.py —— 开会时后台自己记纪要，散会给你一份 md

为什么这么设计（上一次踩的坑）：
  上次是「边开会边和 dsh 聊天」，结果每敲一条命令，浏览器就把会议挤到后台，
  截到的三张全是 dsh 自己的界面；切回会议还得靠 monkey 拉 App，非常麻烦。
  所以现在反过来：**你只管开会，脚本自己在后台定时截图记笔记，你不用碰手机。**

两种读法：
  --a11y        读「无障碍树」里的文字，不截图、不花视觉 token；树里读不到才退回截图
  --a11y-only   只读文字树，永不截图（会议 App 把共享内容画在图片里时就没有内容）
  （默认是截图模式，什么都不加）

特点：
  1. 只在前台确实是会议 App 时才截（前台是别的就跳过，不浪费 token、不打扰你）
  2. 画面没变化就不读图（md5 相同直接跳过），PPT 不翻页就不花钱
  3. 退出时自动把整场笔记归纳成「会议纪要.md」
  4. 模型走 llm.py 的回退链，一个端点挂了自动换下一个

用法：
  python ~/dsh-phone/meetnote.py                      # 开会前敲这一条，散会回来说"总结"
  python ~/dsh-phone/meetnote.py --interval 15        # 15 秒看一次（默认 20）
  python ~/dsh-phone/meetnote.py --pkgs com.tencent.wemeet.app,com.tencent.mm
  python ~/dsh-phone/meetnote.py --minutes 45         # 45 分钟后自动收工
  python ~/dsh-phone/meetnote.py --no-summary         # 只要原始时间线，不生成纪要
  python ~/dsh-phone/meetnote.py --dry-run            # 只打印截到了什么，不调模型

产物：~/tmp/meet/<日期-时间>/时间线.md 和 会议纪要.md（截图默认读完就删，加 --keep-frames 保留）
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm  # noqa: E402

def _adb_serial():
    ser = os.environ.get("DSH_ADB_SER")
    if ser:
        return ser
    port = os.environ.get("DSH_ADB_PORT")
    if not port:
        try:
            port = open(os.path.expanduser("~/.dsh-adb-port")).read().strip()
        except Exception:
            port = "5556"
    return "127.0.0.1:" + (port or "5556")


ADB = ["adb", "-s", _adb_serial()]
HERE = os.path.dirname(os.path.abspath(__file__))

FRAME_PROMPT = """这是手机屏幕截图，正在开线上会议。请只提取"画面上真实存在的信息"，不要推测、不要补充常识。

判断共享内容是什么：PPT / 文档 / 白板 / 视频 / 摄像头头像墙 / 没有共享内容。

如果画面里主要是人头像、聊天区、控制栏，几乎没有可读内容，只输出：
{{"kind":"none"}}

如果共享内容与下面这段"上一次记录"实质相同（比如只是时钟、弹幕、鼠标在动），只输出：
{{"kind":"same"}}

上一次记录：
{prev}

否则输出严格 JSON：
{{"kind":"ppt|doc|whiteboard|video","title":"这页标题","points":["要点1","要点2"],"raw":"画面上的关键原文，看不清就留空"}}
"""

SUMMARY_PROMPT = """下面是一场线上会议期间，手机每 20 秒自动记录的画面文字时间线（不是完整录音，只包含屏幕上出现过的东西）。

请整理成一份中文会议纪要，Markdown 格式，包含：
1. **一句话结论**（这场会到底在讲什么）
2. **按主题分节**：每个主题列要点，合并重复内容
3. **出现的资料/链接/数字**：原样保留（BV 号、网址、人名、编号）
4. **待办或后续**：只在原文明确提到时才写，没写就写"未见明确待办"

不要编造时间线里没有的内容。时间线如下：

---
{timeline}
---
"""


def run(cmd, binary=False, timeout=60):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def foreground():
    out = run(ADB + ["shell", "dumpsys window"], timeout=30)
    for line in out.splitlines():
        if "mCurrentFocus" in line:
            # mCurrentFocus=Window{2917c42 u0 tv.danmaku.bili/com.bilibili.video.X type=1}
            s = line.split("u0 ", 1)[-1]
            pkg = s.split("/", 1)[0].strip()
            if pkg and pkg != "Window{":
                return pkg
    return "?"


# 这些是"会议 App 的按钮/提示"，不是会议内容 —— 靠它们判断"树里有字"会误判
UI_CHROME = (
    "静音", "解除静音", "取消静音", "麦克风", "扬声器", "摄像头", "开启视频", "关闭视频", "切换摄像头",
    "共享屏幕", "共享", "停止共享", "成员", "管理成员", "全体静音", "聊天", "更多", "设置", "美颜",
    "虚拟背景", "举手", "表情", "录制", "会议号", "邀请", "复制", "最小化", "挂断", "离开会议",
    "结束会议", "返回", "确定", "取消", "网络", "信号", "电量", "加入会议", "会议详情", "会议中",
    "主持人", "联席主持人", "布局", "全屏", "画中画", "语音模式", "视频模式", "文档", "白板",
)


def contentish(lines):
    """树里的字里，有多少条像"真内容"（讲义、文档正文、聊天），而不是按钮。"""
    n = 0
    for raw in lines:
        t = (raw or "").strip()
        if len(t) < 4:
            continue
        if any(c in t for c in UI_CHROME) and len(t) <= 8:
            continue        # 纯按钮文字
        if re.search(r"[\u4e00-\u9fff]{6,}", t) or len(t) >= 12:
            n += 1
    return n


def a11y_lines():
    """读无障碍树里的文字（uiautomator dump → ui_text.py），0 张图、0 视觉 token。"""
    xml = ""
    # uiautomator 第一次常常报 "could not get idle state"（页面在动），重试一次就好
    for attempt in (1, 2):
        subprocess.run(ADB + ["shell", "uiautomator", "dump", "--compressed", "/data/local/tmp/mn.xml"],
                       capture_output=True, timeout=40)
        xml = run(ADB + ["shell", "cat", "/data/local/tmp/mn.xml"], timeout=40)
        if "<?xml" in xml:
            break
        time.sleep(1.0)
    if "<?xml" not in xml:
        return []
    r = subprocess.run([sys.executable, os.path.join(HERE, "ui_text.py"), "--json"],
                       input=xml.encode("utf-8"), capture_output=True, timeout=60)
    try:
        d = json.loads(r.stdout.decode("utf-8", "replace"))
    except Exception:
        return []
    out = []
    for n in d.get("nodes") or []:
        t = (n.get("text") or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def shot(path):
    data = run(ADB + ["exec-out", "screencap", "-p"], binary=True, timeout=60)
    if not data or len(data) < 5000:
        return None
    with open(path, "wb") as f:
        f.write(data)
    return hashlib.md5(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=20)
    ap.add_argument("--pkgs", default="com.tencent.wemeet.app",
                    help="允许截图的前台包名，逗号分隔（默认腾讯会议）")
    ap.add_argument("--minutes", type=float, default=0, help="0 = 一直跑到你 Ctrl+C")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--out", default=os.path.expanduser("~/tmp/meet"))
    ap.add_argument("--no-summary", action="store_true")
    ap.add_argument("--keep-frames", action="store_true")
    ap.add_argument("--a11y", action="store_true",
                    help="先读无障碍树的文字（不截图、不花视觉 token），读不到才截图")
    ap.add_argument("--a11y-only", action="store_true",
                    help="只读文字树，永不截图")
    ap.add_argument("--keep-awake", action="store_true",
                    help="开会期间让屏幕保持常亮（截图抓的是当前屏幕，锁屏就什么都抓不到）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summarize", metavar="目录或时间线.md",
                    help="不录新的，只把已有时间线重新归纳成会议纪要")
    args = ap.parse_args()

    if args.summarize:
        src = args.summarize
        if os.path.isdir(src):
            src = os.path.join(src, "时间线.md")
        body = open(src, encoding="utf-8").read()
        r = llm.ask(SUMMARY_PROMPT.format(timeline=body), max_tokens=1600, temperature=0.3, trace=False)
        out = os.path.join(os.path.dirname(os.path.abspath(src)), "会议纪要.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write("# 会议纪要\n\n" + r["text"].strip() + "\n")
        print("会议纪要：%s" % out)
        return 0

    mode = "shot"
    if args.a11y_only:
        mode = "a11y-only"
    elif args.a11y:
        mode = "a11y"

    allow = [p.strip() for p in args.pkgs.split(",") if p.strip()]
    stamp = time.strftime("%Y%m%d-%H%M")
    outdir = os.path.join(args.out, stamp)
    os.makedirs(outdir, exist_ok=True)
    timeline = os.path.join(outdir, "时间线.md")
    frame = os.path.join(outdir, "frame.png")

    print("=== meetnote ===")
    print("只在前台是 %s 时截图；每 %.0f 秒看一次" % ("/".join(allow), args.interval))
    print("输出目录：%s" % outdir)
    if not args.dry_run and mode != "a11y-only":
        try:
            r0 = llm.ask("回复 OK", max_tokens=8, trace=False)
            print("模型自检：%s/%s" % (r0["endpoint"], r0["model"]))
        except Exception as e:
            print("模型连不上，先修网络：%s" % e)
            return 1

    if args.keep_awake:
        subprocess.run(ADB + ["shell", "svc", "power", "stayon", "true"], capture_output=True, timeout=30)
        print("已开启屏幕常亮（结束时自动恢复）")

    prev_md5 = None
    prev_rec = ""
    seen_text = set()   # 无障碍树去重：只记新出现的文字
    pages = 0
    frames = 0
    started = time.time()
    log_lines = []

    def write_timeline():
        head = "# 会议时间线（%s）\n\n" % stamp
        with open(timeline, "w", encoding="utf-8") as f:
            f.write(head + ("\n".join(log_lines) if log_lines else "_（还没有记录到内容）_\n"))

    if os.path.exists(timeline):
        pass
    try:
        while True:
            now = time.time()
            if args.minutes and (now - started) / 60.0 >= args.minutes:
                print("\n到时间了，收工")
                break
            if args.max_frames and frames >= args.max_frames:
                print("\n抓够 %d 帧，收工" % frames)
                break

            fg = foreground()
            if fg not in allow:
                print("\r[跳过] 前台是 %s，不是会议" % fg[:40], end="", flush=True)
                time.sleep(args.interval)
                continue

            label = time.strftime("%H:%M:%S")

            # —— 路线 A：读无障碍树（不截图）——
            if mode in ("a11y", "a11y-only"):
                lines = a11y_lines()
                strong = contentish(lines) >= 2   # 至少两条像正文，才算"树里有内容"
                if lines and strong:
                    new = [l for l in lines if l not in seen_text]
                    if new:
                        pages += 1
                        seen_text.update(new)
                        block = ["## [%s] 第 %d 屏 · 界面文字" % (label, pages), ""]
                        block += ["- " + l for l in new[:40]]
                        block.append("")
                        log_lines.append("\n".join(block))
                        write_timeline()
                        print("\r[%s] 记下第 %d 屏：%d 条新文字（没花视觉 token）"
                              % (label, pages, len(new)))
                    else:
                        print("\r[%s] 文字没变，跳过" % label, end="", flush=True)
                    time.sleep(args.interval)
                    continue
                # 树里只有按钮文字（共享的是图片/PPT），或是空树 → --a11y 退回截图
                if mode == "a11y-only":
                    why = "只有按钮文字" if lines else "读不到界面文字（可能被安全策略挡住）"
                    print("\r[%s] %s" % (label, why), end="", flush=True)
                    time.sleep(args.interval)
                    continue

            md5 = shot(frame)
            if not md5:
                print("\r[跳过] 截屏失败（adb 掉线？跑 fix-adb.sh）", end="", flush=True)
                time.sleep(args.interval)
                continue
            if md5 == prev_md5:
                print("\r[等] 画面没变，跳过（已省一次读图）", end="", flush=True)
                time.sleep(args.interval)
                continue
            prev_md5 = md5
            frames += 1

            if args.dry_run:
                print("\n[%s] 截到一帧（%d KB），前台 %s" % (label, os.path.getsize(frame) // 1024, fg))
                time.sleep(args.interval)
                continue

            try:
                r = llm.ask(FRAME_PROMPT.format(prev=prev_rec or "（无）"), image_path=frame,
                            max_tokens=700, temperature=0.1, trace=False)
                txt = (r.get("text") or "").strip()
            except Exception as e:
                print("\n[%s] 读图失败：%s" % (label, str(e)[:120]))
                time.sleep(args.interval)
                continue

            txt = txt.strip().strip("`").replace("json\n", "")
            try:
                obj = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
            except Exception:
                obj = {"kind": "unknown", "raw": txt[:500]}

            kind = obj.get("kind")
            if kind in ("none", "same"):
                print("\r[%s] 无新内容（%s）" % (label, kind), end="", flush=True)
            else:
                pages += 1
                title = obj.get("title") or "(无标题)"
                pts = obj.get("points") or []
                raw = obj.get("raw") or ""
                block = ["## [%s] 第 %d 屏 · %s" % (label, pages, title), ""]
                for p in pts:
                    block.append("- " + str(p))
                if raw:
                    block += ["", "> 原文：`%s`" % raw.replace("\n", " ")]
                block.append("")
                log_lines.append("\n".join(block))
                prev_rec = title + "｜" + "；".join(str(p) for p in pts[:3])
                write_timeline()
                print("\r[%s] 记下第 %d 屏：%s" % (label, pages, title[:30]))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n你按了 Ctrl+C，收工")
    finally:
        if args.keep_awake:
            subprocess.run(ADB + ["shell", "svc", "power", "stayon", "false"], capture_output=True, timeout=30)
        write_timeline()
        print("时间线：%s（%d 屏，抓了 %d 帧）" % (timeline, pages, frames))
        if not args.keep_frames and os.path.exists(frame):
            os.remove(frame)
        if pages and not args.no_summary and not args.dry_run:
            body = "\n".join(log_lines)
            try:
                r = llm.ask(SUMMARY_PROMPT.format(timeline=body), max_tokens=1600, temperature=0.3, trace=False)
                path = os.path.join(outdir, "会议纪要.md")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("# 会议纪要（%s）\n\n" % stamp + r["text"].strip() + "\n")
                print("会议纪要：%s" % path)
                print("（用 %s/%s 生成）" % (r["endpoint"], r["model"]))
            except Exception as e:
                print("纪要生成失败：%s" % str(e)[:150])
    return 0


if __name__ == "__main__":
    sys.exit(main())
