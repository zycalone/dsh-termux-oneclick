# 10 · AGENTS.md：给 Agent 装"工作规矩"

## 这是什么

`AGENTS.md` 是放在**工作区里的一份说明文件**，dsh 每次在这个目录里干活时会读它。
它决定了 Agent 的默认行为：用什么模型看图、上网怎么搜、点按钮的规矩、什么绝对不许做。

仓库里给了一份可直接用的：[config/AGENTS.md](../config/AGENTS.md)

```bash
cp config/AGENTS.md ~/AGENTS.md              # 家目录
cp config/AGENTS.md ~/dsh日常工作区/AGENTS.md  # 工作区
```

---

## 它应该包含什么

一份好用的 AGENTS.md 有 6 块：

1. **环境事实**：跑在 Termux、没有 LibreOffice、没有 `/tmp`、没有 root。
2. **能力对应的正确做法**：
   - 识图 → 必须用声明了 `image` 的模型
   - 上网 → `web_search` 不可用时改抓 `cn.bing.com/search`
   - 查论文 → 直接打 arXiv / Crossref / PubMed 的 API
3. **操作 App 的规矩**：优先点文字、每次截图复核、别抢用户手机。
4. **答题的规矩**：多模型投票、按选项原文点、提交前给用户过目、别重复提交。
5. **红线**：不代付、不要验证码/密码、考试签到人脸要停下来问。
6. **已知坑**：中文路径、CRLF、`/data/data` 不可读、scoped storage。

---

## 一段可以直接抄的写法

```markdown
## 识图
- 图片必须用声明了 image 的视觉模型，否则会被丢弃。
- 先抄文字，再解题；两步比分一步准。

## 上网
- web_search 没配置就别调；用 web_fetch 抓 https://cn.bing.com/search?q=<关键词>
- 论文优先用 arXiv / Crossref / PubMed 的 API。

## 操作 App
- 用 ~/dsh-phone/appctl.sh：text 读屏 → tap-text "文字" 点 → shot 截图复核
- 不猜坐标；点完必须截图确认。
- 用户正在用手机时先问一句。

## 红线
- 不代付、不要支付密码/验证码；考试、签到、人脸识别先问用户。
```

---

## 维护建议

- 每踩一个坑就往里加一条，比写笔记有用得多——Agent 下次就不会再犯。
- 别写成散文，写成**祈使句 + 具体命令**。
- 不同的活可以放在不同目录，各自一份 AGENTS.md（比如 `~/学习/` 一份、`~/工作/` 一份）。
- 版本化：把这个文件也纳入 git，回滚方便。
