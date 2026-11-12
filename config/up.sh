#!/data/data/com.termux/files/usr/bin/bash
# 一键启动（日常就用这一条）：bash ~/dsh-phone/up.sh
# 安装位置：~/dsh-phone/up.sh  （chmod +x）
# 同时装开机自启：~/.termux/boot/start.sh 内容为  bash $HOME/dsh-phone/up.sh >> $HOME/dsh-phone/boot.log 2>&1
termux-wake-lock
pgrep -f "dsh.*web" >/dev/null || tmux new -d -s dsh "bash $HOME/dsh-phone/dshx.sh > $HOME/dsh-phone/dsh.log 2>&1"
sleep 20
grep -oE "http://127.0.0.1:[0-9]+/\?token=[A-Za-z0-9_-]+" $HOME/dsh-phone/dsh.log | tail -1
