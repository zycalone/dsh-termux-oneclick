#!/usr/bin/env python3
"""从 docx 里抽出的题目截图中，读出题干与「标红的正确选项」。
用法: python read_quiz_imgs.py <docx> [起始图号]
输出: 逐题 JSON + 汇总表
"""
import base64
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

BASE = os.environ.get("DSH_GW", "http://127.0.0.1:8787/v1/chat/completions")
KEY = os.environ.get("DSH_KEY", "local-noop")
MODEL = os.environ.get("DSH_VISION_MODEL", "glm-5v-turbo")

PROMPT = (
    "这是一张在线答题页面/试卷的手机截图。\n"
    "请仔细看清图片，输出以下三项，用纯文本：\n"
    "题目：<把题干原文完整抄下来>\n"
    "选项：<把每个选项原文按 A/B/C/D 顺序抄下来，没有的不要编>\n"
    "标记：<哪个选项被高亮/标红/标注为正确答案；抄它开头的字母，如 C；若图中没有标记就写 无>\n"
    "只依据图片内容，不要猜。看不清就写 看不清。"
)


def ask_image(png_bytes, mime="image/png"):
    b64 = base64.b64encode(png_bytes).decode()
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, b64)}},
        ]}],
        "max_tokens": 700,
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(BASE, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return (d["choices"][0]["message"].get("content") or "").strip()


def main():
    src = sys.argv[1]
    z = zipfile.ZipFile(src)
    names = [n for n in z.namelist() if n.startswith("word/media/") and not n.endswith("/")]
    # 按数字顺序: image1, image2 ... image28, 但 image3 是 jpeg
    def key(n):
        m = re.search(r"image(\d+)\.", n)
        return int(m.group(1)) if m else 999
    names.sort(key=key)
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    targets = [n for n in names if key(n) >= start]

    def work(n):
        data = z.read(n)
        mime = "image/jpeg" if n.lower().endswith((".jpg", ".jpeg")) else "image/png"
        try:
            txt = ask_image(data, mime)
        except Exception as e:  # noqa: BLE001
            txt = "ERROR: %s" % e
        return n, txt

    out = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for n, txt in ex.map(work, targets):
            print("=" * 60)
            print("#", n)
            print(txt)
            sys.stdout.flush()
            out.append({"img": n, "text": txt})
    with open("quiz-answers.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n已存 quiz-answers.json")


if __name__ == "__main__":
    main()
