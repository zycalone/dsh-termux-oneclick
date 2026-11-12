#!/data/data/com.termux/files/usr/bin/bash
# act_batch —— 一次执行一串动作（JSON），带失败中断与干跑预览
#
# 用法：
#   python act_batch.py steps.json              # 真跑
#   python act_batch.py steps.json --dry-run    # 只打印将要执行的命令
#   python act_batch.py steps.json --keep-going # 某步失败也继续
#
# steps.json 例：
# [
#   {"act": "cur"},
#   {"act": "open",      "pkg": "com.tencent.mm"},
#   {"act": "wait-text", "text": "微信",  "timeout": 15},
#   {"act": "tap-text",  "text": "通讯录", "verify": true},
#   {"act": "type",      "text": "你好"},
#   {"act": "swipe",     "args": [540, 1800, 540, 900, 300]},
#   {"act": "key",       "code": "KEYCODE_BACK"},
#   {"act": "sleep",     "seconds": 1},
#   {"act": "shot"},
#   {"act": "text",      "opts": ["--click"]}
# ]
#
# 为什么这么做：让模型一次性输出多步，本地顺序执行，少几个来回就少几次 token 与误点。

import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APPCTL = os.path.join(HERE, "appctl.sh")


def build(step):
    act = (step.get("act") or "").strip()
    if act in ("cur", "text", "apps", "shot"):
        cmd = ["bash", APPCTL, act] + [str(x) for x in step.get("opts", [])]
    elif act == "open":
        cmd = ["bash", APPCTL, "open", str(step.get("pkg", ""))]
    elif act == "tap":
        cmd = ["bash", APPCTL, "tap", str(step.get("x")), str(step.get("y"))]
    elif act == "tap-text":
        cmd = ["bash", APPCTL, "tap-text", str(step.get("text", ""))]
        if step.get("verify"):
            cmd += ["--verify"]
        if step.get("tries"):
            cmd += ["--tries", str(step["tries"])]
    elif act == "type":
        cmd = ["bash", APPCTL, "type", str(step.get("text", ""))]
    elif act == "key":
        cmd = ["bash", APPCTL, "key", str(step.get("code", "KEYCODE_BACK"))]
    elif act == "swipe":
        cmd = ["bash", APPCTL, "swipe"] + [str(x) for x in step.get("args", [])]
    elif act == "wait-text":
        cmd = ["bash", APPCTL, "wait-text", str(step.get("text", "")), str(step.get("timeout", 15))]
    elif act == "kb-save":
        cmd = ["bash", APPCTL, "kb", "save", str(step.get("name", "page"))]
    elif act == "kb-get":
        cmd = ["bash", APPCTL, "kb", "get", str(step.get("name", "page"))]
    else:
        return None
    return cmd


def main():
    if len(sys.argv) < 2:
        print(__doc__ or "需要 steps.json")
        return 2
    path = sys.argv[1]
    dry = "--dry-run" in sys.argv
    keep = "--keep-going" in sys.argv
    steps = json.load(open(path, encoding="utf-8"))
    if isinstance(steps, dict):
        steps = steps.get("steps", [])
    ok = 0
    for idx, step in enumerate(steps, 1):
        act = step.get("act", "?")
        if act == "sleep":
            sec = float(step.get("seconds", 1))
            print("[%d] sleep %ss" % (idx, sec))
            if not dry:
                import time

                time.sleep(sec)
            ok += 1
            continue
        cmd = build(step)
        if cmd is None:
            print("[%d] 跳过未知动作: %s" % (idx, act))
            if not keep:
                return 3
            continue
        label = " ".join(shlex.quote(c) for c in cmd[2:])
        if dry:
            print("[%d] DRY  appctl %s" % (idx, label))
            ok += 1
            continue
        print("[%d] 执行 appctl %s" % (idx, label))
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if out:
            print("    " + out.replace("\n", "\n    "))
        if p.returncode != 0:
            if err:
                print("    ! " + err.replace("\n", "\n    "))
            print("[%d] 失败 rc=%d，%s" % (idx, p.returncode, "继续" if keep else "中止"))
            if not keep:
                return p.returncode
        else:
            ok += 1
    print("\n完成 %d/%d 步" % (ok, len(steps)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
