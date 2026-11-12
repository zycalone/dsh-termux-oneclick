# 02 · 接管手机：ADB 与 SSH（不需要电脑）

让手机**自己控制自己**：读屏幕、点按钮、截图、传文件。全程不需要电脑。

---

## 1. 一次性准备：开无线调试

设置 → 关于手机 → 连点「版本号」7 次开开发者选项 → 开发者选项 → 打开 **无线调试**
（Android 11+ 直接在「无线调试 → 使用配对码配对设备」里配对；老系统：连一次 USB，电脑上 `adb tcpip 5556`）。

```bash
pkg install -y android-tools
adb connect 127.0.0.1:5556
adb devices          # 看到 127.0.0.1:5556  device 就成
```

> 只要不重启，连接就一直有效。重启后要重连（见第 4 节）。

---

## 2. 常用 adb 命令

```bash
adb shell dumpsys window | grep mCurrentFocus     # 当前前台 App
adb exec-out screencap -p > /sdcard/Download/a.png # 截图
adb shell input tap 540 1800                       # 点坐标
adb shell input swipe 540 1600 540 600 300         # 滑动
adb shell input keyevent KEYCODE_BACK              # 返回
adb shell input text "hello"                       # 输入（只能英文数字）
adb shell am start -n com.chaoxing.mobile/.ui.main.MainTabActivity   # 启动 App
adb shell pm list packages | grep -i note          # 找包名
```

**⚠️ 最容易踩的坑**：从别的程序（脚本、ssh、python）里调 adb，务必加 `</dev/null`：

```bash
adb -s 127.0.0.1:5556 shell pm list packages </dev/null
```

否则 adb 会等 stdin 而挂住，表现为"命令没反应"。

---

## 3. SSH 进手机（在手机上跑，也可从电脑进）

```bash
pkg install -y openssh
sshd                                   # 默认 8022 端口
passwd                                  # 设个密码
whoami                                  # 记住用户名，形如 u0_a123
```

手机内登录自己：

```bash
ssh -p 8022 -o StrictHostKeyChecking=no $(whoami)@127.0.0.1
```

**从电脑进手机**（电脑带 adb 时）：

```powershell
adb forward tcp:18022 tcp:8022
ssh -p 18022 -o StrictHostKeyChecking=no <用户名>@127.0.0.1
```

建议用密钥登录（`ssh-keygen` + 把 `~/.ssh/id_ed25519.pub` 追加进 `~/.ssh/authorized_keys`，`chmod 600`）。

---

## 4. 手机重启后修复

```bash
bash ~/dsh-phone/fix-adb.sh
```

它做的事：`adb kill-server` → `adb start-server` → `adb connect 127.0.0.1:5556` → 自检 `dumpsys`。
若仍失败：无线调试开关关掉再开，端口可能变了，`adb connect 127.0.0.1:<新端口>`。

---

## 5. 传文件的几个坑

- **中文路径**：`adb pull 中文名` 经常失败。用 `adb exec-out cat > 本地名`，或先 `adb shell cp` 到 `/sdcard/Download/` 再拉。
- **`/sdcard/Android/data/` 下的东西**：Termux 用户无权限（scoped storage），必须走 `adb shell`（shell 用户）读。
- **大文件**：`adb push` 比 `exec-out cat` 稳。
- 从电脑推到手机脚本：`cmd /c "type 脚本.sh | ssh ... \"cat > ~/目标.sh && sed -i 's/\r$//' ~/目标.sh\""`（务必去掉 CRLF）。
