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

## 4. 拔线 / 重启后连不上？**端口别写死**

```bash
bash ~/dsh-phone/fix-adb.sh           # 自动找回通道（推荐）
bash ~/dsh-phone/fix-adb.sh status    # 只看现在通不通
bash ~/dsh-phone/fix-adb.sh ensure    # 静默模式，只输出端口号（appctl 内部用）
```

### 为什么"拔了 USB 就连不上"

这是安卓自己的规矩，不是你配置错了：

1. **无线调试会自己关** —— 重启、断 Wi-Fi、换网络、关掉开发者选项，`无线调试` 开关都会回到关闭。
2. **端口是随机的** —— 每次重新打开无线调试，`adbd` 监听的端口都会换（这次 5556，下次可能 4 万多）。
   所以网上"写死 5556"的教程在你重启之后必然失效。
3. **列不出端口** —— Android 9 起普通 App 读不了 `/proc/net/tcp`，`ss` / `netstat` 在 Termux 里
   全是 `Permission denied`（本项目实测确认），`adb mdns services` 在 Termux 的 adb 上也提示不支持。
   **所以只能反向探测。**

### fix-adb.sh v2 怎么找端口

| 顺序 | 方法 | 实际耗时 |
|---|---|---|
| 1 | 已经在连着的 → 直接记下端口 | 0.1s |
| 2 | 记住的端口 + 历史端口（`~/.dsh-adb-port`、`~/.dsh-adb-ports`）+ 5555/5556/5557 | **163ms** |
| 3 | TCP 探测 30000-49999 + 5555-5599 里"真在听"的端口，逐个 `adb connect` | **约 3s** |
| 4 | 桌面 Linux 上退回读 `/proc/net/tcp`（Android 上读不到，仅兜底） | —— |

第 3 步靠 `scripts/phone/find_adb_port.py`：256 线程并发探测，本地端口拒绝是瞬间的，
20000 多个端口 2 秒扫完。实测这台机器上"在听"的有 7 个端口，其中只有一个是 adb。

顺手还做两件事：
- 探测失败的端口会 `adb disconnect` 掉，`adb devices` 不会留一堆 `offline` 残渣（开场也会清一次）。
- 找到的端口写进历史，下次先试历史，通常 **0.2 秒**就连上，不用再扫。

### 连不上的两种人话结论

```
-- 没找到可连的 adb 端口 --
→ 手机上 设置 → 系统 → 开发者选项 → 打开「无线调试」，再跑一次 fix-adb.sh
→ 顺便把 Wi-Fi 设成「始终保持连接」（有的 ROM 叫「休眠时保持 Wi-Fi」），否则息屏久了又掉
```

- **`failed to authenticate` / 手机弹「允许 USB 调试」** → 点允许，勾选一律允许
- **`devices` 里是 `offline`** → 关掉无线调试再开一次（`fix-adb.sh` 现在会自动清这类残渣）

### 想开机就自动接回来（可选）

装了 [Termux:Boot](https://f-droid.org/packages/com.termux.boot/) 之后：

```bash
mkdir -p ~/.termux/boot
cp ~/dsh-phone/boot-fixadb.sh ~/.termux/boot/ && chmod +x ~/.termux/boot/boot-fixadb.sh
cat ~/dsh-phone/boot-fixadb.log      # 看每次开机有没有接上
```

它会在开机 25 秒后跑一次 `fix-adb.sh ensure`，把（变过的）端口找出来记住。
**前提是无线调试还开着** —— 系统要是把它关了，adbd 没在监听，任何脚本都救不回来，只能手动再打开。

### appctl 已经会自愈

`appctl.sh` 不再写死端口：它先看你上次的端口，连不上就静默调 `fix-adb.sh ensure` 再试，
所以你直接跑 `appctl.sh text` 就可能自己连回来了（实测：手动 `adb disconnect` 后直接 `appctl.sh cur`，自动重连成功）。


---

## 5. 传文件的几个坑

- **中文路径**：`adb pull 中文名` 经常失败。用 `adb exec-out cat > 本地名`，或先 `adb shell cp` 到 `/sdcard/Download/` 再拉。
- **`/sdcard/Android/data/` 下的东西**：Termux 用户无权限（scoped storage），必须走 `adb shell`（shell 用户）读。
- **大文件**：`adb push` 比 `exec-out cat` 稳。
- 从电脑推到手机脚本：`cmd /c "type 脚本.sh | ssh ... \"cat > ~/目标.sh && sed -i 's/\r$//' ~/目标.sh\""`（务必去掉 CRLF）。
