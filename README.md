# 字幕校对 / 重建 / 外挂 SRT

> AI 转写字幕（B 站 CC 字幕、TTS 语音转写）满屏同音错字——**对照成稿逐处修正、按原文重建分块、导出播放器直接能挂的 SRT**。
> 四条路线都自带脚本，**纯标准库、不联网、不需要 cookie**（`fetch` 那一层除外，见下）。

## 这是什么

字幕校对的坑不在「改错字」，在**改完之后不能把结构弄坏**：

- **块长**：太碎读不过来，太长一刀切在半句上。实测三轮定版值：**8–26 字，平均 ~14**（v9 试过贪心合并到平均 23.8 字，被否决——过长 + 切出半句难看）
- **定位**：以原文行（原文段落）为基础分块，不是按字幕块顺序改；章节标题独立成块
- **验证**：交付前跑匹配度（规范化后全文 diff）——**目标 100%**，不是「看着差不多」
- **交付**：产出 `原名-校对版.md/srt`，**原文件一个字不动**；格式校验通过才算交付

一条最贵的教训：**list 级校验会假绿**。替换行重建时丢行尾 `\n` → 写盘相邻行粘连，元素数、时间戳数都不变，校验全过。校验必须内容级（`''.join(...).splitlines()` 数行 + 比时间轴），替换时保留行尾换行。

## 四条路线怎么选

| 手上是什么 | 走哪个 |
|:--|:--|
| `.srt` ＋ 原文/成稿 | 对照校对 → `references/srt-workflow-and-rebuild.md` |
| 只有 AI 字幕、没有原稿（口播/解说） | 无基准校对 → `references/no-baseline-proofreading.md` |
| 要按原稿重做字幕（块太碎／断章） | 重建模式 → `references/srt-workflow-and-rebuild.md` §重建模式 |
| 多人语音 ASR 导出稿（`发言人N`＋时间戳） | **先量化再决定修不修** → `references/multi-speaker-asr.md` |
| 要出外挂 SRT | `scripts/subtitle.py to-srt` |

多人语音那一路的判据最反直觉：**拿不准数 ≥ 实锤数、要动手的条数过半 → 直接跟委托人摊牌别硬修**。硬改＝创作，不是校对；这类稿的结论常常是「不做稿，只做索引」。

## CLI

```bash
python3 scripts/subtitle.py proofread <md|目录> --fixes fixes.json [--force] [-v]
    # fixes.json: {"global": {"乌蠢":"污纯"}, "files": {"文件子串": {"无视角":"无视掉"}}}
    # global 跨期统一 + files 定向防误伤；出 <part>_字幕校对版.md，标题行自动改「校对版」
python3 scripts/subtitle.py to-srt <md> [--video <视频目录>] [--dur 秒]
    # md → srt；--video 时输出与 mp4 同名（ffprobe 拿时长，播放器同目录自动挂载）
python3 scripts/subtitle.py fetch <bvid> --dir <视频目录>     # ⚠️ 需要外部拉取脚本，见下
```

- **`fetch` 那一层不自包含**：它调用一个外部的 B 站字幕拉取脚本（作者环境用环境变量 `BILI_SUBTITLE_SCRIPT` 指定路径），并需要 B 站 cookie。**其余三段纯本地**。
- fixes.json 生成法：先 diff 原文/校对版拿真实改动对，能自动复现的才是安全表（实测手工 20 处 → CLI 5/5 逐字一致）
- 替换值里不能含被替换词本身（工具会拦下自循环替换：替换后仍有残留 = 报错，不是静默通过）

## 工具（5 个，纯标准库）

| 脚本 | 干什么 |
|:---|:---|
| `subtitle.py` | 三段全链 CLI（proofread / to-srt / fetch），见上 |
| `proofread_diff.py` | **第一步就用它**：解析 SRT + 完整性检查 + 规范化全文 diff + 匹配度 + 差异块输出 |
| `rebuild_srt.py` | 重建模式 v10：以原文行为基础分块 + 章节标题独立 + 块长 8–26 + 时间轴插值 + 自动验证 |
| `md_cues_to_srt.py` | 时间轴 md → SRT（同秒多条合并成双行块；`to-srt` 的底层） |
| `asr_export_parse.py` | 多人语音 ASR 导出件（`发言人N + 时间戳 + 文本`）→ 逐条 JSON + 原文 md；**按形态扫时间戳（`MM:SS` 与 `HH:MM:SS` 混排）并打印三条自检** |

⚠️ 时间戳混排是踩过的坑：只写单形态正则会**静默丢掉大半条目**（实测 2359 条只解出 722 条 = 漏 69%，而剩下的读着都「正常」）。格式异常先跑 `asr_export_parse.py`，别现场手写解析器。

## 目录

| 路径 | 内容 |
|:---|:---|
| `SKILL.md` | 入口：分流表 · CLI 用法 · 脚本表 |
| `references/srt-workflow-and-rebuild.md` | 七步流程（解析／完整性／规范化 diff／定位错词／按块修正／验证／交付纪律）+ 重建模式 + 错误分类原则 |
| `references/no-baseline-proofreading.md` | 无基准校对模式 |
| `references/multi-speaker-asr.md` | 多人语音 ASR：小样量化口径、说话人聚簇 ≠ 真人、家族频扫 |
| `references/pitfalls.md` | 通用坑（双坐标系／插值／硬切／碎尾） |

## 读者须知

文中出现的 `bin/subtitle`、`bin/asr`、`bin/bili-cookie-path`、`bilibili-api-ops`、`wufan-forum` 都是**作者环境**的工具与 skill（不在本仓、也不影响判据）——照自己的项目替换即可。实测数字里的课程名／实录名读作「某场三小时录音样本」。

## 姊妹仓库

- [liya-prose-quality-metrics](https://github.com/feverZHONG/liya-prose-quality-metrics) —— 稿子质量的量化体检（同一条「先量再改」的线，动手改稿前先量）
- [liya-subtraction-skill](https://github.com/feverZHONG/liya-subtraction-skill) —— 技能库做减法：减法优先、去重、归档、拆薄
- [liya-persona-authoring](https://github.com/feverZHONG/liya-persona-authoring) —— 给 AI agent 写它自己的身份文件（SOUL.md）
- [liya-sillytavern-cards](https://github.com/feverZHONG/liya-sillytavern-cards) · [liya-tavern-card-refinement](https://github.com/feverZHONG/liya-tavern-card-refinement) · [liya-sillytavern-worldbook](https://github.com/feverZHONG/liya-sillytavern-worldbook) —— 酒馆角色卡三件（写卡 / 精修 / 世界书）
- [liya-vision-recognition-traps](https://github.com/feverZHONG/liya-vision-recognition-traps) —— 视觉模型识图陷阱：实测陷阱 + 真 OCR 通道 + 两图差分
- [liya-chat-game-referee](https://github.com/feverZHONG/liya-chat-game-referee) · [liya-spy-game](https://github.com/feverZHONG/liya-spy-game) · [liya-sea-turtle-soup](https://github.com/feverZHONG/liya-sea-turtle-soup) —— 聊天里能玩的三件（回合制裁判引擎 / 谁是卧底 / 海龟汤）
- [liya-delegation-and-verification](https://github.com/feverZHONG/liya-delegation-and-verification) —— 委派与验收：给子代理写任务书、并行隔离、把「自报」验成事实
- [liya-ruozhiba-wordbank](https://github.com/feverZHONG/liya-ruozhiba-wordbank) —— 弱智吧题防御手册：中文互联网逻辑陷阱题 160 道逐题拆解 + 三连防御法
- [liya-corpus-line-mining](https://github.com/feverZHONG/liya-corpus-line-mining) —— 从本地语料／会话库挖可复用原句：候选池筛选 + 人审落库（纯标准库，零依赖）
- [liya-story-revision-plan](https://github.com/feverZHONG/liya-story-revision-plan) —— 小说全稿修订方案：评估／缺口清单／逐章大纲／信息融合／优先级（含标准模板）

## 提思路 / 提修正

- 你那边遇到的字幕形态、新的错词家族、块长基线 → 开 [Issue](https://github.com/feverZHONG/liya-subtitle-proofreading/issues)，把「什么形态、错在哪、你怎么修的」写清
- 想直接改 → Fork + PR

## 许可

**双许可**——文档与代码分开：

- **代码**（`scripts/` 下的文件）：**MIT** —— 拿去用、改、再发，保留版权声明即可。
- **文档**（`SKILL.md`、`references/`、本 README 的正文）：**[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)** —— 可以自由使用、改编、连商用都行，**但要署名**（莉娅 / [@feverZHONG](https://github.com/feverZHONG)）并注明来源。

两份全文：`LICENSE`（MIT）／`LICENSE-DOCS`（CC BY 4.0）。

---

*莉娅（[@feverZHONG](https://github.com/feverZHONG)）· 宇宙美好记录官*
