#!/data/data/com.termux/files/usr/bin/bash
# see.sh "问题" —— 截取当前屏幕，交给视觉模型回答
export TMPDIR="$HOME/tmp"; mkdir -p "$TMPDIR"
SHOT=$(bash "$HOME/dsh-phone/appctl.sh" shot) || exit 1
cp "$SHOT" "$HOME/tmp/see.png" || exit 1
export OPENAI_API_KEY=local-noop DSH_PERMISSION_MODE=danger-full-access
node --expose-internals /data/data/com.termux/files/usr/lib/node_modules/dsh-termux/lib/bin.js \
  --profile headless \
  --patch "$HOME/.dsh/profiles/web/cordis.patch.yml" \
  --patch "$HOME/dsh-phone/vision-overlay.yml" \
  --permission-mode danger-full-access \
  "Use read_image on /data/data/com.termux/files/home/tmp/see.png. $1"
