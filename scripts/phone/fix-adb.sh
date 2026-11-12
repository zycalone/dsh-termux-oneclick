#!/data/data/com.termux/files/usr/bin/bash
# fix-adb.sh —— 手机重启后恢复 appctl 通道
# 手机重启会关掉 adb 的 TCP 5556 端口，必须在电脑上插一次 USB 执行下面这条：
#     adb tcpip 5556
# 然后在手机上跑本脚本确认。
export TMPDIR="$HOME/tmp"; mkdir -p "$TMPDIR"

echo "=== 检查自连通道 ==="
adb connect 127.0.0.1:5556 >/dev/null 2>&1
ST=$(adb -s 127.0.0.1:5556 get-state 2>/dev/null)
if [ "$ST" = "device" ]; then
  echo "OK: appctl 可用（当前前台：$(bash "$HOME/dsh-phone/appctl.sh" cur 2>/dev/null | sed 's/.*u0 //' | cut -c1-60)）"
  exit 0
fi

echo "通道断了：手机重启后 adb TCP 模式会关闭。恢复步骤："
echo "  1) 数据线插到电脑（电脑需装着本项目的 platform-tools\\adb.exe）"
echo "  2) 手机上若弹「允许 USB 调试」-> 勾选一律允许/允许"
echo "  3) 电脑执行： adb tcpip 5556"
echo "  4) 拔线，手机执行： bash ~/dsh-phone/fix-adb.sh"
echo ""
echo "没有电脑时的替代办法："
echo "  - dsh 的其它能力（识图、搜索、写文档）不受影响，只有「操作别的 App」用不了"
echo "  - 或者把手机连到任意一台装了 adb 的机器上执行一次 adb tcpip 5556"
exit 1
