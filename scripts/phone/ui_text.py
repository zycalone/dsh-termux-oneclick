import sys, re, xml.etree.ElementTree as ET

raw = sys.stdin.read()
i = raw.find('<?xml')
if i < 0:
    print("NO_DUMP")
    sys.exit(0)
try:
    root = ET.fromstring(raw[i:])
except ET.ParseError as e:
    print("BAD_XML:", e)
    sys.exit(0)

rows = []
for n in root.iter('node'):
    label = (n.get('text') or '').strip() or (n.get('content-desc') or '').strip()
    if not label:
        continue
    m = re.match(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]', n.get('bounds') or '')
    if not m:
        continue
    x1, y1, x2, y2 = map(int, m.groups())
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    flags = []
    if n.get('clickable') == 'true':
        flags.append('可点')
    elif n.get('scrollable') == 'true':
        flags.append('可滚')
    cls = (n.get('class') or '').split('.')[-1]
    pkg = n.get('package') or ''
    rows.append("[%s] %s <%s> @%d,%d" % ('/'.join(flags) or '-', label[:60], cls, cx, cy))

print('\n'.join(rows) if rows else 'EMPTY')
