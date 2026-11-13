#!/data/data/com.termux/files/usr/bin/bash
# boot-fixadb.sh —— 开机自动把 adb 通道接回来（可选，需要装 Termux:Boot）
#
# 安装：
#   pkg install -y termux-boot        # 或从 F-Droid 装 Termux:Boot
#   mkdir -p ~/.termux/boot && cp ~/dsh-phone/boot-fixadb.sh ~/.termux/boot/
#   chmod +x ~/.termux/boot/boot-fixadb.sh
#
# 说明：手机重启后「无线调试」通常会被系统关掉，这种情况下本脚本也救不回来
#       （adbd 根本没在听）。它的价值是：只要你把无线调试保持开启，
#       开机后端口变了，它会在后台把新端口找出来并记住，你上手就能用。
sleep 25   # 等 Wi-Fi 起来、系统稳定
bash "$HOME/dsh-phone/fix-adb.sh" ensure >/dev/null 2>&1
# 顺手把端口记到日志，方便回溯
echo "$(date '+%F %T') boot-fixadb → $(cat "$HOME/.dsh-adb-port" 2>/dev/null || echo 失败)" >> "$HOME/dsh-phone/boot-fixadb.log"
