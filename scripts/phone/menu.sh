#!/data/data/com.termux/files/usr/bin/bash
# menu.sh —— 打开 Termux 就进这个菜单（.bashrc 自动调用；敲 0 回普通命令行）
# 菜单项直接来自 ~/.shortcuts/，加了新脚本会自动出现（文件名带空格也支持）
cd "$HOME" || exit 1

mapfile -t ITEMS < <(ls -1 "$HOME"/.shortcuts/*.sh 2>/dev/null | sort)
N=${#ITEMS[@]}
if [ "$N" -eq 0 ]; then
  echo "还没建快捷脚本"; exit 0
fi

while true; do
  echo
  echo "===== dsh 手机端 ====="
  for ((i = 1; i <= N; i++)); do
    name=$(basename "${ITEMS[$((i - 1))]}" .sh)
    printf '  %2d) %s\n' "$i" "$name"
  done
  printf '   0) 退出到命令行（敲 m 再回来）\n'
  printf '选一个数字：'
  if ! read -r n; then echo; exit 0; fi
  case "$n" in
    ""|0|q) echo "  回到命令行。敲 m 随时再进菜单。"; exit 0 ;;
    *[!0-9]*) echo "  要输数字" ;;
    *)
      if [ "$n" -lt 1 ] || [ "$n" -gt "$N" ]; then
        echo "  没有第 $n 项"
      else
        f="${ITEMS[$((n - 1))]}"
        echo "  --- 跑：$(basename "$f" .sh) ---"
        bash "$f" </dev/null
      fi ;;
  esac
done
