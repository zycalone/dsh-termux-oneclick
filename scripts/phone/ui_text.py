import json
import re
import sys
import xml.etree.ElementTree as ET

"""
把 uiautomator dump 的 XML 变成模型好看的形式。

用法：
  ui_text.py                 # 全部有文字的元素（默认，含坐标/可点标记）
  ui_text.py --click         # 只留可点元素（省 token，最常用）
  ui_text.py --json          # 结构化输出，方便模型一次规划多步动作
  ui_text.py --max 40        # 限制条数
  ui_text.py --scroll        # 只留可滚动容器（找列表用）
"""

argv = sys.argv[1:]
only_click = "--click" in argv
as_json = "--json" in argv
only_scroll = "--scroll" in argv
max_rows = 0
if "--max" in argv:
    try:
        max_rows = int(argv[argv.index("--max") + 1])
    except (IndexError, ValueError):
        max_rows = 0

raw = sys.stdin.read()
i = raw.find("<?xml")
if i < 0:
    print("NO_DUMP")
    sys.exit(0)
try:
    root = ET.fromstring(raw[i:])
except ET.ParseError as e:
    print("BAD_XML:", e)
    sys.exit(0)

rows = []
seen = set()
for n in root.iter("node"):
    label = (n.get("text") or "").strip() or (n.get("content-desc") or "").strip()
    if not label:
        continue
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", n.get("bounds") or "")
    if not m:
        continue
    x1, y1, x2, y2 = map(int, m.groups())
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    clickable = n.get("clickable") == "true"
    scrollable = n.get("scrollable") == "true"
    if only_click and not clickable:
        continue
    if only_scroll and not scrollable:
        continue
    # 同标签同位置去重（很多容器会给子节点重复 text）
    key = (label, cx // 8, cy // 8)
    if key in seen:
        continue
    seen.add(key)
    rows.append({
        "text": label[:120],
        "class": (n.get("class") or "").split(".")[-1],
        "cx": cx,
        "cy": cy,
        "bounds": [x1, y1, x2, y2],
        "clickable": clickable,
        "scrollable": scrollable,
        "pkg": n.get("package") or "",
    })

if max_rows and len(rows) > max_rows:
    rows = rows[:max_rows]

if as_json:
    print(json.dumps({"count": len(rows), "nodes": rows}, ensure_ascii=False, indent=1))
    sys.exit(0)

if not rows:
    print("EMPTY")
    sys.exit(0)

lines = []
for r in rows:
    flags = []
    if r["clickable"]:
        flags.append("可点")
    elif r["scrollable"]:
        flags.append("可滚")
    lines.append("[%s] %s <%s> @%d,%d" % ("/".join(flags) or "-", r["text"][:60], r["class"], r["cx"], r["cy"]))
print("\n".join(lines))
