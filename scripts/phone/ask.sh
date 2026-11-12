#!/data/data/com.termux/files/usr/bin/bash
# ask.sh "任务描述" —— 在 Termux 里一句话把活交给 dsh（不用浏览器）
# 视觉模型已挂上，能截图看屏；危险模式开，能自由读写文件
if [ -z "$1" ]; then
  echo '用法：bash ~/dsh-phone/ask.sh "打开学习通，做 7.3 章节测验，用 quiz.py 核查后报给我"'
  exit 1
fi
cd "$HOME" || exit 1
export TMPDIR="$HOME/tmp"; mkdir -p "$TMPDIR"
export OPENAI_API_KEY=local-noop
export DSH_PERMISSION_MODE=danger-full-access
exec node --expose-internals \
  /data/data/com.termux/files/usr/lib/node_modules/dsh-termux/lib/bin.js \
  --profile headless \
  --patch "$HOME/.dsh/profiles/web/cordis.patch.yml" \
  --patch "$HOME/dsh-phone/vision-overlay.yml" \
  --permission-mode danger-full-access \
  "$1"
