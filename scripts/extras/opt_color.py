import io
import json
import re
import zipfile

import numpy as np
from PIL import Image

SRC = r"C:\Users\15362\Downloads\青年学生考评自测（学生自测）操作手册.docx"
z = zipfile.ZipFile(SRC)


def bands(dark_rows, h):
    act = dark_rows
    out = []
    start = None
    gap = 0
    y = 0
    while y < h:
        if act[y]:
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
        y += 1
    return out


res = {}
for n in sorted(z.namelist()):
    m = re.search(r"image(\d+)\.png$", n)
    if not m or not (6 <= int(m.group(1)) <= 25):
        continue
    img = Image.open(io.BytesIO(z.read(n))).convert("RGB")
    a = np.array(img).astype(int)
    h, w = a.shape[:2]
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    sat = mx - mn
    gray = np.array(img.convert("L"))
    dark_rows = (gray < 150).sum(axis=1) > max(2, int(w * 0.004))
    bs = bands(dark_rows, h)
    rows = []
    for (y0, y1) in bs[-3:]:
        seg = a[y0:y1 + 1]
        s = sat[y0:y1 + 1]
        # 彩色像素（饱和度>40）计数，以及其中最"红"的样本
        colored = int((s > 40).sum())
        redish = int(((seg[:, :, 0] - (seg[:, :, 1] + seg[:, :, 2]) / 2) > 25).sum())
        greenish = int(((seg[:, :, 1] - (seg[:, :, 0] + seg[:, :, 2]) / 2) > 25).sum())
        rows.append({"y": [int(y0), int(y1)], "colored": colored, "red": redish, "green": greenish})
    res[n.split("/")[-1]] = rows
    print(n.split("/")[-1], json.dumps(rows, ensure_ascii=False))
json.dump(res, open(r"D:\shots\optcolor.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
