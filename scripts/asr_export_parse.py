#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析「说话人 + 时间戳」型 ASR 导出（docx / txt）→ 逐条 JSON + 原文 md。

用于多人语音（语音频道/会议/开黑录音）的 ASR 导出件：形如
    发言人1   00:12
    文本一行
    发言人2   01:03:44
    文本一行
**时间戳会在 1 小时处由 MM:SS 切成 HH:MM:SS**，只写单形态正则会静默丢掉大半条目。
本脚本按形态扫描 + 三条自检，把「漏解析」变成会喊出来的报错。

用法:
    python3 asr_export_parse.py <导出.docx|txt> [-o 输出目录] [--quiet]

产出（输出目录默认与输入同目录）:
    <名>_原文.md   —— 逐条 `[HH:MM:SS] 发言人N：文本`，原样不改一字
    <名>.json      —— [[发言人号, 秒, 文本], ...] 供后续替换/统计

自检（别跳，只看 stdout 最后一块）:
    条数 / 各说话人条数与字数 / 时长 / 时序倒置数 / 疑似未匹配行 / 未消费散行
"""

import argparse
import collections
import json
import os
import re
import sys
import zipfile

SPK_RE = re.compile(r"^\u53d1\u8a00\u4eba\s*(\d+)\s+(\d{1,3}):(\d{2})(?::(\d{2}))?\s*$")


def docx_paragraphs(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return [
        "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))
        for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    ]


def read_paragraphs(path):
    if path.lower().endswith(".docx"):
        return docx_paragraphs(path)
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read().splitlines()


def secs(m):
    a, b, c = int(m.group(2)), int(m.group(3)), m.group(4)
    return a * 3600 + b * 60 + int(c) if c is not None else a * 60 + b


def join_text(buf):
    s = buf[0]
    for t in buf[1:]:
        s += (" " if (s and s[-1].isascii() and t[:1].isascii()) else "") + t
    return s


def parse(paras):
    turns, dropped = [], []
    i, n = 0, len(paras)
    while i < n:
        s = paras[i].strip()
        if not s:
            i += 1
            continue
        m = SPK_RE.match(s)
        if not m:
            dropped.append(s)
            i += 1
            continue
        spk, t = int(m.group(1)), secs(m)
        j, buf = i + 1, []
        while j < n:
            u = paras[j].strip()
            if not u:
                j += 1
                continue
            if SPK_RE.match(u):
                break
            buf.append(u)
            j += 1
        turns.append([spk, t, join_text(buf) if buf else ""])
        i = j
    return turns, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out-dir", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    paras = read_paragraphs(a.src)
    turns, dropped = parse(paras)
    if not turns:
        print("[FAIL] 一条都没解出来 —— 先看下面的疑似行，格式多半不是「发言人N + 时间戳」", file=sys.stderr)
        for l in [x for x in paras if x.strip()][:20]:
            print("   ", l[:120], file=sys.stderr)
        return 2

    nonempty = [l.strip() for l in paras if l.strip()]
    loose = [l for l in nonempty if l.startswith("\u53d1\u8a00\u4eba") and not SPK_RE.match(l)]
    shapes = collections.Counter(
        re.sub(r"\d", "#", l) for l in nonempty if SPK_RE.match(l)
    )
    turns_c = collections.Counter(t[0] for t in turns)
    chars_c = collections.Counter()
    for sp, _, x in turns:
        chars_c[sp] += len(x)
    inv = sum(1 for x, y in zip(turns, turns[1:]) if y[1] < x[1])
    dur = turns[-1][1]

    out_dir = a.out_dir or os.path.dirname(os.path.abspath(a.src))
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(a.src))[0]
    md_path = os.path.join(out_dir, base + "_原文.md")
    js_path = os.path.join(out_dir, base + ".json")

    def fmt(s):
        return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# %s\n\n> 由 asr_export_parse.py 解析，**逐条原样**，未改一字。\n"
                "> 实测：%d 条 / %d 字 / 时长 %s / %d 个说话人簇\n\n"
                % (base, len(turns), sum(chars_c.values()), fmt(dur), len(turns_c)))
        for sp, t, x in turns:
            f.write("[%s] \u53d1\u8a00\u4eba%d\uff1a%s\n" % (fmt(t), sp, x))
    json.dump(turns, open(js_path, "w", encoding="utf-8"), ensure_ascii=False)

    if not a.quiet:
        print("=== 自检（三条必须干净，脏了就是解析漏了） ===")
        print("时间戳形态:", dict(shapes))
        print("疑似未匹配行(%d):" % len(loose), loose[:5])
        print("未消费散行(%d, 正常只有标题/导出时间那几行):" % len(dropped), dropped[:5])
        print("时序倒置(%d, 应为 0):" % inv)
        print("--- 内容 ---")
        print("条数:", len(turns), "| 字数:", sum(chars_c.values()), "| 时长:", fmt(dur))
        print("各说话人:", dict(sorted(turns_c.items())), dict(sorted(chars_c.items())))
        print("产出:", md_path)
        print("     ", js_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
