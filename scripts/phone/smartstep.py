#!/usr/bin/env python3
"""smartstep.py —— 带「反思」的手机自动操作循环（Termux 本地跑）

思路借鉴 Mobile-Agent 的 reflection：动作做完没效果，不是盲目重试，
而是**截图问视觉模型「为什么没成功、下一步该点什么」**，拿到修正再试一次。

用法：
  python smartstep.py --goal "打开设置，进入显示，把深色模式打开" --dry-run
  python smartstep.py --goal "..." --max-steps 10
  python smartstep.py --goal "..." --no-reflect          # 关掉反思，退化成机械重试
  python smartstep.py --goal "..." --plan-out plan.json  # 把每步计划存下来复盘

安全：
  - 动作里出现 支付/付款/转账/验证码/密码/人脸/卸载/格式化 等字样，直接中止
  - --dry-run 只读屏、只打印计划，绝不点屏幕
  - 步数上限（默认 8），防死循环
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APPCTL = os.path.join(HERE, "appctl.sh")
sys.path.insert(0, HERE)
import llm  # noqa: E402
from act_batch import build  # noqa: E402

BLOCK = ("支付", "付款", "转账", "收款", "免密", "验证码", "密码", "人脸", "刷脸",
         "卸载", "格式化", "恢复出厂", "注销", "解绑")

SYS = """你在通过 adb 操作一台安卓手机。每一步我会给你：目标、已经做过的动作、当前屏幕上可点的元素（含坐标）。
你只能输出一个 JSON 对象，不要任何解释、不要 markdown 代码块。

可选动作：
  {"act":"tap-text","text":"要点的元素文字"}     点包含这段文字的元素（首选，比坐标稳）
  {"act":"tap","x":540,"y":1200}               点坐标（只有在没有文字时才用）
  {"act":"type","text":"要输入的文本"}
  {"act":"key","code":"KEYCODE_BACK"}          按键：BACK/HOME/ENTER/KEYCODE_WAKEUP
  {"act":"swipe","args":[540,1800,540,900,300]}  滑动
  {"act":"wait-text","text":"文字","timeout":8}  等某元素出现
  {"act":"done","why":"已完成或无法继续的原因"}

每次只能输出一个动作。如果目标已经达成，用 done。
千万不要猜不存在的元素：只能用我给你的列表里出现过的文字。
输出格式示例：{"thought":"先进入设置","act":"tap-text","text":"设置"}"""


def sh(cmd, timeout=90):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def screen_json():
    rc, out, err = sh(["bash", APPCTL, "text", "--click", "--json"])
    if rc != 0:
        return [], "appctl 失败: " + (err or out)[:120]
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return [], "读屏返回不是 JSON: " + out[:120]
    return d.get("nodes", []), ""


def fingerprint():
    rc, out, _ = sh(["bash", APPCTL, "text", "--click"])
    return hashlib.md5(out.encode("utf-8", "replace")).hexdigest()[:8]


def compact(nodes, limit=45):
    lines = []
    for n in nodes[:limit]:
        lines.append("- %s  @%d,%d" % (n["text"][:40], n["cx"], n["cy"]))
    return "\n".join(lines) or "(屏幕上没有可点元素)"


def parse_action(text):
    """从模型回复里抠出 JSON 对象；失败返回 None。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else None
    except json.JSONDecodeError:
        pass
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        try:
            d = json.loads(text[i:j + 1])
            return d if isinstance(d, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def unsafe(action):
    blob = json.dumps(action, ensure_ascii=False)
    return [w for w in BLOCK if w in blob]


def run_action(action, dry):
    step = dict(action)
    cmd = build(step)
    if cmd is None:
        return 3, "未知动作: %s" % action.get("act")
    if dry:
        return 0, "DRY  appctl " + " ".join(cmd[2:])
    rc, out, err = sh(cmd, timeout=120)
    return rc, (out or err)[:300]


def reflect(goal, failed_action, image_path):
    """截图问视觉模型：为什么没成功？下一步怎么办？"""
    prompt = (
        "我在用 adb 操作安卓手机。目标：%s\n"
        "上一步执行了动作：%s\n"
        "但是界面完全没有变化，说明这一步没生效。\n"
        "这是当前屏幕截图。请你判断：为什么没成功？下一步应该做什么？\n"
        "只输出一个 JSON：{\"reason\":\"为什么没成功\",\"act\":\"tap-text|tap|key|done\","
        "\"text\":\"要点的元素文字\",\"x\":0,\"y\":0,\"code\":\"KEYCODE_BACK\"}\n"
        "点文字优先，点坐标最后手段；实在没法继续就用 done 并说明原因。" % (goal, json.dumps(failed_action, ensure_ascii=False))
    )
    r = llm.ask(prompt, image_path=image_path, max_tokens=500, temperature=0.1)
    return parse_action(r["text"]) or {}, r


def main():
    args = sys.argv[1:]
    goal = None
    max_steps = 8
    dry = "--dry-run" in args
    use_reflect = "--no-reflect" not in args
    plan_out = None
    if "--goal" in args:
        goal = args[args.index("--goal") + 1]
    if "--max-steps" in args:
        max_steps = int(args[args.index("--max-steps") + 1])
    if "--plan-out" in args:
        plan_out = args[args.index("--plan-out") + 1]
    if not goal:
        print(__doc__)
        return 2

    print("目标：%s" % goal)
    print("模式：%s%s" % ("干跑（不点屏幕）" if dry else "真跑",
                        "，失败会反思" if use_reflect else "，失败只重试不反思"))
    history = []
    trace = []
    for step in range(1, max_steps + 1):
        nodes, err = screen_json()
        if err:
            print("[%d] 读屏失败：%s" % (step, err))
            return 1
        prompt = (
            "%s\n\n【目标】%s\n\n【已做过的动作】\n%s\n\n【当前可点元素】\n%s\n\n输出下一个动作 JSON："
            % (SYS, goal, "\n".join(history) or "(还没有动作)", compact(nodes))
        )
        try:
            r = llm.ask(prompt, max_tokens=400, temperature=0.1)
        except RuntimeError as e:
            print("[%d] 模型全挂：%s" % (step, e))
            return 1
        action = parse_action(r["text"])
        if not action:
            print("[%d] 模型没给出合法 JSON：%r" % (step, r["text"][:200]))
            history.append("step%d: 输出非法，已忽略" % step)
            continue
        thought = action.get("thought", "")
        print("\n[%d] 计划 %s%s" % (step, json.dumps({k: v for k, v in action.items() if k != "thought"}, ensure_ascii=False),
                                    ("  // " + thought) if thought else ""))
        trace.append({"step": step, "action": action, "endpoint": r["endpoint"], "model": r["model"]})

        if action.get("act") == "done":
            print("[%d] 结束：%s" % (step, action.get("why", "")))
            break
        bad = unsafe(action)
        if bad:
            print("[%d] 中止：动作里出现敏感词 %s —— 这类操作必须人来做" % (step, ",".join(bad)))
            return 4

        before = fingerprint()
        rc, out = run_action(action, dry)
        print("     执行 → rc=%d %s" % (rc, out.replace("\n", "\n       ")))
        history.append("step%d: %s → rc=%d" % (step, json.dumps({k: v for k, v in action.items() if k != "thought"}, ensure_ascii=False), rc))
        if dry:
            continue
        if rc != 0:
            history.append("   该步失败")
        time.sleep(1.2)
        after = fingerprint()
        changed = after != before
        print("     复核 → 界面%s变化" % ("有" if changed else "没有"))
        if changed or rc != 0 and not use_reflect:
            continue
        if not changed and use_reflect:
            print("     反思 → 截图问视觉模型为什么没成功")
            rc2, path, err2 = sh(["bash", APPCTL, "shot"], timeout=120)
            if rc2 != 0 or not path:
                print("     反思跳过：截图失败 %s" % (err2[:100]))
                continue
            try:
                fix, r2 = reflect(goal, action, path)
            except (RuntimeError, ValueError) as e:
                print("     反思失败：%s" % e)
                continue
            print("     反思结论：%s" % fix.get("reason", "(没说原因)"))
            if not fix.get("act") or fix.get("act") == "done":
                print("     反思建议停止：%s" % fix.get("reason", ""))
                history.append("step%d: 反思建议停止" % step)
                break
            fix.pop("thought", None)
            fix.pop("reason", None)
            bad2 = unsafe(fix)
            if bad2:
                print("     中止：反思建议里出现敏感词 %s" % ",".join(bad2))
                return 4
            rc3, out3 = run_action(fix, dry)
            print("     反思动作 %s → rc=%d %s" % (json.dumps(fix, ensure_ascii=False), rc3, out3[:160]))
            trace.append({"step": step, "reflect": fix, "endpoint": r2["endpoint"], "model": r2["model"]})
            history.append("step%d 反思后: %s → rc=%d" % (step, json.dumps(fix, ensure_ascii=False), rc3))
            time.sleep(1.2)
    else:
        print("\n达到步数上限 %d，停止。" % max_steps)

    if plan_out:
        json.dump(trace, open(plan_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("轨迹已存：%s" % plan_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
