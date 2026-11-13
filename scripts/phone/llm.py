#!/usr/bin/env python3
"""llm.py —— 多端点 / 多模型回退链（手机本地跑，只用标准库）

为什么要它：单端点一挂，整条流水线全废。这里把「端点 × 模型」排成一条链，
按顺序试，谁先回来用谁；HTTP 错误、超时、空回复、429 都会自动跳到下一个。

配置（优先级从高到低）：
  1) 环境变量 DSH_ENDPOINTS —— 一整段 JSON
  2) 文件 ~/dsh-phone/endpoints.json
  3) 内置默认：单个本地端点 127.0.0.1:8787

endpoints.json 例：
{
  "timeout": 90,
  "retries_per_endpoint": 2,
  "endpoints": [
    {"name": "local",  "base": "http://127.0.0.1:8787/v1/chat/completions",
     "key": "local-noop",
     "models": ["deepseek-v4-pro", "glm-5.2"],
     "vision_models": ["glm-5v-turbo"]},
    {"name": "cloud",  "base": "https://api.example.com/v1/chat/completions",
     "key": "sk-xxx",
     "models": ["gpt-4o-mini"],
     "vision_models": ["gpt-4o"]}
  ]
}

命令行：
  python llm.py --ping             # 逐个探活，打印谁通、谁挂、多少毫秒
  python llm.py "用一句话说明你是谁"   # 单次问答（走回退链）
  python llm.py --vision 图.jpg "这图上写了什么"
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONF_FILE = os.path.join(HERE, "endpoints.json")
DEFAULT = {
    "timeout": 90,
    "retries_per_endpoint": 2,
    "endpoints": [
        {
            "name": "local",
            "base": "http://127.0.0.1:8787/v1/chat/completions",
            "key": "local-noop",
            "models": ["deepseek-v4-pro"],
            "vision_models": ["glm-5v-turbo"],
        }
    ],
}


def load_conf():
    raw = os.environ.get("DSH_ENDPOINTS")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print("[llm] DSH_ENDPOINTS 不是合法 JSON：%s" % e, file=sys.stderr)
    if os.path.isfile(CONF_FILE):
        try:
            return json.load(open(CONF_FILE, encoding="utf-8"))
        except json.JSONDecodeError as e:
            print("[llm] endpoints.json 解析失败：%s，改用默认" % e, file=sys.stderr)
    return DEFAULT


CONF = load_conf()


def candidates(vision=False, only_model=None, only_endpoint=None):
    """按优先级展开成 [(endpoint_dict, model_name), ...]"""
    out = []
    for ep in CONF.get("endpoints", []):
        if only_endpoint and ep.get("name") != only_endpoint:
            continue
        models = ep.get("vision_models" if vision else "models") or []
        if not models and not vision:
            models = ep.get("models") or []
        for m in models:
            if only_model and m != only_model:
                continue
            out.append((ep, m))
    return out


def _one_call(ep, model, messages, timeout, max_tokens, temperature):
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        ep["base"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + str(ep.get("key", "")),
        },
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    ms = int((time.time() - t0) * 1000)
    text = ""
    try:
        text = (d["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError):
        raise ValueError("返回结构不对: %s" % json.dumps(d, ensure_ascii=False)[:200])
    if not text:
        raise ValueError("空回复")
    return text, ms


def ask(prompt, vision=False, model=None, endpoint=None, max_tokens=800, temperature=0.2,
        image_path=None, image_b64=None, trace=True):
    """走回退链问一句。返回 dict：{text, endpoint, model, ms, tried}

    全部挂掉时抛 RuntimeError，里面带着每个候选的失败原因。
    """
    timeout = int(CONF.get("timeout", 90))
    retries = int(CONF.get("retries_per_endpoint", 2))
    msgs = [{"role": "user", "content": prompt}]
    if vision or image_path or image_b64:
        b64 = image_b64
        if image_path:
            b64 = base64.b64encode(open(image_path, "rb").read()).decode()
        if not b64:
            raise ValueError("vision=True 需要 image_path 或 image_b64")
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                ],
            }
        ]
    tried = []
    for ep, mdl in candidates(vision=bool(vision or image_path or image_b64),
                              only_model=model, only_endpoint=endpoint):
        for attempt in range(1, retries + 1):
            try:
                text, ms = _one_call(ep, mdl, msgs, timeout, max_tokens, temperature)
                if trace:
                    print("[llm] %s/%s  %dms" % (ep.get("name", "?"), mdl, ms), file=sys.stderr)
                return {"text": text, "endpoint": ep.get("name"), "model": mdl, "ms": ms, "tried": tried}
            except urllib.error.HTTPError as e:
                tried.append("%s/%s HTTP %s" % (ep.get("name"), mdl, e.code))
                if e.code in (400, 401, 403, 404):
                    break  # 这类错误重试没用，直接换下一个
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
                tried.append("%s/%s %s" % (ep.get("name"), mdl, str(e)[:60]))
            if attempt < retries:
                time.sleep(1.0 * attempt)
    raise RuntimeError("所有端点都失败了：" + " | ".join(tried or ["没有可用候选"]))


def ping():
    print("候选链：")
    for i, (ep, m) in enumerate(candidates(), 1):
        print("  %d) %s / %s" % (i, ep.get("name"), m))
    print("\n逐个探活：")
    ok = 0
    for ep, m in candidates():
        try:
            r = ask("只回复两个字：在的", model=m, endpoint=ep.get("name"), max_tokens=16, trace=False)
            print("  OK   %-8s %-16s %5dms  %r" % (ep.get("name"), m, r["ms"], r["text"][:20]))
            ok += 1
        except Exception as e:  # noqa: BLE001
            print("  FAIL %-8s %-16s %s" % (ep.get("name"), m, str(e)[:120]))
    print("\n可用 %d / %d" % (ok, len(candidates())))
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--ping":
        return ping()
    img = None
    if args[0] == "--vision":
        img = args[1]
        prompt = " ".join(args[2:]) or "描述这张图"
    else:
        prompt = " ".join(args)
    try:
        r = ask(prompt, image_path=img)
    except RuntimeError as e:
        print("FAIL:", e)
        return 1
    print(r["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
