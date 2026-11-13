#!/usr/bin/env python3
"""minutetool.py —— 转写稿 → 纪要 / 学习笔记（两种模式，走 llm.py 回退链）

场景 B 的收尾工具：腾讯会议「云录制 / 转写」或其它录音转写出来的文字稿，
在这里一键变成能直接看的东西。**不碰屏幕、不截图、不吃视觉 token。**

两种模式：
  --kind meeting  （默认）会议纪要：一句话结论 / 结论与决策 / 待办（谁·做什么·何时）/ 数字与资料 / 风险分歧
  --kind lecture  学习笔记：本次主线 / 核心概念与定义 / 公式与结论 / 例题与解法 / 可能考点 / 易错点 / 没听懂的地方
  --kind auto     先让模型判断这是会议还是讲座，再按对应模式处理

输入格式（自动识别，不需要额外依赖）：
  .txt / .md        纯文本
  .srt / .vtt       字幕（自动剥掉时间轴和序号）
  .docx             Word（用标准库解压读 XML，不装 python-docx）
  .pdf              需要系统里有 pdftotext（Termux: pkg install poppler）

用法：
  python ~/dsh-phone/minutetool.py 转写稿.txt                  # 会议模式
  python ~/dsh-phone/minutetool.py 讲座.srt --kind lecture      # 讲座模式
  python ~/dsh-phone/minutetool.py 录音.docx --kind auto --title "航模基础第二讲"
  cat 稿子.txt | python ~/dsh-phone/minutetool.py -             # 从标准输入读

产物：~/tmp/notes/<标题-时间>/<meeting|lecture>.md（同时打印摘要前几行）
"""
import argparse
import os
import re
import subprocess
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm  # noqa: E402

CHUNK_MEETING = """这是一场会议转写稿的第 {i}/{n} 段。请只提取稿子里**明确说过**的信息，不要推测、不要补充常识。

分条列出：
1. 讨论了什么议题
2. 得出的结论或决定（谁定的）
3. 待办（谁 / 做什么 / 什么时候）
4. 出现的数字、日期、资料名、人名（原样保留）

没有的内容不要编。输出中文分条，尽量短。

稿子：
---
{chunk}
---"""

CHUNK_LECTURE = """这是一场讲座/课堂转写稿的第 {i}/{n} 段。请只提取稿子里**明确讲过**的内容，不要推测、不要补充你自己的知识。

分条列出：
1. 讲了哪些知识点（给知识点起小标题）
2. 概念的定义、公式、结论（原样保留术语、符号、人名、书名）
3. 举的例子或例题（谁在什么条件下得到什么结果）
4. 讲者特别强调、反复提醒的地方

看不懂、听不清的地方写"[听不清]"，不要猜。输出中文分条。

稿子：
---
{chunk}
---"""

MERGE_MEETING = """下面是一份会议转写稿分段提取出的内容（可能有重复和零碎）。请合并成一份中文会议纪要，Markdown，结构固定：

## 一句话结论
## 结论与决策
## 待办清单
| 谁 | 做什么 | 时间 |
（稿子里没提到就写"未提及"，不要编）
## 数字与资料
## 风险与不同意见

要求：合并重复项；保留所有数字、人名、资料名原文；不确定的标 ⚠️。

分段内容：
---
{body}
---"""

MERGE_LECTURE = """下面是一场讲座/课堂转写稿分段提取出的内容（可能有重复和零碎）。请合并成一份中文学习笔记，Markdown，结构固定：

## 这次讲了什么（3 句以内）
## 核心概念与定义
## 公式 / 结论 / 步骤
## 例子与例题
## 可能考的点和问法
## 容易混 / 容易错的地方
## 我没听懂或稿子里缺失的部分

要求：术语保留原文；合并重复项；**不要引入稿子里没有的知识**（这一条最重要，你不是在补课）；
缺信息的直说，不要用猜测填满。

分段内容：
---
{body}
---"""

KIND_PROBE = """下面是一段转写稿的开头。判断它更像"会议/工作讨论"，还是"讲座/课堂/培训"。

只输出 JSON，不要别的话：
{{"kind":"meeting","why":"一句话理由"}}
或
{{"kind":"lecture","why":"一句话理由"}}

稿子开头：
---
{sample}
---"""


def read_text(path):
    low = path.lower()
    if low.endswith((".txt", ".md", ".markdown", ".csv", ".log")):
        return open(path, encoding="utf-8", errors="replace").read()
    if low.endswith((".srt", ".vtt")):
        raw = open(path, encoding="utf-8", errors="replace").read()
        keep = []
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.isdigit():
                continue
            if s.upper().startswith("WEBVTT") or s.startswith("NOTE "):
                continue
            if re.match(r"^[\d:,.]+\s*-->", s):  # 00:00:01,000 --> 00:00:03,000
                continue
            keep.append(s)
        # 合并相邻重复行（自动字幕常见的滚动重复）
        out = []
        for s in keep:
            if not out or out[-1] != s:
                out.append(s)
        return "\n".join(out)
    if low.endswith(".docx"):
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<[^>]+>", "", xml)
        return re.sub(r"\n{3,}", "\n\n", xml)
    if low.endswith(".pdf"):
        r = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, timeout=180)
        if r.returncode != 0:
            raise SystemExit("PDF 需要 pdftotext：pkg install poppler（或先转成 txt/docx）")
        return r.stdout.decode("utf-8", "replace")
    raise SystemExit("不认识的格式：%s（支持 txt/md/srt/vtt/docx/pdf）" % path)


def chunk_text(text, size=5000):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        paras = [text]
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > size:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        chunks.append(cur)
    # 段落特别长的再按字符切
    out = []
    for c in chunks:
        while len(c) > size * 2:
            out.append(c[:size * 2])
            c = c[size * 2:]
        out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="转写稿路径，或 - 表示从标准输入读")
    ap.add_argument("--kind", choices=["meeting", "lecture", "auto"], default="meeting")
    ap.add_argument("--title", default="")
    ap.add_argument("--out", default=os.path.expanduser("~/tmp/notes"))
    ap.add_argument("--chunk", type=int, default=5000, help="每段字符数（默认 5000）")
    ap.add_argument("--dry-run", action="store_true", help="只切段、不调模型")
    args = ap.parse_args()

    if args.path == "-":
        text = sys.stdin.read()
        title = args.title or "stdin"
    else:
        text = read_text(args.path)
        title = args.title or os.path.splitext(os.path.basename(args.path))[0]
    text = text.strip()
    if not text:
        raise SystemExit("稿子是空的")

    stamp = time.strftime("%Y%m%d-%H%M")
    kind = args.kind
    print("=== minutetool ===")
    print("稿子：%d 字%s" % (len(text), "（%s）" % args.path if args.path != "-" else ""))

    if kind == "auto":
        r = llm.ask(KIND_PROBE.format(sample=text[:2500]), max_tokens=120, temperature=0.1, trace=False)
        raw = r["text"]
        try:
            import json as _json
            kind = _json.loads(raw[raw.find("{"):raw.rfind("}") + 1]).get("kind", "meeting")
        except Exception:
            kind = "lecture" if "讲座" in raw or "课堂" in raw else "meeting"
        print("自动判断：%s（%s）" % (kind, " ".join(raw.split())[:80]))

    chunks = chunk_text(text, args.chunk)
    print("分 %d 段，模式：%s" % (len(chunks), kind))
    if args.dry_run:
        for i, c in enumerate(chunks, 1):
            print("  [%d] %d 字 → %s" % (i, len(c), " ".join(c.split())[:60]))
        return 0

    per_chunk = CHUNK_MEETING if kind == "meeting" else CHUNK_LECTURE
    parts = []
    for i, c in enumerate(chunks, 1):
        r = llm.ask(per_chunk.format(i=i, n=len(chunks), chunk=c), max_tokens=1200, temperature=0.2, trace=False)
        print("  [%d/%d] %d 字 → %s" % (i, len(chunks), len(c), (r["model"] or "")[:20]))
        parts.append("### 第 %d 段\n%s" % (i, r["text"].strip()))

    body = "\n\n".join(parts)
    merge = MERGE_MEETING if kind == "meeting" else MERGE_LECTURE
    r = llm.ask(merge.format(body=body), max_tokens=2200, temperature=0.3, trace=False)

    outdir = os.path.join(args.out, "%s-%s" % (title.replace("/", "_")[:40], stamp))
    os.makedirs(outdir, exist_ok=True)
    final = os.path.join(outdir, "%s.md" % kind)
    with open(final, "w", encoding="utf-8") as f:
        f.write("# %s（%s）\n\n" % (title, "会议纪要" if kind == "meeting" else "学习笔记"))
        f.write(r["text"].strip() + "\n")
    raw_path = os.path.join(outdir, "分段提取.md")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(body + "\n")

    print("\n成品：%s（用 %s/%s 合并）" % (final, r["endpoint"], r["model"]))
    print("分段原文：%s" % raw_path)
    print("\n—— 前 20 行预览 ——")
    for line in r["text"].strip().splitlines()[:20]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
