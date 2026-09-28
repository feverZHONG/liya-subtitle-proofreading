#!/usr/bin/env python3
"""md 时间轴字幕 → SRT 外挂字幕。

形态：`[hh:mm:ss] 台词` 逐行（B站 AI 字幕落盘 md 的格式），转标准 SRT。
规则：
- 同秒多条合并为一块（文本 '\n' 连接，还原 AI 字幕多行块）
- 块 end = 下一条 start（无缝衔接）；最后一块 end 用 --dur 视频时长 clamp
- 跳过 # 标题 / > 注释 / 空行

用法：
  python3 md_cues_to_srt.py <md> [--dur 秒] [-o 输出.srt] [--out-dir 目录]
  python3 md_cues_to_srt.py <目录> [--dur 秒] [--out-dir 目录]   # 目录内批量
输出名自动去 `_字幕校对版`/`_字幕原文` 后缀（露出与 mp4 同名的 base）。

实战：2026-09-09 合金弹头5教学 5P（289/292/282/696/437 条）→ srt 276/278/265/655/411 块。
"""
import argparse, glob, os, re, sys

CUE_RE = re.compile(r'^\[(\d{2}):(\d{2}):(\d{2})\]\s*(.*)$')


def strip_suffix(base):
    for suf in ('_字幕校对版', '_字幕原文'):
        if base.endswith(suf):
            return base[: -len(suf)]
    return base


def parse_md(path):
    cues = []  # (start_sec, text)
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#') or line.startswith('>'):
            continue
        m = CUE_RE.match(line)
        if not m:
            print(f'[skip-unparsed] {path}: {line!r}', file=sys.stderr)
            continue
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        text = m.group(4).strip()
        cues.append((h * 3600 + mi * 60 + s, text))
    return cues


def fmt(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{s:02d},000'


def to_srt(cues, dur_s=None):
    # 同秒合并
    groups = []
    for t, text in cues:
        if groups and groups[-1][0] == t:
            groups[-1][1].append(text)
        else:
            groups.append([t, [text]])
    out = []
    n = len(groups)
    for i, (t, texts) in enumerate(groups):
        start = t
        end = groups[i + 1][0] if i + 1 < n else int(dur_s) if dur_s else start + 3
        if end <= start:
            end = start + 1
        out.append(f'{i + 1}\n{fmt(start)} --> {fmt(end)}\n' + '\n'.join(texts))
    return '\n\n'.join(out) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', help='md 文件或目录')
    ap.add_argument('--dur', type=float, default=None, help='视频时长(秒)，末块 clamp 用')
    ap.add_argument('-o', '--out', default=None, help='输出 srt 路径（单文件，目录批量时忽略）')
    ap.add_argument('--out-dir', default=None, help='输出目录（默认 md 所在目录；与 -o 二选一）')
    args = ap.parse_args()

    files = [args.path] if os.path.isfile(args.path) else sorted(
        f for f in glob.glob(os.path.join(args.path, '*.md'))
        if not os.path.basename(f).startswith('#'))
    if not files:
        print('未找到 md', file=sys.stderr)
        sys.exit(1)

    for md in files:
        cues = parse_md(md)
        if not cues:
            print(f'跳过(无字幕行): {md}', file=sys.stderr)
            continue
        if args.out and len(files) == 1:
            out = args.out
        else:
            d = args.out_dir or os.path.dirname(md) or '.'
            base = strip_suffix(os.path.splitext(os.path.basename(md))[0])
            out = os.path.join(d, base + '.srt')
        srt = to_srt(cues, args.dur)
        with open(out, 'w', encoding='utf-8') as f:
            f.write(srt)
        print(f'{os.path.basename(md)}: {len(cues)} 条 -> {srt.count(chr(10) + chr(10)) + 1} 块 -> {out}')


if __name__ == '__main__':
    main()
