import base64
import io
import json
import sys
import re
import urllib.request
import zipfile

import numpy as np
from PIL import Image

SRC = r"C:\Users\15362\Downloads\青年学生考评自测（学生自测）操作手册.docx"
URL = "http://127.0.0.1:8787/v1/chat/completions"
MODEL = "glm-5v-turbo"
z = zipfile.ZipFile(SRC)

STEMS = json.load(open(r"D:\shots\ocr_result.json", encoding="utf-8"))
stem_map = {}
for r in STEMS:
    n = r["img"].split("/")[-1]
    m = re.search(r"题干：(.*)", r["text"])
    stem_map[n] = (m.group(1).strip() if m else "")


def ask(png, prompt, mt=200):
    b64 = base64.b64encode(png).decode()
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
    ]}], "max_tokens": mt, "temperature": 0.05}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer local-noop"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return (d["choices"][0]["message"].get("content") or "").strip()


def bands(gray, w, h):
    dark_rows = (gray < 150).sum(axis=1) > max(2, int(w * 0.004))
    out, start, gap, end = [], None, 0, 0
    for y in range(h):
        if dark_rows[y]:
            if start is None:
                start = y
            gap = 0
            end = y
        elif start is not None:
            gap += 1
            if gap >= 5:
                if end - start >= 6:
                    out.append((start, end))
                start = None
    if start is not None and end - start >= 6:
        out.append((start, end))
    return out


rows = []
for i in range(6, 26):
    name = "image%d.png" % i
    img = Image.open(io.BytesIO(z.read("word/media/" + name))).convert("RGB")
    a = np.array(img).astype(int)
    h, w = a.shape[:2]
    gray = np.array(img.convert("L"))
    bs = bands(gray, w, h)
    tail = bs[-3:]
    warm = []
    for (y0, y1) in tail:
        seg = a[y0:y1 + 1]
        cnt = int(((seg[:, :, 0] - (seg[:, :, 1] + seg[:, :, 2]) / 2) > 25).sum())
        warm.append(cnt)
    letter, atext = None, ""
    if max(warm) > 800:
        idx = warm.index(max(warm))
        letter = "ABC"[idx]
        y0, y1 = tail[idx]
        crop = img.crop((0, max(0, y0 - 3), w, min(h, y1 + 4)))
        crop = crop.resize((crop.width * 5, crop.height * 5), Image.LANCZOS)
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        atext = ask(buf.getvalue(), "只输出图片里这一行的文字内容，逐字抄写，不要解释。")
    qno = i - 5
    rows.append({"q": qno, "img": name, "stem": stem_map.get(name, ""),
                 "answer": letter or "?", "atext": atext, "warm": warm})
    print("%2d %-12s %-3s %-20s | %s" % (qno, name, letter or "?", atext.replace("\n", " ")[:20],
                                         stem_map.get(name, "")[:30]))

with open(r"D:\shots\anti_aids_answers.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)

lines = ["| 题号 | 题目 | 正确选项 |", "|---|---|---|"]
for r in rows:
    lines.append("| %d | %s | **%s** %s |" % (r["q"], r["stem"], r["answer"],
                                              r["atext"].replace("\n", " ")))
OUT = sys.argv[1] if len(sys.argv) > 1 else "answers.md"
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\nsaved", OUT)
