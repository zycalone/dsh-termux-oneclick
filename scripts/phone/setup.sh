#!/data/data/com.termux/files/usr/bin/bash
# setup.sh —— Termux 环境一键安装（Android arm64，无需 root）
# 用法：bash setup.sh [dsh-termux 的 tgz 路径]
# 说明：本脚本只装 dsh 与运行依赖，不包含任何模型代理；模型端点靠 config/cordis.patch.yml 填。
set -u

APP_DIR="$HOME/dsh-phone"
DSH_HOME="$HOME/.dsh"
PROFILE_DIR="$DSH_HOME/profiles/web"
TARBALL="${1:-}"

ok()   { echo "[OK] $*"; }
info() { echo "== $* =="; }
warn() { echo "[!] $*"; }
die()  { echo "[X] $*"; exit 1; }

info "1/5 安装系统依赖"
pkg update -y >/dev/null 2>&1 || warn "pkg update 有报错，继续"
pkg install -y nodejs python git openssh tmux termux-api android-tools curl >/dev/null 2>&1 \
  && ok "系统依赖就绪" || warn "部分包可能没装上，看上面报错"

NODE_V=$(node -v 2>/dev/null || echo none)
PY_V=$(python -V 2>&1 | awk '{print $2}')
info "Node=$NODE_V  Python=$PY_V"
case "$NODE_V" in
  v1[0-9]*|v2[0-9]*) ok "Node 版本可用" ;;
  none) die "没有 node，先 pkg install nodejs" ;;
  *) warn "Node 版本偏旧（建议 >= 20）" ;;
esac

info "2/5 安装 dsh-termux"
if command -v dsh >/dev/null 2>&1; then
  ok "dsh 已存在：$(command -v dsh)"
elif [ -n "$TARBALL" ] && [ -f "$TARBALL" ]; then
  npm i -g "$TARBALL" && ok "已从 $TARBALL 安装" || die "npm 安装失败"
else
  warn "没找到 dsh，也没给 tgz 路径。用法：bash setup.sh /path/to/dsh-termux.tgz"
fi

info "3/5 建目录与配置"
mkdir -p "$APP_DIR" "$PROFILE_DIR" "$HOME/tmp" "$HOME/.termux/boot" "$HOME/dsh日常工作区"
if [ -f ./config/cordis.patch.yml ]; then
  [ -f "$PROFILE_DIR/cordis.patch.yml" ] && cp "$PROFILE_DIR/cordis.patch.yml" "$PROFILE_DIR/cordis.patch.yml.bak"
  cp ./config/cordis.patch.yml "$PROFILE_DIR/cordis.patch.yml" && ok "写入 cordis.patch.yml"
else
  warn "当前目录下没有 config/cordis.patch.yml，跳过"
fi
for f in dshx.sh up.sh; do
  [ -f "./config/$f" ] && cp "./config/$f" "$APP_DIR/$f" && chmod +x "$APP_DIR/$f" && ok "安装 $f"
done
[ -f "./config/AGENTS.md" ] && cp "./config/AGENTS.md" "$HOME/AGENTS.md" && ok "安装 AGENTS.md（Agent 行为规矩）"
[ -f "./config/vision-overlay.yml" ] && cp "./config/vision-overlay.yml" "$APP_DIR/" && ok "安装 vision-overlay.yml"
for f in ./scripts/phone/*.sh ./scripts/phone/*.py; do
  [ -f "$f" ] && cp "$f" "$APP_DIR/"
done
chmod +x "$APP_DIR/"*.sh 2>/dev/null
ok "能力脚本已装到 $APP_DIR"

info "4/5 自检"
command -v dsh >/dev/null && ok "dsh 在 PATH 里" || warn "dsh 不在 PATH，检查 npm 全局前缀"
[ -f "$PROFILE_DIR/cordis.patch.yml" ] && ok "配置存在" || warn "缺 cordis.patch.yml"
grep -q "danger-full-access" "$PROFILE_DIR/cordis.patch.yml" 2>/dev/null && ok "沙箱模式已放开" || warn "沙箱模式没改"
python -c "import json,urllib.request" && ok "python 标准库可用"

info "5/5 下一步"
cat <<'TIP'
1) 编辑 ~/.dsh/profiles/web/cordis.patch.yml，把 baseURL 换成一个 OpenAI 兼容端点
2) export OPENAI_API_KEY=你的key（或写进 ~/dsh-phone/dshx.sh）
3) bash ~/dsh-phone/up.sh        # 起来后会打印 http://127.0.0.1:3080/?token=...
4) 想让 dsh 常驻：写开机自启
   echo 'bash $HOME/dsh-phone/up.sh >> $HOME/dsh-phone/boot.log 2>&1' > ~/.termux/boot/start.sh
   并装 Termux:Boot 并打开一次
5) 手机自我接管（可选）：bash ~/dsh-phone/fix-adb.sh
TIP
