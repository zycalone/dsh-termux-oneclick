#!/usr/bin/env python3
"""test_fallback_offline.py —— 不用真端点，离线验证 llm.py 的回退链

跑法（先起假网关）：
  python scripts/pc/mock_gw.py 18080 &
  python scripts/pc/test_fallback_offline.py

它会检查 8 件事：
  1. 500 端点 + 空回复端点 → 能跳到好端点
  2. 跳过的坏端点被记录下来（tried）
  3. 视觉链同样能回退
  4. jpg 被识别成 image/jpeg（mime 不写对，有些端点会拒图）
  5. 指定模型不存在 → 放开模型限制再试一轮
  6. 全部挂掉 → 报错里列得出端点名和原因
  7. vidnote.vision() 走回退链
  8. vidnote.post() 模型不存在也能拿到回复
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PHONE = os.environ.get("DSH_PHONE") or os.path.join(os.path.dirname(HERE), "phone")
sys.path.insert(0, PHONE)

BASE = os.environ.get("MOCK_BASE", "http://127.0.0.1:18080")
IMG = os.path.join(os.path.dirname(HERE), "..", "tmp_test.jpg")


def eps(*items):
    parts = []
    for name, path, models, vmodels in items:
        parts.append(
            '{"name":"%s","base":"%s%s","key":"k","models":%s,"vision_models":%s}'
            % (name, BASE, path, models, vmodels)
        )
    return '{"timeout":10,"retries_per_endpoint":1,"endpoints":[%s]}' % ",".join(parts)


fails = []


def check(name, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + name + (("  " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


os.environ["DSH_ENDPOINTS"] = eps(
    ("500端点", "/v1/fail/chat/completions", '["m1"]', '["v1"]'),
    ("空荡端点", "/v1/empty/chat/completions", '["m2"]', '["v2"]'),
    ("好端点", "/v1/ok/chat/completions", '["good-text"]', '["good-vision"]'),
)
import llm  # noqa: E402

print("== 1) 文本回退：500 → 空回复 → 好端点 ==")
r = llm.ask("你好", max_tokens=32, trace=False)
print("   ", r["text"], "| 走的是", r["endpoint"], "/", r["model"])
print("    tried =", r["tried"])
check("最终用好端点", r["endpoint"] == "好端点")
check("跳过了 2 个坏端点", len(r["tried"]) >= 2, r["tried"])

print("== 2) 视觉回退 + mime 正确 ==")
open(IMG, "wb").write(b"\xff\xd8\xff\xe0" + b"0" * 400)
r2 = llm.ask("看图", image_path=IMG, max_tokens=32, trace=False)
print("   ", r2["text"])
check("视觉链也跳到好端点", r2["endpoint"] == "好端点")
check("jpg 认成 image/jpeg", "image/jpeg" in r2["text"], r2["text"])
os.remove(IMG)

print("== 3) 指定模型全挂 → 放开模型限制重试 ==")
r3 = llm.ask("你好", model="不存在的模型", max_tokens=32, trace=False)
print("   ", r3["text"], "| 走的是", r3["endpoint"], "/", r3["model"])
check("换到了别的模型", r3["model"] in ("m1", "m2", "good-text"), r3["model"])

print("== 4) 全部挂掉：报错要列原因 ==")
os.environ["DSH_ENDPOINTS"] = ('{"timeout":5,"retries_per_endpoint":1,"endpoints":'
                               '[{"name":"死端口","base":"http://127.0.0.1:9/v1/chat/completions",'
                               '"key":"k","models":["m"]}]}')
importlib.reload(llm)
try:
    llm.ask("x", max_tokens=8, trace=False)
    check("全挂时应抛错", False)
except RuntimeError as e:
    print("    ", str(e)[:120])
    msg = str(e).lower()
    check("报错含端点名与原因", "死端口" in str(e) and any(
        k in msg for k in ("refused", "111", "积极拒绝", "拒绝", "connect")))

print("== 5) vidnote.vision() / post() 走回退链 ==")
os.environ["DSH_ENDPOINTS"] = eps(
    ("500端点", "/v1/fail/chat/completions", '["m1"]', '["v1"]'),
    ("好端点", "/v1/ok/chat/completions", '["good-text"]', '["good-vision"]'),
)
importlib.reload(llm)
import vidnote  # noqa: E402
importlib.reload(vidnote)
open(IMG, "wb").write(b"\xff\xd8\xff\xe0" + b"0" * 400)
v = vidnote.vision(IMG, "00:10")
os.remove(IMG)
print("    vision:", v)
check("vidnote.vision 走回退链", "MOCK_OK" in v and "image/jpeg" in v, v)
s = vidnote.post({"model": "随便一个不存在的", "messages": [{"role": "user", "content": "汇总"}],
                  "max_tokens": 64, "temperature": 0.1})
print("    post:", s)
check("vidnote.post 模型不存在也能拿到回复", "MOCK_OK" in s, s)

print()
print("结果：%d 项失败" % len(fails) if fails else "结果：全部通过 ✅")
sys.exit(1 if fails else 0)
