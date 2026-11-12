#!/usr/bin/env python3
"""把本地仓库目录同步到 GitHub（只更新有改动的文件），用 Contents API，不需要本地 git。

用法：  set GITHUB_TOKEN=ghp_xxx  &&  python push_update.py
可选：  set GITHUB_REPO=zycalone/dsh-termux-oneclick   set GITHUB_BRANCH=main
"""
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.environ.get("GITHUB_LOCAL") or os.path.abspath(os.path.join(ROOT, "..", ".."))
REPO = os.environ.get("GITHUB_REPO", "zycalone/dsh-termux-oneclick")
BRANCH = os.environ.get("GITHUB_BRANCH", "main")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com"
SKIP_DIRS = {".git", "__pycache__"}


def req(url, method="GET", data=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "dsh-publish",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def remote_sha(path):
    q = urllib.parse.quote(path, safe="/")
    code, d = req("%s/repos/%s/contents/%s?ref=%s" % (API, REPO, q, BRANCH))
    if code == 200 and isinstance(d, dict):
        return d.get("sha")
    return None


def upload(path, content_bytes, message):
    cur = remote_sha(path)
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "branch": BRANCH,
    }
    if cur:
        payload["sha"] = cur
    q = urllib.parse.quote(path, safe="/")
    code, d = req("%s/repos/%s/contents/%s" % (API, REPO, q), "PUT", payload)
    return code, d


def main():
    if not TOKEN:
        print("缺 GITHUB_TOKEN")
        return 1
    if not os.path.isdir(LOCAL):
        print("本地目录不存在:", LOCAL)
        return 1
    changed = 0
    for dirpath, dirnames, filenames in os.walk(LOCAL):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, LOCAL).replace("\\", "/")
            data = open(full, "rb").read()
            rs = remote_sha(rel)
            if rs:
                # 已存在：比对内容 sha，不同才更新
                local_sha = hashlib.sha1(("blob %d\0" % len(data)).encode() + data).hexdigest()
                if rs == local_sha:
                    continue
            code, d = upload(rel, data, "docs: 更新 %s" % rel)
            ok = "OK" if code in (200, 201) else "FAIL"
            print("%-4s %-3s %s" % (ok, code, rel))
            if code in (200, 201):
                changed += 1
            else:
                print("     ", json.dumps(d, ensure_ascii=False)[:300])
    print("\n更新文件数:", changed)
    code, d = req("%s/repos/%s" % (API, REPO))
    if code == 200:
        print("仓库:", d.get("html_url"), "| 默认分支:", d.get("default_branch"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
