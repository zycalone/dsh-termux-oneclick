#!/data/data/com.termux/files/usr/bin/bash
# 手机端 dsh 启动包装器（必须这样起，不能直接敲 dsh）
# 作用：
#   DSH_PERMISSION_MODE=danger-full-access  安卓无沙箱后端，必须全放行
#   --expose-internals                      绕过缺失的 node-addon-require-builtin 安卓原生绑定
# 安装位置：~/dsh-phone/dshx.sh   （chmod +x）
export OPENAI_API_KEY=local-noop
export DSH_PERMISSION_MODE=danger-full-access
exec node --expose-internals "$(readlink -f /data/data/com.termux/files/usr/bin/dsh)" web "$@"
