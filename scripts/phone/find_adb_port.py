#!/usr/bin/env python3
"""find_adb_port.py —— 在手机本地扫出「无线调试」的 adb 端口

为什么要这个：Android 从 9 开始禁止普通 App 读 /proc/net/tcp、也不给 netlink，
所以 ss/netstat 在 Termux 里全是 Permission denied，**没法直接列监听端口**。
只能反过来试：对 127.0.0.1 的一段端口做 TCP 连接探测（本地拒绝是瞬间的，很快），
把「真的在听」的端口挑出来，再交给 adb connect 去验。

用法：
  python find_adb_port.py                  # 默认扫 30000-49999 + 5555-5599
  python find_adb_port.py 30000 40000      # 指定范围
  python find_adb_port.py --all            # 额外再扫 1024-29999（更慢）

输出：一行，空格分隔的开放端口（升序）。找不到就什么都不打印。
"""
import socket
import sys
from concurrent.futures import ThreadPoolExecutor


def probe(port, timeout=0.25):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        return port
    except OSError:
        return None
    finally:
        s.close()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    want_all = "--all" in sys.argv
    if len(args) >= 2:
        ranges = [(int(args[0]), int(args[1]))]
    else:
        ranges = [(30000, 49999), (5555, 5599)]
        if want_all:
            ranges.append((1024, 29999))

    ports = []
    for lo, hi in ranges:
        ports.extend(range(lo, hi + 1))

    open_ports = []
    with ThreadPoolExecutor(max_workers=256) as ex:
        for r in ex.map(probe, ports, chunksize=32):
            if r:
                open_ports.append(r)
    open_ports.sort()
    if open_ports:
        print(" ".join(str(p) for p in open_ports))
    return 0 if open_ports else 1


if __name__ == "__main__":
    sys.exit(main())
