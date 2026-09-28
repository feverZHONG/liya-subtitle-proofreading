---
name: subtitle-proofreading
tier: T2  # T分级: T2=直接做 / T1=先请示 / T0=一律拒
description: 字幕收档/校对/重建/外挂SRT——B站AI字幕拉取存档(subtitle CLI fetch)、无基准校对(proofread)、SRT对照原稿逐字对齐、md转srt外挂、多人语音ASR导出件（发言人分离）校对。触发：收字幕、校对字幕、srt修正、字幕转srt、字幕对照原文、字幕块太碎要合并、甩来语音识别稿（docx/会议导出）说"错误一抓一大把"。
---

# 字幕校对/重建 · Subtitle Proofreading

> AI 转写字幕（B站 CC 字幕/TTS 语音转写）满屏同音错字，对照成稿/朗读稿逐处修正。
> 2026-08-13 一场三小时课程录音的实战（三轮）：
> 第一轮按块修 39 处错字（匹配度 99.2%→99.6%）；第二轮按反馈重建（v9：逐字取原文+贪心合并，760 块/平均 23.8 字）被**打回**（过长+切出半句难看）；第三轮 v10 定版：以原文行为基础分块，1590 → 1324 块，平均 9.5 → 13.7 字，规范化匹配度 **100%**，章节标题独立。

## 触发场景

- 手上有一个 .srt 字幕 + 一份原文/成稿，要「校对字幕」「修正错字」「看看字幕对不对」
- 从视频提取的 AI 字幕要变成可用成品
- 无原稿基准的纯 AI 字幕「顺手收录+校对」→ 走下方**无基准校对模式**（2026-09-09 合金弹头教学 5P 实战）

## 四种模式怎么选

| 手上是什么 | 走哪个 |
|:--|:--|
| `.srt` ＋ 原文/成稿 | 对照校对 → `references/srt-workflow-and-rebuild.md`（§流程 ＋ §错误分类原则） |
| 只有 AI 字幕、无原稿（B站口播/解说） | 无基准校对 → `references/no-baseline-proofreading.md` |
| 要按原稿重做字幕（块太碎／断章） | 重建模式 → `references/srt-workflow-and-rebuild.md` §重建模式 |
| 多人语音 ASR 导出稿（发言人N＋时间戳） | **先量化再决定修不修** → `references/multi-speaker-asr.md` |
| 要出外挂 SRT | `subtitle to-srt`（见下方 CLI 段） |

> 通用坑（双坐标系／插值／硬切／碎尾）见 `references/pitfalls.md`。


## 无基准校对 CLI · subtitle（2026-09-09 定版）

> 入口：`python3 scripts/subtitle.py`。三段全链，收字幕一条龙（作者环境另有 `bin/subtitle` 壳）。

```
subtitle fetch <bvid> --dir <视频目录> [--pages all|1,3] [--author 名]
    # 拉 B站 AI 字幕落 <视频目录>/字幕/<part>_字幕原文.md（part=B站分P名，自动与 mp4 同名对齐）
    # 字幕本体由外部拉取脚本提供（作者环境：bilibili-api-ops 里的 bili_subtitle.py，不在本仓）；
    # 作者名自动从标题 by.XXX 提取
subtitle proofread <md|目录> --fixes fixes.json [--force] [-v]
    # fixes.json: {"global": {"乌蠢":"污纯"}, "files": {"文件子串": {"无视角":"无视掉"}}}
    # global 跨期统一 + files 定向防误伤；出 <part>_字幕校对版.md，标题行自动改「校对版」
subtitle to-srt <md> [--video <视频目录>] [--dur 秒]
    # md → srt；--video 时输出与 mp4 同名（ffprobe 自动拿时长，播放器同目录自动挂载）
```

- fetch 前置（**只有作者环境有这一层**）：cookie 由本地凭据工具提供；Playwright 浏览器目录走 `PW_DIR`（默认 `<TMPDIR>/pw`，存在可用版本时自动接管 `PLAYWRIGHT_BROWSERS_PATH`）。**本仓自带的 proofread／to-srt／ASR 解析三段是纯本地纯标准库，不需要 cookie。**
- fixes.json 生成法：先 diff 原文/校对版拿真实改动对，能自动复现的就是安全表（2026-09-09 回归：手工 20 处 → CLI 5/5 逐字一致）
- **list 级校验的盲区**：替换行重建时丢行尾 `\n` → `writelines` 写盘相邻行粘连，list 元素数/时间戳数都不变、校验假绿。校验必须内容级：`''.join(new_lines).splitlines()` 后数行 + 比时间轴；替换时保留 `line.endswith('\n')`

## 多人语音 ASR 导出稿

见 `references/multi-speaker-asr.md` —— 先 5 分钟小样量化（实锤／拿不准／受影响条数占比）再谈铺不铺开、说话人聚簇 ≠ 真人（认人靠证据）、家族频扫、`scripts/asr_export_parse.py` 解析双格式时间戳。

## SRT 工作流（对照校对 · 重建）

见 `references/srt-workflow-and-rebuild.md` —— 七步流程（解析／完整性／规范化 diff／定位错词／按块修正／验证／交付纪律）、重建模式（以原文行为基础分块 ＋ 章节保护 ＋ 块长 8-26）、错误分类原则（哪些修哪些不修）。



## 坑

见 `references/pitfalls.md`。

## 脚本

- `scripts/proofread_diff.py <srt> <txt>` — 解析 SRT + 完整性检查 + 规范化全文 diff + 匹配度 + 差异块输出（第一步就用它，别现场重写解析）
- `scripts/rebuild_srt.py <srt> <txt> [out] [--max-len 22]` — 重建模式 v10（2026-08-13 三轮定版）：以原文行为基础分块 + 章节标题独立 + 块长 8-26（平均 ~14）+ 时间轴插值 + 自动验证匹配度。⚠️ 跑前确认**输入是原始 SRT**（别用上次输出的校对版，会读到中间产物）；跑完抽查开头/章节边界/结尾三处
- `scripts/subtitle.py` — 无基准校对全链 CLI，用法见上方「无基准校对 CLI · subtitle」段
- `scripts/asr_export_parse.py <导出.docx|txt> [-o 目录]` — 多人语音 ASR 导出件（`发言人N + 时间戳 + 文本`）解析为逐条 JSON + 原文 md；**按形态扫描时间戳（MM:SS 与 HH:MM:SS 混排）并打印三条自检**，另出 `<名>_原文.md` ／ `<名>.json`；判读格式异常先跑它，别现场写解析器（作者环境另有 `bin/asr` 壳，依赖本仓外的实现——本仓这份自包含）
- `scripts/md_cues_to_srt.py <md> [--dur 秒] [--out-dir 目录]` — 时间轴 md → SRT（同秒多条合并为一块双行、输出名去 `_字幕原文/字幕校对版` 后缀；to-srt 子命令的底层）

## 拆分记录

- **2026-09-28 拆薄**：SKILL.md 150 行 →（6.4KB）。按**模式**整组搬出（逐字、一条未删）：无基准校对 → `references/no-baseline-proofreading.md`；多人语音 ASR（含当日的实录评估基准）→ `references/multi-speaker-asr.md`；SRT 流程＋重建＋错误分类 → `references/srt-workflow-and-rebuild.md`；通用坑 → `references/pitfalls.md`。正文留**分流表**（手上是什么 → 走哪个）＋ CLI 段 ＋ 脚本表。
- **2026-09-28 对外发布版**：本机路径参数化（`BILI_SUBTITLE_SCRIPT`／`PW_DIR`／`TMPDIR`）、外部依赖明确标注「只有作者环境有这一层」（fetch 段需要 B 站 cookie 与外部拉取脚本，不在本仓）、私人实例中性化。本仓自带的三段（proofread／to-srt／ASR 解析）纯本地可独立跑。
