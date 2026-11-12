# dsh-termux-oneclick

把一台**安卓手机**（Termux，**不需要 root**、不需要电脑常开）变成能干活的 Agent：
识图答题、操作手机里的其它 App、上网查资料写论文、做章节测验、看视频出笔记、生成 PPT/Word/Excel/PDF。

本仓库是一套**在一台真实手机上跑通**的配置 + 脚本 + 踩坑记录。

> ⚠️ 本仓库**不含任何模型代理/逆向实现**。你需要自备一个 OpenAI 兼容的 `/v1/chat/completions` 端点
> （本机 `127.0.0.1:8787`、局域网、或任何云端兼容服务都行），填进配置即可。

---

## 能力一览

| 能力 | 靠什么实现 | 入口脚本 | 文档 |
|---|---|---|---|
| 识图 / 看图答题 | 视觉模型 + `read_image` | — | [docs/04](docs/04-识图.md) |
| 操作手机上的其它 App | 本机 adb + uiautomator | `appctl.sh` | [docs/03](docs/03-操作其它App.md) |
| 章节测验/在线答题（高正确率） | 多模型投票 + 检索兜底 | `quiz.py` | [docs/05](docs/05-满分答题流水线.md) |
| 看视频出笔记 | 截屏抽帧 + 视觉模型读画面 | `screenwatch.py` / `vidnote.py` | [docs/06](docs/06-看视频出笔记.md) |
| 上网查资料 / 写论文 | `web_fetch` 抓 Bing / arXiv / Crossref / PubMed | — | README「联网」 |
| 生成文档 | python-pptx / python-docx / openpyxl / reportlab | — | README「文档」 |
| 手机自我接管（ADB/SSH） | adb tcpip + sshd | `fix-adb.sh` | [docs/02](docs/02-接管手机-ADB与SSH.md) |
| 一句话交给 Agent | headless CLI | `ask.sh` | [docs/01](docs/01-快速开始.md) |

---

## 硬性前提

- Android **arm64**（`aarch64`），Termux（F-Droid 或 GitHub 版，**不要用 Google Play 版**）
- Node ≥ 20（实测 v24）、Python ≥ 3.10（实测 3.14）
- `dsh-termux` 预编译包（上游发布，见 [docs/01](docs/01-快速开始.md)）
- 一个 OpenAI 兼容端点 + API Key（**不提供**，自备）

---

## 目录结构

```
.
├── README.md
├── docs/                       # 全部使用说明
│   ├── 01-快速开始.md
│   ├── 02-接管手机-ADB与SSH.md
│   ├── 03-操作其它App.md
│   ├── 04-识图.md
│   ├── 05-满分答题流水线.md
│   ├── 06-看视频出笔记.md
│   ├── 07-提示词大全.md
│   ├── 08-能力清单与实测.md
│   ├── 09-常见问题.md
│   └── 10-AGENTS配置.md
├── config/
│   ├── cordis.patch.yml        # dsh 在安卓上必须的配置补丁
│   ├── dshx.sh                 # dsh 启动包装器（必须带 --expose-internals）
│   ├── up.sh                   # 一键启动 + 打印网页 token 地址
│   ├── AGENTS.md               # 给 Agent 的行为规矩（可直接放进工作区）
│   └── vision-overlay.yml      # headless 时补上视觉模型
├── scripts/
│   ├── phone/                  # 装到手机 ~/dsh-phone/
│   ├── phone/patches/          # dsh 在 Termux 上的补丁与探测脚本
│   ├── pc/                     # 电脑侧推送/修复脚本（PowerShell）
│   └── extras/                 # 附加示例：从 docx 截图批量提答案
├── LICENSE
└── .gitignore
```

---

## 快速开始（5 步）

```bash
# 1) Termux 基础环境
pkg update -y && pkg install -y nodejs python git openssh tmux termux-api

# 2) 装 dsh-termux（用你自己的 tarball / 上游包）
npm i -g ./dsh-termux.tgz        # 或 npm i -g dsh-termux

# 3) 放配置
mkdir -p ~/.dsh/profiles/web ~/dsh-phone
cp config/cordis.patch.yml ~/.dsh/profiles/web/cordis.patch.yml
cp config/dshx.sh config/up.sh ~/dsh-phone/ && chmod +x ~/dsh-phone/*.sh

# 4) 起服务（会打印 http://127.0.0.1:3080/?token=...）
bash ~/dsh-phone/up.sh

# 5) 装能力脚本
cp scripts/phone/*.sh scripts/phone/*.py ~/dsh-phone/ && chmod +x ~/dsh-phone/*.sh
```

浏览器打开上一步打印的 `?token=` 地址 → 就能对话了。

详细步骤与逐条验证：[docs/01-快速开始.md](docs/01-快速开始.md)

---

## 模型接入（自备端点）

编辑 `config/cordis.patch.yml` 里这一段：

```yaml
- id: llm-pi-ai
  config:
    providers:
      openai:
        displayName: 本地网关
        api: openai-completions
        baseURL: http://127.0.0.1:8787/v1     # ← 换成你的端点
        apiKeyEnv: OPENAI_API_KEY
        models:
          - id: <文本模型 id>
            name: <显示名>
          - id: <视觉模型 id>
            name: <显示名>
            input: [text, image]               # ← 视觉模型必须声明
```

```bash
export OPENAI_API_KEY=你的key        # dshx.sh 里默认写的是 local-noop
```

**四条血泪结论**（不改就起不来，详见 [docs/01](docs/01-快速开始.md#为什么这些配置非改不可)）：

1. `--expose-internals` 必须加，否则安卓缺 `node-addon-require-builtin` 原生绑定直接崩。
2. `sandbox-policy.mode: danger-full-access` + `approval.policy: never`，安卓没有沙箱后端。
3. **模型 ID 必须手写**：很多兼容端点的 `/v1/models` 返回格式与 dsh 期望的不一致，自动拉取会是空的。
4. 视觉模型不声明 `input: [text, image]`，图片会被**静默丢弃**，模型只看到占位符——这是"为什么它说看不见图"的根因。

---

## 手机自我接管（不需要电脑）

```bash
pkg install -y android-tools          # 提供 adb
adb connect 127.0.0.1:5556            # 连自己（需先在同一 Wi-Fi 下开一次无线调试）
bash ~/dsh-phone/appctl.sh text       # 读当前屏幕的所有文字 + 坐标
bash ~/dsh-phone/appctl.sh tap-text "发送"
```

> 每次从别的进程调 adb，记得加 `</dev/null`，否则 adb 会挂着等 stdin。

详见 [docs/02](docs/02-接管手机-ADB与SSH.md)、[docs/03](docs/03-操作其它App.md)。

---

## 常用命令速查

```bash
bash ~/dsh-phone/up.sh                          # 起 dsh，打印 token 网页地址
bash ~/dsh-phone/ask.sh "把桌面截图，读一下上面写了什么"
bash ~/dsh-phone/appctl.sh cur|text|shot|apps    # 当前 App / 屏幕文字 / 截图 / 装了什么
bash ~/dsh-phone/appctl.sh open com.chaoxing.mobile
bash ~/dsh-phone/appctl.sh tap-text "登录" | tap X Y | type abc | key KEYCODE_BACK
python ~/dsh-phone/quiz.py solve ~/tmp/q.json    # 多模型投票答题
python ~/dsh-phone/screenwatch.py --minutes 15 --interval 20   # 看视频出笔记
bash ~/dsh-phone/fix-adb.sh                      # 手机重启后修 adb
```

---

## 联网与文档能力

- **搜索**：`web_fetch` 抓 `https://cn.bing.com/search?q=...`（手机端 `web_search` 通常没有 provider）。
- **论文**：arXiv / Crossref / PubMed 的公开 API 直接可用；Semantic Scholar 会 429 限流。
- **文档**：`python-pptx` / `python-docx` / `openpyxl` / `reportlab` 直接生成；
  **没有 LibreOffice**，docx/pptx 转 PDF 只能重排或用 WPS 导出。

---

## 实测状态（诚实清单）

| 项 | 状态 |
|---|---|
| dsh web 界面 | ✅ 可用 |
| 视觉识图 | ✅ 可用（需声明 image 的视觉模型） |
| 手机 App 自动化 | ✅ 可用（读屏依赖 a11y，**微信读不到**） |
| 音视频理解 | ❌ 无音视频模型，只能抽帧读画面 |
| docx/pptx → pdf | ❌ 手机无 LibreOffice |
| `/tmp` 写入 | ❌ Termux 下不可写，用 `~/tmp` |
| 微信自动化 | ❌ uiautomator 拿到的是空树 |

---

## 安全与免责

- 服务**只监听 127.0.0.1**，不要改 `--host 0.0.0.0`；不要把 token 网页地址发给别人。
- 不要用本仓库做：代付、输入支付密码、绕过验证码、登录他人账号、批量刷课等违规用途。
- 自动化操作第三方 App 可能违反其用户协议，**后果自负**。
- Agent 会读写你手机上的文件（`danger-full-access`），请只在自己的设备上使用。
- 模型输出可能出错，考试、财务、医疗类内容请自己复核。

## License

MIT，见 [LICENSE](LICENSE)。
