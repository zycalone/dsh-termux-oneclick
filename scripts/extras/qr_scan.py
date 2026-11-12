import io
import os
import sys
import zipfile

import cv2
import numpy as np

src = sys.argv[1]
z = zipfile.ZipFile(src)
det = cv2.QRCodeDetector()
outdir = os.path.join(os.path.dirname(src), "media")
os.makedirs(outdir, exist_ok=True)
hits = []
for n in sorted(z.namelist()):
    if not n.startswith("word/media/") or n.endswith("/"):
        continue
    data = z.read(n)
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        print(n, "decode-fail")
        continue
    h, w = img.shape[:2]
    txt, pts, _ = det.detectAndDecode(img)
    ok = bool(txt)
    if not ok:
        # try upscale for small codes
        big = cv2.resize(img, (w * 3, h * 3), interpolation=cv2.INTER_NEAREST)
        txt, pts, _ = det.detectAndDecode(big)
        ok = bool(txt)
    print("%-24s %5dx%-5d qr=%s %s" % (os.path.basename(n), w, h, ok, txt[:90] if txt else ""))
    if ok:
        with open(os.path.join(outdir, os.path.basename(n)), "wb") as f:
            f.write(data)
        hits.append((os.path.basename(n), txt))
print("\nQR 命中:", hits)
