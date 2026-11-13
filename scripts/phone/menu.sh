#!/data/data/com.termux/files/usr/bin/bash
# menu.sh —— 打开 Termux 敲 m 就出这个菜单（桌面小组件失败时的兜底）
cd "$HOME" || exit 1
while true; do
  echo
  echo "========= dsh 手机端 一键菜单 ========="
  echo "  1) 开会记纪要（全程记屏，Ctrl+C 收工出纪要）"
  echo "  2) 看屏幕做笔记（20 分钟，边看边记）"
  echo "  3) 解析手机上最新视频（下载目录/相册里最新的）"
  echo "  4) 最新转写稿成笔记（下载目录里最新的 txt/docx/srt/pdf）"
  echo "  5) 修 ADB 连接（拔线/重启后连不上时用）"
  echo "  6) 看看状态（adb / 网关 / 模型 自检）"
  echo "  7) 打开 dsh 网页版"
  echo "  0) 退出"
  printf "选一个："
  read -r n
  case "$n" in
    1) python "$HOME/dsh-phone/meetnote.py" --pkgs com.tencent.wemeet.app --interval 15 --keep-awake ;;
    2) python "$HOME/dsh-phone/screenwatch.py" --minutes 20 --interval 20 ;;
    3) V=$(find /sdcard/Download /sdcard/Movies /sdcard/DCIM/Camera -maxdepth 2 -type f \
             \( -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.webm' \) -printf '%T@ %p\n' 2>/dev/null \
           | sort -rn | head -1 | cut -d' ' -f2-)
       if [ -z "$V" ]; then echo "没找到视频"; else echo "用：$V"; python "$HOME/dsh-phone/vidnote.py" "$V" --interval 30 --max 20 --kind auto; fi ;;
    4) F=$(find /sdcard/Download /sdcard/Documents "$HOME/tmp" -maxdepth 2 -type f \
             \( -iname '*.txt' -o -iname '*.md' -o -iname '*.srt' -o -iname '*.vtt' -o -iname '*.docx' -o -iname '*.pdf' \) \
             -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
       if [ -z "$F" ]; then echo "没找到转写稿"; else echo "用：$F"; python "$HOME/dsh-phone/minutetool.py" "$F" --kind auto; fi ;;
    5) bash "$HOME/dsh-phone/fix-adb.sh" | tail -12; adb devices | tail -3 ;;
    6) bash "$HOME/dsh-phone/healthcheck.sh" | tail -20 ;;
    7) bash "$HOME/dsh-phone/start-dsh.sh" 2>/dev/null || echo "网页版没起来，跑 bash ~/dsh-phone/up.sh 看看" ;;
    0|q) break ;;
    *) echo "  没这个选项" ;;
  esac
done
