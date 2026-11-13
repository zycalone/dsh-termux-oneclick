#!/data/data/com.termux/files/usr/bin/bash
# fix-adb.sh v2 —— 手机自己把「本机 adb」通道找回来（拔线 / 重启后）
#
# 为什么原来会连不上：
#   Android 11+ 的「无线调试」一重启、一断 Wi-Fi、一换网络就会**自动关闭**，
#   重新打开后**端口是随机的**（不一定还是 5556）；老办法 adb tcpip 5556 也只在重启前有效。
#   把 5556 写死，迟早连不上 —— 这里改成自己去把当前端口找出来。
#
#   注意：Android 9 起禁止普通 App 读 /proc/net/tcp，ss / netstat 全是 Permission denied，
#   所以「列监听端口」这条路走不通，只能拿 python 反向探测（本地拒绝是瞬间的，很快）。
#
# 用法：
#   bash ~/dsh-phone/fix-adb.sh            # 全量：先快后慢，最后给人话结论
#   bash ~/dsh-phone/fix-adb.sh ensure     # 静默快速：成功只打印端口号（appctl 内部调用）
#   bash ~/dsh-phone/fix-adb.sh status     # 只看现在通不通
#
# 找端口顺序：已经连着的 → 记住的 → 5555/5556/5557 → 端口探测 → /proc 扫描（桌面 Linux 用）
export TMPDIR="$HOME/tmp"; mkdir -p "$TMPDIR"
HERE=$(cd "$(dirname "$0")" && pwd)
PORTFILE="$HOME/.dsh-adb-port"
HISTFILE="$HOME/.dsh-adb-ports"   # 历史上找到过的端口，下次先试这些
QUIET=0
case "${1:-}" in
  ensure) QUIET=1 ;;
esac
SAY() { [ "$QUIET" = "1" ] || echo "$@"; }

remember() { # 记住当前端口 + 追加历史（去重，最多 5 个）
  echo "$1" > "$PORTFILE"
  { cat "$HISTFILE" 2>/dev/null; echo "$1"; } | awk 'NF && !seen[$0]++' | tail -5 > "$HISTFILE.tmp" && mv "$HISTFILE.tmp" "$HISTFILE"
}

have_device() { # $1=port
  adb devices 2>/dev/null </dev/null | grep -qE "^127\.0\.0\.1:$1[[:space:]]+device"
}

try_port() { # $1=port → 通就记住并返回 0
  local p="$1"
  [ -z "$p" ] && return 1
  case "$p" in 8022|8787|5037|5554) return 1;; esac
  have_device "$p" && { remember "$p"; return 0; }
  timeout 3 adb connect "127.0.0.1:$p" >/dev/null 2>&1 </dev/null
  if have_device "$p"; then remember "$p"; return 0; fi
  adb disconnect "127.0.0.1:$p" >/dev/null 2>&1 </dev/null   # 清掉 offline 残渣
  return 1
}

# /proc/net/tcp{,6} 的监听端口 —— 只在桌面 Linux 有意义，Android 上会空
listen_ports() {
  local f local_addr hex
  for f in /proc/net/tcp /proc/net/tcp6; do
    [ -r "$f" ] || continue
    tail -n +2 "$f" 2>/dev/null | while read -r _sl local_addr _rem st _rest; do
      [ "$st" = "0A" ] || continue
      hex=${local_addr#*:}
      case "$hex" in ''|*[!0-9A-Fa-f]*) continue;; esac
      echo $((16#$hex))
    done
  done | sort -un
}

scan_ports() {
  if command -v python >/dev/null 2>&1 && [ -f "$HERE/find_adb_port.py" ]; then
    python "$HERE/find_adb_port.py" 2>/dev/null
  else
    listen_ports | awk '$1>=1024' | sort -urn | head -40
  fi
}

SAY "=== fix-adb v2 ==="
adb start-server >/dev/null 2>&1 </dev/null

# 清掉以前探测留下的 offline 残渣（不然 adb devices 会越来越脏）
adb devices 2>/dev/null </dev/null | awk '/offline/ {print $1}' | while read -r d; do
  [ -n "$d" ] && adb disconnect "$d" >/dev/null 2>&1 </dev/null
done

# 1) 已经通了？（任意端口）
CUR=$(adb devices 2>/dev/null </dev/null | grep -E '^127\.0\.0\.1:[0-9]+[[:space:]]+device' | head -1 | sed 's/^127\.0\.0\.1:\([0-9]*\).*/\1/')
if [ -n "$CUR" ]; then
  remember "$CUR"
  if [ "$QUIET" = "1" ]; then echo "$CUR"; else SAY "已连通，端口 $CUR（无需修复）"; fi
  exit 0
fi

# 2) 记住的端口 → 常见端口（FIXADB_SCAN_ONLY=1 跳过，专门验第 3 步探测）
if [ "${FIXADB_SCAN_ONLY:-0}" != "1" ]; then
  for p in "$(cat "$PORTFILE" 2>/dev/null)" $(awk '{a[NR]=$0} END{for(i=NR;i>0;i--) printf "%s ", a[i]}' "$HISTFILE" 2>/dev/null) 5555 5556 5557; do
    if try_port "$p"; then
      if [ "$QUIET" = "1" ]; then echo "$p"; else SAY "连上了：端口 $p（已记住，下次优先用它）"; fi
      exit 0
    fi
  done
fi

# 3) 探测本机在听的端口，逐个试
[ "$QUIET" = "0" ] && SAY "正在探测本机端口（约 3-10 秒）…"
OPENPS=$(scan_ports)
[ "$QUIET" = "0" ] && SAY "在听的：${OPENPS:-（一个都没扫到）}"
for p in $OPENPS; do
  if try_port "$p"; then
    if [ "$QUIET" = "1" ]; then echo "$p"; else SAY "扫到了：端口 $p"; fi
    exit 0
  fi
done

# 4) 没救了 —— 给人话结论
[ "$QUIET" = "1" ] && exit 1
cat <<'EOT'

--- 没找到可连的 adb 端口 ---

最可能的原因：手机上「开发者选项 → 无线调试」被关掉了。
  重启、断 Wi-Fi、切网络之后它都会自动关闭，重新打开时端口还会变（所以别写死 5556）。

两种修法，任选：

【A. 完全不用电脑】设置 → 系统 → 开发者选项 → 打开「无线调试」
    打开后不用管「配对码」，Termux 里再跑一次：bash ~/dsh-phone/fix-adb.sh
    顺便把 Wi-Fi 设成「始终保持连接」（有的 ROM 叫「休眠时保持 Wi-Fi」），
    否则息屏久了无线调试会掉线，下次又连不上。

【B. 插一次电脑，把端口固定下来】
    adb tcpip 5555        # 仅当次有效，重启后还要重来，但比找端口省事
    adb devices           # 确认能看到设备
    拔线，手机执行：bash ~/dsh-phone/fix-adb.sh

两个常见报错：
  - "failed to authenticate"，手机上弹「允许 USB 调试」→ 点允许（勾选一律允许）
  - 端口能连上但 devices 里是 offline → 关掉无线调试再开一次

即使 adb 全废，dsh 的识图、联网、写文档照常能用，只有「操作别的 App」这一块停摆。
EOT
exit 1
