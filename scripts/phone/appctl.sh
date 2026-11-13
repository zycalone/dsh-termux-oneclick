#!/data/data/com.termux/files/usr/bin/bash
# appctl —— 让手机自己操作其它 App（本机 adb，无需电脑、无需 root）
#
# 设计要点（借鉴 droidrun / Mobile-Agent / AppAgent 的思路）：
#   1) 默认读屏只给「可点元素」，省 token、少瞎点 —— text --click
#   2) 点完自动复核界面有没有变化，失败自动重试 —— tap-text "文字" --verify
#   3) 等元素出现，别靠 sleep 赌时间 —— wait-text "文字" 15
#   4) 把某个界面摸清后存成「控件知识库」，下次直接查，不用再 dump —— kb save/get
#   5) 多步动作一次性下发、本地顺序执行 —— act_batch.py steps.json
export TMPDIR="$HOME/tmp"; mkdir -p "$TMPDIR"
HERE=$(cd "$(dirname "$0")" && pwd)
# 端口不写死：无线调试重开一次端口就会变，这里读上次找到的（fix-adb.sh 维护）
SERFILE="$HOME/.dsh-adb-port"
SER="127.0.0.1:$(cat "$SERFILE" 2>/dev/null || echo 5556)"
KB="$HOME/dsh-phone/kb"

ensure() {
  st=$(adb -s "$SER" get-state 2>/dev/null </dev/null)
  [ "$st" = "device" ] && return 0
  # 自愈：拔线 / 重启 / 无线调试换端口后，自动把当前端口找回来
  p=$(bash "$HERE/fix-adb.sh" ensure 2>/dev/null </dev/null)
  if [ -n "$p" ]; then SER="127.0.0.1:$p"; return 0; fi
  echo "ADB_OFFLINE: 本机 adb 连不上（无线调试多半被关掉了）。" >&2
  echo "  跑 bash $HERE/fix-adb.sh 看具体结论；docs/02 有说明" >&2
  exit 1
}

A() { adb -s "$SER" "$@" </dev/null; }

dump_xml() {
  A shell uiautomator dump --compressed /data/local/tmp/ui.xml >/dev/null 2>&1
  A shell cat /data/local/tmp/ui.xml 2>/dev/null
}

readscreen() { dump_xml | python "$HERE/ui_text.py" "$@"; }

sigh() { if command -v md5sum >/dev/null 2>&1; then md5sum | cut -c1-8; else cksum | cut -d' ' -f1; fi; }

curpkg() {
  A shell dumpsys window 2>/dev/null | grep -m1 mCurrentFocus | sed 's#.*u0 ##; s#/.*##; s# .*##'
}

cmd="$1"; shift 2>/dev/null
case "$cmd" in
  cur)
    ensure
    A shell dumpsys window 2>/dev/null | grep -m1 mCurrentFocus
    ;;
  text)
    ensure
    readscreen "$@"
    ;;
  tap)
    ensure; A shell input tap "$1" "$2"; echo "tapped $1,$2"
    ;;
  tap-text)
    ensure
    want="$1"; shift 2>/dev/null
    verify=0; tries=3
    while [ $# -gt 0 ]; do
      case "$1" in
        --verify) verify=1 ;;
        --tries) shift; tries="${1:-3}" ;;
      esac
      shift
    done
    before=$(readscreen --click | sigh)
    i=1
    while [ "$i" -le "$tries" ]; do
      line=$(readscreen --click | grep -F -- "$want" | head -1)
      if [ -z "$line" ]; then
        echo "NOT_FOUND: $want (第 $i/$tries 次)" >&2
        sleep 1; i=$((i + 1)); continue
      fi
      xy=$(echo "$line" | grep -o '@[0-9]*,[0-9]*' | tail -1 | tr -d '@')
      x=${xy%,*}; y=${xy#*,}
      A shell input tap "$x" "$y"
      if [ "$verify" = "1" ]; then
        sleep 1.2
        after=$(readscreen --click | sigh)
        if [ "$after" = "$before" ]; then
          echo "tapped [$want] at $x,$y changed=no (第 $i/$tries 次，界面没变化，重试)" >&2
          sleep 0.8; i=$((i + 1)); continue
        fi
        echo "tapped [$want] at $x,$y changed=yes"
      else
        echo "tapped [$want] at $x,$y"
      fi
      exit 0
    done
    echo "GIVE_UP: $want（试了 $tries 次，界面始终没变化；先 text --click 看看现在到底有什么）" >&2
    exit 4
    ;;
  wait-text)
    ensure
    want="$1"; timeout="${2:-15}"
    n=0
    while [ "$n" -lt "$timeout" ]; do
      if readscreen --click | grep -qF -- "$want"; then
        echo "FOUND: $want（等了 ${n}s）"; exit 0
      fi
      sleep 1; n=$((n + 1))
    done
    echo "TIMEOUT: $want（${timeout}s 内没出现）" >&2; exit 3
    ;;
  swipe)
    ensure; A shell input swipe "$1" "$2" "$3" "$4" "${5:-300}"; echo swiped
    ;;
  key)
    ensure; A shell input keyevent "$1"; echo "key $1"
    ;;
  type)
    ensure
    txt=$(printf '%s' "$1" | sed 's/ /%s/g')
    A shell input text "$txt"; echo typed
    ;;
  open)
    ensure
    A shell monkey -p "$1" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
    echo "opened $1"
    ;;
  apps)
    ensure; A shell pm list packages -3 | sed 's/package://' | sort
    ;;
  shot)
    ensure
    ts=$(date +%H%M%S)
    A shell screencap -p /data/local/tmp/s.png
    A pull /data/local/tmp/s.png "$HOME/tmp/shot_$ts.png" >/dev/null 2>&1
    echo "$HOME/tmp/shot_$ts.png"
    ;;
  kb)
    ensure
    sub="$1"; shift 2>/dev/null
    mkdir -p "$KB"
    name="${1:-$(curpkg | tr '/. ' '___')}"
    case "$sub" in
      save)
        {
          echo "# pkg: $(curpkg)"
          echo "# saved: $(date '+%Y-%m-%d %H:%M')"
          readscreen --click
        } >"$KB/$name.txt"
        echo "$KB/$name.txt"
        ;;
      get)
        if [ -f "$KB/$name.txt" ]; then cat "$KB/$name.txt"; else echo "NO_KB: $name（先 kb save $name）"; fi
        ;;
      list)
        ls -1 "$KB" 2>/dev/null | sed 's/\.txt$//'
        ;;
      *)
        echo "用法: appctl kb save|get|list [名字]" >&2; exit 2
        ;;
    esac
    ;;
  batch)
    ensure
    python "$HERE/act_batch.py" "$@"
    ;;
  *)
    echo "appctl —— 手机自控（本机 adb，不用电脑）"
    echo "  appctl cur                当前前台 App/界面"
    echo "  appctl text [--click]     读屏：--click 只给可点元素（省 token，推荐）"
    echo "                           还有 --json / --max N / --scroll"
    echo "  appctl tap X Y            点坐标"
    echo "  appctl tap-text 文字 [--verify]   点包含该文字的元素；--verify 自动复核+重试"
    echo "  appctl wait-text 文字 [秒]        等元素出现（默认 15s），别用 sleep 赌"
    echo "  appctl swipe X1 Y1 X2 Y2 [毫秒]"
    echo "  appctl key KEYCODE_HOME   按键（HOME/BACK/ENTER/KEYCODE_WAKEUP）"
    echo "  appctl type 文本           输入文字"
    echo "  appctl open 包名           启动 App（如 com.tencent.mm）"
    echo "  appctl apps               列出第三方 App 包名"
    echo "  appctl shot               截屏并打印 png 路径（交给 read_image 看图）"
    echo "  appctl kb save|get|list [名字]    控件知识库：摸过的界面存下来，下次直接查"
    echo "  appctl batch steps.json [--dry-run]   多步动作一次下发（见 act_batch.py）"
    echo ""
    echo "最稳的组合：cur → text --click → tap-text \"文字\" --verify → shot 视觉复核"
    ;;
esac
