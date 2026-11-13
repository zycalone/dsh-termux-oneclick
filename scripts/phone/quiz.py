#!/usr/bin/env python3
"""quiz.py —— 章节测验/选择题多路核查流水线（手机本地跑，直连网关）

用法：
  python quiz.py solve q.json            # 批量核查
  python quiz.py one "题干" "选项1" "选项2" "选项3" [--multi] [--judge]
  python quiz.py demo                    # 自检（内置样题）

输入 JSON：
  [{"id":"1","type":"single|multi|judge","q":"题干","options":["选项1","选项2",...]}]
  判断题可不给 options（默认 ["正确","错误"]）

输出：每题给出
  - 5 个模型的独立投票
  - 逐项判定（每项 3 票「是/否」）
  - 最终答案（字母 + 选项原文）
  - 置信度：高（两轮一致）/ 中（靠逐项或检索定案）/ 低（有分歧，需人工看）

设计原则：宁可标「低」也不硬猜。多选用逐项判定保证"选全"。
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# 端点与模型都可以用环境变量覆盖（DSH_GW / DSH_KEY / DSH_VOTE_MODELS …）
BASE = os.environ.get("DSH_GW", "http://127.0.0.1:8787/v1/chat/completions")
KEY = os.environ.get("DSH_KEY", "local-noop")
VOTE_MODELS = os.environ.get("DSH_VOTE_MODELS", "deepseek-v4-pro,glm-5.2,hy3,minimax-m3,deepseek-v4-flash").split(",")
ITEM_MODELS = os.environ.get("DSH_ITEM_MODELS", "deepseek-v4-pro,glm-5.2,hy3").split(",")
JUDGE_MODEL = os.environ.get("DSH_JUDGE_MODEL", "deepseek-v4-pro")
LETTERS = "ABCDEFGH"
USE_SEARCH = True


def ask(model, prompt, max_tokens=200, temperature=0.1, timeout=120):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE, data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY},
    )
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            return (d["choices"][0]["message"].get("content") or "").strip()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5)
    raise last


def pmap(fn, items, workers=5):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fn, it) for it in items]
        out = []
        for f in futs:
            try:
                out.append(f.result())
            except Exception:  # noqa: BLE001
                out.append(None)
        return out


def letters_from(text):
    if not text:
        return ""
    m = re.search(r"(?:答案|answer)\s*[:：是为]*\s*([A-Ha-h][A-Ha-h,，、\s]*)", text, re.I)
    cand = m.group(1) if m else None
    if cand is None:
        found = re.findall(r"\b([A-H]{1,6})\b", text)
        cand = found[-1] if found else ""
    return "".join(sorted(set(re.findall(r"[A-H]", cand.upper()))))


def opt_lines(options):
    return "\n".join("%s. %s" % (LETTERS[i], o) for i, o in enumerate(options))


def prompt_vote(qtype, q, options):
    kind = {"single": "单选题（只有一个正确答案）",
            "multi": "多选题（可能有两个或更多正确答案，必须选全）",
            "judge": "判断题"}[qtype]
    return (
        "你是一个严谨的答题专家。请作答下面的%s。\n\n题目：%s\n\n选项：\n%s\n\n"
        "要求：先在心里逐步推理（不要输出推理过程），最后单独一行按格式输出：\n"
        "答案：X\n（X 为选项字母，多选写成如 ABD，不要有空格）" % (kind, q, opt_lines(options))
    )


def prompt_item(qtype, q, opt):
    return (
        "题目：%s\n（%s）\n\n请单独判断下面这一个选项是否正确：\n%s\n\n"
        "只回答一个字：是 或 否。不要解释。"
        % (q, {"single": "单选", "multi": "多选", "judge": "判断"}[qtype], opt)
    )


def web_snippets(query, limit=6):
    try:
        url = "https://cn.bing.com/search?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return "SEARCH_FAILED: %s" % e
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    blocks = re.findall(r'(?is)<li class="b_algo".*?</li>', html)
    texts = []
    for b in blocks[:limit]:
        t = re.sub(r"(?is)<[^>]+>", " ", b)
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) > 40:
            texts.append(t[:500])
    return "\n---\n".join(texts) if texts else "(无结果)"


def prompt_judge(qtype, q, options, snippets):
    return (
        "下面是用户在刷学习通课程时遇到的一道%s，以及网上检索到的资料片段。\n\n"
        "题目：%s\n\n选项：\n%s\n\n网络资料：\n%s\n\n"
        "请只依据题目与资料作答，不要臆测。最后一行输出：\n答案：X\n"
        "（多选写如 ABD；若资料完全无法支撑，输出 答案：UNKNOWN）"
        % ({"single": "单选题", "multi": "多选题", "judge": "判断题"}[qtype],
           q, opt_lines(options), snippets[:3000])
    )


def solve_one(item):
    q = (item.get("q") or "").strip()
    qtype = item.get("type") or "single"
    options = item.get("options") or (["正确", "错误"] if qtype == "judge" else [])
    if not q:
        return {"id": item.get("id"), "error": "empty question"}
    options = [str(o).strip() for o in options]

    # ---- 第一轮：五模型独立投票 ----
    p = prompt_vote(qtype, q, options)
    raw = pmap(lambda m: ask(m, p, max_tokens=300), VOTE_MODELS)
    votes = {}
    for m, t in zip(VOTE_MODELS, raw):
        votes[m] = letters_from(t) if t else ""
    valid = {k: v for k, v in votes.items() if v and all(c in LETTERS[:len(options)] for c in v)}
    counts = {}
    for v in valid.values():
        counts[v] = counts.get(v, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])

    need_items = qtype == "multi" or not (top and top[0][1] >= 3 and (len(top) == 1 or top[0][1] > top[1][1]))

    # ---- 第二轮：逐项判定（选全 + 纠错）----
    item_counts = {}
    if need_items and options:
        def one_opt(i):
            vals = pmap(lambda m: ask(m, prompt_item(qtype, q, "%s. %s" % (LETTERS[i], options[i])),
                                      max_tokens=8), ITEM_MODELS, workers=3)
            yes = sum(1 for v in vals if v and v.strip().startswith("是"))
            return LETTERS[i], yes, len([v for v in vals if v])
        res = pmap(one_opt, list(range(len(options))), workers=3)
        for r in res:
            if r:
                item_counts[r[0]] = (r[1], r[2])

    chosen = ""
    if item_counts:
        if qtype == "single" or qtype == "judge":
            ranked = sorted(item_counts.items(), key=lambda kv: -kv[1][0])
            if ranked and ranked[0][1][0] >= 2 and (len(ranked) == 1 or ranked[0][1][0] > ranked[1][1][0]):
                chosen = ranked[0][0]
        else:
            chosen = "".join(sorted(k for k, v in item_counts.items() if v[0] >= 2))

    # ---- 合并判断 ----
    vote_answer = top[0][0] if top else ""
    confidence = "低"
    source = []
    if vote_answer and chosen and vote_answer == chosen:
        answer = chosen
        confidence = "高"
        source.append("投票+逐项一致")
    elif not chosen and vote_answer:
        answer = vote_answer
        confidence = "高" if (top and top[0][1] >= 4) else "中"
        source.append("投票一致度 %d/%d" % (top[0][1], len(valid)))
    elif chosen and (not vote_answer or qtype == "multi"):
        answer = chosen if not vote_answer else (
            "".join(sorted(set(chosen) | set(vote_answer))) if qtype == "multi" and
            (top and top[0][1] < 4) else chosen)
        confidence = "中"
        source.append("逐项判定")
    else:
        answer = vote_answer or ""

    # ---- 第三轮：检索兜底 ----
    snippets_used = ""
    if USE_SEARCH and (not answer or confidence != "高"):
        query = '"%s"' % q[:60]
        if options:
            query += " " + " ".join(o[:12] for o in options[:3])
        snippets_used = web_snippets(query)
        try:
            verdict = letters_from(ask(JUDGE_MODEL, prompt_judge(qtype, q, options, snippets_used),
                                       max_tokens=200))
        except Exception:  # noqa: BLE001
            verdict = ""
        if verdict and all(c in LETTERS[:len(options)] for c in verdict):
            if not answer:
                answer = verdict
                confidence = "中"
                source.append("检索")
            elif verdict != answer:
                source.append("检索给出 %s（与前面不同，需人工确认）" % verdict)
                confidence = "低"

    answer_text = "；".join("%s. %s" % (c, options[LETTERS.index(c)]) for c in answer
                            if c in LETTERS[:len(options)]) if options else answer
    return {
        "id": item.get("id"),
        "type": qtype,
        "q": q,
        "options": options,
        "votes": votes,
        "vote_top": top[:3],
        "item_judgement": {k: "%d/%d是" % v for k, v in item_counts.items()},
        "answer": answer,
        "answer_text": answer_text,
        "confidence": confidence,
        "notes": source,
    }


def print_result(r, idx=None):
    tag = r.get("id") or (idx + 1)
    if r.get("error"):
        print("[%s] 错误：%s" % (tag, r["error"]))
        return
    print("=" * 60)
    print("[%s] (%s) %s" % (tag, r["type"], r["q"]))
    for i, o in enumerate(r["options"]):
        print("    %s. %s" % (LETTERS[i], o))
    print("  投票：", "  ".join("%s=%s" % (k, v or "-") for k, v in r["votes"].items()))
    if r["item_judgement"]:
        print("  逐项：", "  ".join("%s:%s" % (k, v) for k, v in r["item_judgement"].items()))
    print("  ★ 最终答案：%s   【置信度 %s】" % (r["answer"] or "未定", r["confidence"]))
    if r["answer_text"]:
        print("    勾选：%s" % r["answer_text"])
    if r["notes"]:
        print("    说明：%s" % "；".join(r["notes"]))


def main():
    global USE_SEARCH
    args = [a for a in sys.argv[1:]]
    if not args:
        print(__doc__)
        return
    if "--no-search" in args:
        args.remove("--no-search")
        USE_SEARCH = False
    cmd = args[0]

    if cmd == "demo":
        items = [
            {"id": "样题1", "type": "single", "q": "Transformer 架构中最核心的机制是什么？",
             "options": ["循环神经网络", "自注意力机制", "卷积运算", "最大池化"]},
            {"id": "样题2", "type": "multi", "q": "以下哪些属于大语言模型当前公认的局限？",
             "options": ["会产生幻觉", "上下文窗口有限", "训练与推理成本高", "完全无法处理中文"]},
            {"id": "样题3", "type": "judge", "q": "大模型的参数量越大，在所有任务上的表现一定越好。"},
        ]
    elif cmd == "one":
        q = args[1]
        opts = args[2:]
        qtype = "single"
        if "--multi" in opts:
            opts.remove("--multi"); qtype = "multi"
        elif "--judge" in opts:
            opts.remove("--judge"); qtype = "judge"
        items = [{"id": "1", "type": qtype, "q": q, "options": opts or None}]
    elif cmd == "solve":
        path = args[1]
        with open(path, "r", encoding="utf-8") as f:
            items = json.load(f)
    else:
        print(__doc__)
        return

    results = []
    for it in items:
        r = solve_one(it)
        results.append(r)
        print_result(r, len(results) - 1)
        sys.stdout.flush()

    unanswered = [r for r in results if not r.get("answer")]
    low = [r for r in results if r.get("confidence") == "低"]
    print("=" * 60)
    print("共 %d 题；未定案 %d 题；低置信度 %d 题" % (len(results), len(unanswered), len(low)))
    if low:
        print("需人工看一眼：", "、".join(str(r.get("id")) for r in low))
    out = "quiz-result.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("结果已存：%s" % out)


if __name__ == "__main__":
    main()
