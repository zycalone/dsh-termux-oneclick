#!/usr/bin/env python3
"""see_screen.py —— 抓当前屏幕并用视觉模型读出上面有什么（核对界面用）
用法: python see_screen.py [提问]
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/dsh-phone"))
from vidnote import post  # noqa: E402

q = sys.argv[1] if len(sys.argv) > 1 else "把屏幕上显示的所有文字逐条读出来，并说明这是什么界面。"
fp = os.path.expanduser("~/tmp/see_screen.png")
subprocess.run(["adb", "-s", "127.0.0.1:5556", "exec-out", "screencap", "-p"],
               stdout=open(fp, "wb"), stderr=subprocess.DEVNULL, timeout=60)
print("截图:", fp, os.path.getsize(fp), "字节")
import base64  # noqa: E402

b64 = base64.b64encode(open(fp, "rb").read()).decode()
print(post({"model": "glm-5v-turbo", "messages": [{"role": "user", "content": [
    {"type": "text", "text": q},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
]}], "max_tokens": 900, "temperature": 0.1}))
