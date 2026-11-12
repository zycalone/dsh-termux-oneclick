import glob, json, os, subprocess, sys, time

sess = glob.glob(os.path.expanduser("~/.dsh/sessions/*/session-*/session.v4.jsonl.zstd"))
rows = []
for p in sess:
    try:
        raw = subprocess.run(["zstd", "-dc", p], capture_output=True, timeout=60).stdout
    except Exception:
        continue
    msgs = []
    last = 0
    for line in raw.split(b"\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        t = r.get("time") or 0
        if t:
            last = max(last, t)
        if r.get("type") == "agent/inbox/spliced":
            for ins in (r.get("data") or {}).get("inserted") or []:
                if ins.get("role") == "user":
                    for c in ins.get("content") or []:
                        if c.get("type") == "text":
                            msgs.append(("U", t, c.get("text", "")))
        elif r.get("type") in ("message", "assistant/message"):
            d = r.get("data") or {}
            if d.get("role") == "assistant":
                txt = ""
                for c in (d.get("content") or []):
                    if isinstance(c, dict) and c.get("type") == "text":
                        txt += c.get("text", "")
                if txt:
                    msgs.append(("A", t, txt))
    if not msgs:
        continue
    rows.append((last, p, msgs))

rows.sort(key=lambda x: -x[0])
for last, p, msgs in rows[:8]:
    ts = time.strftime("%H:%M:%S", time.localtime(last / 1000))
    print("=" * 70)
    print("会话 %s  最后活动 %s  消息数 %d" % (os.path.basename(os.path.dirname(p))[:20], ts, len(msgs)))
    print("路径: %s" % p)
    for role, t, txt in msgs[-8:]:
        tt = time.strftime("%H:%M", time.localtime(t / 1000)) if t else "??"
        one = " ".join(txt.split())
        print("  [%s %s] %s" % (tt, role, one[:300]))
