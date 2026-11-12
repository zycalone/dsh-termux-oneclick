# 03 · 操作手机上的其它 App

核心脚本：`scripts/phone/appctl.sh`（内部用本机 adb + `uiautomator` 解析控件树，自动带 `</dev/null`）。

---

## 命令表

```bash
bash ~/dsh-phone/appctl.sh cur                    # 当前前台 App 包名/Activity
bash ~/dsh-phone/appctl.sh text                   # 读当前屏幕：文字 + 坐标 + 是否可点
bash ~/dsh-phone/appctl.sh shot                   # 截屏，打印 png 绝对路径
bash ~/dsh-phone/appctl.sh apps                   # 已装第三方 App 包名
bash ~/dsh-phone/appctl.sh open com.tencent.mm    # 启动 App
bash ~/dsh-phone/appctl.sh tap-text "发送"         # 点「含该文字」的控件（首选）
bash ~/dsh-phone/appctl.sh tap 540 1800           # 点坐标（找不到文字时才用）
bash ~/dsh-phone/appctl.sh type "hello"           # 输入（英文数字；中文见下）
bash ~/dsh-phone/appctl.sh key KEYCODE_BACK       # 按键
bash ~/dsh-phone/appctl.sh swipe 540 1600 540 600 # 滑动
```

---

## 标准流程

```
open 包名 → text 看有什么 → tap-text "文字" → shot 截图 → 看图复核 → 不对就重来
```

四条规矩：

1. **优先 `tap-text`，别猜坐标**：App 改版后坐标全废，文字一般还在。
2. **每次关键操作后 `shot` + 让视觉模型看图复核**，别凭想象宣布成功。
3. 界面加载慢就 `sleep 2` 再 `text`；读不到多半是还在加载。
4. **中文输入**：`input text` 只支持 ASCII。办法：① 用英文/拼音；② 让用户自己粘；
   ③ 用 App 内的「粘贴」按钮配合剪贴板（先让用户复制好）。

---

## 实战要点

- **微信、部分加固 App 读不到控件**：`uiautomator dump` 只返回几十字节的空树。
  这类 App 只能截图 + 视觉模型看图，**或者说实话：自动化不了，让用户自己点几下**。
- **不要抢用户的手机**：先 `cur` 看前台是什么；如果用户正在用（比如在看视频/聊天），先问一句。
- **弹窗与广告**：`text` 里找「关闭」「跳过」「我知道了」先点掉，再干正事。
- **列表滚动**：`text` 只给当前屏幕；要全量就先 `swipe` 多次，每次 `text` 累积去重。
- **验证码 / 支付 / 人脸**：到这一步就停，交给用户。

---

## 示例：进学习通看有哪些任务点

```bash
A=~/dsh-phone/appctl.sh
bash $A open com.chaoxing.mobile; sleep 6
bash $A text | head -30          # 找「我的课程」
bash $A tap-text "我的课程"; sleep 4
bash $A tap-text "<课程名>"; sleep 5
bash $A shot                     # 截图后交给视觉模型读「未完成」标记
```
