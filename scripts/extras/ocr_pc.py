import base64
import io
import json
import re
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

SRC = r"C:\Users\15362\Downloads\青年学生考评自测（学生自测）操作手册.docx"
URL = "http://127.0.0.1:8787/v1/chat/completions"
MODEL = "glm-5v-turbo"

PROMPT = (
    "这是一张手机截图。请严格按下面的格式输出，不要多余的话：\n"
    "页面：<填表页/考前须知/考试题目/成绩页/证书页/其他>\n"
    "题干：<若含题目，逐字抄写题干；否则写 无>\n"
    "选项：<A. xxx / B. xxx / C. xxx 分行列出；否则写 无>\n"
    "红字：<哪个选项的文字显示为红色（正确答案）；只写字母如 B；若没有红色文字写 无>\n"
    "只依据图片，不要推测。"
)


def call(png_bytes, mime):
    b64 = base64.b64encode(png_bytes).decode()
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, b64)}},
        ]}],
        "max_tokens": 800,
        "temperature": 0.05,
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer local-noop"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return (d["choices"][0]["message"].get("content") or "").strip()


def prep(data):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if im.width < 900:
        im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue(), im.size


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 28
    z = zipfile.ZipFile(SRC)

    def key(n):
        m = re.search(r"image(\d+)\.", n)
        return int(m.group(1)) if m else 999

    names = sorted([n for n in z.namelist()
                    if n.startswith("word/media/") and not n.endswith("/")], key=key)
    targets = [n for n in names if lo <= key(n) <= hi]

    def work(n):
        data = z.read(n)
        png, size = prep(data)
        try:
            txt = call(png, "image/png")
        except Exception as e:  # noqa: BLE001
            txt = "ERROR %s" % e
        return n, size, txt

    out = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for n, size, txt in ex.map(work, targets):
            print("=" * 70)
            print("#", n, size)
            print(txt)
            sys.stdout.flush()
            out.append({"img": n, "size": list(size), "text": txt})
    with open(r"D:\shots\ocr_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nsaved D:\\shots\\ocr_result.json")


if __name__ == "__main__":
    main()
