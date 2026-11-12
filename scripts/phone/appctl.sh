#!/data/data/com.termux/files/usr/bin/bash
# appctl —— 让手机自己操作其它 App（本机 adb，无需电脑）
export TMPDIR="$HOME/tmp"; mkdir -p "$TMPDIR"
SER=127.0.0.1:5556
HERE=$(cd "$(dirname "$0")" && pwd)

ensure() {
  adb connect "$SER" >/dev/null 2>&1 </dev/null
  st=$(adb -s "$SER" get-state 2>/dev/null </dev/null)
  if [ "$st" != "device" ]; then
    echo "ADB_OFFLINE: 需一次 USB 连接执行 adb tcpip 5556（见 手机接管-ADB+SSH.md）" >&2
    exit 1
  fi
}

A() { adb -s "$SER" "$@" </dev/null; }

cmd="$1"; shift 2>/dev/null
case "$cmd" in
  cur)
    ensure
    A shell dumpsys window 2>/dev/null | grep -m1 mCurrentFocus
    ;;
  text)
    ensure
    A shell uiautomator dump --compressed /data/local/tmp/ui.xml >/dev/null 2>&1
    A shell cat /data/local/tmp/ui.xml 2>/dev/null | python "$HERE/ui_text.py"
    ;;
  tap)
    ensure; A shell input tap "$1" "$2"; echo "tapped $1,$2"
    ;;
  tap-text)
    ensure
    line=$(bash "$HERE/appctl.sh" text | grep -F -- "$1" | head -1)
    if [ -z "$line" ]; then echo "NOT_FOUND: $1" >&2; exit 2; fi
    xy=$(echo "$line" | grep -o '@[0-9]*,[0-9]*' | tail -1 | tr -d '@')
    x=${xy%,*}; y=${xy#*,}
    A shell input tap "$x" "$y"; echo "tapped [$1] at $x,$y"
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
  *)
    echo "appctl —— 手机自控（本机 adb，不用电脑）"
    echo "  appctl cur               当前前台 App/界面"
    echo "  appctl text              读当前屏幕文字（含坐标与是否可点）"
    echo "  appctl tap X Y           点坐标"
    echo "  appctl tap-text 文字      点包含该文字的元素（推荐）"
    echo "  appctl swipe X1 Y1 X2 Y2 [毫秒]"
    echo "  appctl key KEYCODE_HOME  按键（HOME/BACK/ENTER/KEYCODE_WAKEUP）"
    echo "  appctl type 文本          输入文字"
    echo "  appctl open 包名          启动 App（如 com.tencent.mm）"
    echo "  appctl apps              列出第三方 App 包名"
    echo "  appctl shot              截屏并打印 png 路径（可交给 read_image 看图）"
    echo "组合：open → text → tap-text → shot 视觉确认"
    ;;
esac
