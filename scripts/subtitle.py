#!/usr/bin/env python3
"""subtitle —— B站字幕全流程 CLI（fetch / proofread / to-srt）

链路：B站视频 AI 字幕 → 原文 md 收档 → 无基准校对（出校对版双份）→ SRT 外挂字幕

用法:
  subtitle fetch <bvid> --dir <视频目录> [--pages all|1,3] [--author 名]
      # 拉 AI 字幕落 <视频目录>/字幕/<part>_字幕原文.md（part=B站分P标题，与mp4同名）
  subtitle proofread <原文md|目录> --fixes <fixes.json> [--force] [-v]
      # 应用替换清单（global 跨期 + files 定向），出 <part>_字幕校对版.md，校验行数/时间轴
  subtitle to-srt <md> [--video <视频目录>] [--dur 秒]
      # md → srt；--video 时输出与 mp4 同名到视频目录（外挂自动挂载），时长自动 ffprobe

fixes.json 结构:
  {"global": {"乌蠢": "污纯"}, "files": {"文件名子串": {"无视角": "无视掉"}}}

实战: 2026-09-09 悟饭污纯《合金弹头5无脑通关教学》5P —— 289/292/282/696/437 条，
fetch→proofread(20处)→to-srt 全链一次成型。
"""
import argparse
import json
import os
import re
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
# 字幕本体拉取脚本：作者环境默认指向 bilibili-api-ops 里的实现（不在本仓）。
# 换环境用环境变量覆盖：BILI_SUBTITLE_SCRIPT=/path/to/bili_subtitle.py
BILI_SUB = os.environ.get('BILI_SUBTITLE_SCRIPT') or os.path.join(
    SKILLS_ROOT, 'bilibili-api-ops', 'scripts', 'bili_subtitle.py')
if not os.path.exists(BILI_SUB):
    BILI_SUB = os.path.expanduser('~/skills/bilibili-api-ops/scripts/bili_subtitle.py')

CUE_RE = re.compile(r'^(\[\d{2}:\d{2}:\d{2}\]\s*)(.*)$')
HEAD_RE = re.compile(r'^#|^>|^\s*$')
BY_RE = re.compile(r'[（(]by\.([^）)】\s]+)')
TMP = os.environ.get('TMPDIR', '/tmp')


def log(msg):
    print(msg)


# ---------- fetch ----------

def view_pages(bvid):
    """view 接口拿分P（匿名）。返回 (title, owner, [{page, part, cid, duration}])"""
    out = subprocess.run(
        ['curl', '-s', '--max-time', '20',
         f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'],
        capture_output=True, text=True)
    d = json.loads(out.stdout)
    if d.get('code') != 0:
        raise RuntimeError(f'view 接口失败: {d.get("message")}')
    data = d['data']
    return (data['title'], data['owner']['name'], data['pages'])


def cmd_fetch(args):
    title, owner, pages = view_pages(args.bvid)
    log(f'标题: {title} | UP: {owner} | 分P: {len(pages)}')
    author = args.author or ''
    if not author:
        m = BY_RE.search(title)
        if m:
            author = m.group(1).strip()
            log(f'从标题提取作者: {author}')
    author = author or owner

    if args.pages == 'all':
        want = list(range(1, len(pages) + 1))
    else:
        want = [int(x) for x in args.pages.split(',') if x.strip()]
    sub_dir = os.path.join(args.dir, '字幕')
    os.makedirs(sub_dir, exist_ok=True)
    if not os.path.exists(BILI_SUB):
        raise RuntimeError(f'找不到 bili_subtitle.py: {BILI_SUB}')

    done = []
    env = dict(os.environ)
    # Playwright 浏览器目录接管（默认 <TMPDIR>/pw，可用软链指向本机可用版本；
    # 环境默认路径常缺脚本期望的版本号——有可用版本时无条件覆盖；换目录用 PW_DIR）
    pw_dir = os.environ.get('PW_DIR', os.path.join(TMP, 'pw'))
    if os.path.isdir(pw_dir) and any(
            d.startswith('chromium_headless_shell-') for d in os.listdir(pw_dir)):
        env['PLAYWRIGHT_BROWSERS_PATH'] = pw_dir
    for pno in want:
        if not (1 <= pno <= len(pages)):
            log(f'跳过 P{pno}（超出 1..{len(pages)}）')
            continue
        p = pages[pno - 1]
        part = re.sub(r'[/\\]', '_', p['part'])
        tmp = os.path.join(TMP, f'sub_fetch_{args.bvid}_{pno}.txt')
        log(f'--- P{pno}: {p["part"]} ({p["duration"]}s) ---')
        r = subprocess.run(
            [sys.executable, BILI_SUB, args.bvid, '--page', str(pno), '--out', tmp],
            capture_output=True, text=True, timeout=600, env=env)
        for line in (r.stderr or '').strip().splitlines():
            log(f'  {line}')
        if r.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError(f'P{pno} 拉取失败: {(r.stderr or r.stdout or "")[-800:]}')
        with open(tmp, encoding='utf-8') as f:
            body = f.read().rstrip('\n')
        os.unlink(tmp)
        n = len([l for l in body.splitlines() if CUE_RE.match(l)])
        md = os.path.join(sub_dir, f'{part}_字幕原文.md')
        head = (f'# {part} 字幕（原文）\n\n'
                f'> 作者：{author}\n'
                f'> 来源：B站 AI 字幕 {args.bvid} 分P P{pno}（{title}，视频 {p["duration"]}s）\n'
                f'> 形态：`[时:分:秒] 台词` 逐行\n\n')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(head + body + '\n')
        log(f'✅ {os.path.basename(md)}（{n} 条）')
        done.append(md)
    if not done:
        raise RuntimeError('没有拉到任何分P')
    log(f'\n完成 {len(done)} 个，字幕目录: {sub_dir}')


# ---------- proofread ----------

def apply_fixes(lines, table, basename, verbose):
    """逐行替换正文文本（不动时间轴）。返回 (改后行, 命中明细列表)"""
    out = []
    hits = []  # (行号, 原文, 改后, 词)
    for idx, line in enumerate(lines):
        m = CUE_RE.match(line)
        if not m:
            out.append(line)
            continue
        prefix, text = m.group(1), m.group(2)
        changed = False
        for wrong, right in table:
            if wrong in text:
                new_text = text.replace(wrong, right)
                if new_text != text:
                    hits.append((idx + 1, text, new_text, wrong))
                    text = new_text
                    changed = True
        if changed:
            # 保留行尾换行——丢了 writelines 会把相邻行粘成一行（2026-09-09 实战教训）
            nl = '\n' if line.endswith('\n') else ''
            out.append(prefix + text + nl)
        else:
            out.append(line)
    return out, hits


def cmd_proofread(args):
    if args.fixes == '-':
        fixes = json.load(sys.stdin)
    else:
        with open(args.fixes, encoding='utf-8') as f:
            fixes = json.load(f)
    g_table = list((fixes.get('global') or {}).items())
    f_table = {k: list(v.items()) for k, v in (fixes.get('files') or {}).items()}

    if os.path.isdir(args.target):
        files = sorted(f for f in os.listdir(args.target)
                       if f.endswith('_字幕原文.md'))
        base_dir = args.target
    else:
        files = [os.path.basename(args.target)]
        base_dir = os.path.dirname(args.target) or '.'
    if not files:
        raise RuntimeError(f'{args.target} 下没有 *_字幕原文.md')

    for fn in files:
        src = os.path.join(base_dir, fn)
        if '_字幕原文' in fn:
            out_fn = fn.replace('_字幕原文', '_字幕校对版')
        else:
            out_fn = fn[:-3] + '_字幕校对版.md'
        dst = os.path.join(base_dir, out_fn)
        if os.path.exists(dst) and not args.force:
            raise RuntimeError(f'输出已存在: {out_fn}（--force 覆盖）')

        with open(src, encoding='utf-8') as f:
            lines = f.read().splitlines(keepends=True)

        # 组装本文件替换表：global + 命中文件子串的定向表
        table = list(g_table)
        for key, items in f_table.items():
            if key in fn:
                table.extend(items)
        table_done = [t for t in table]  # (错, 对)
        new_lines, hits = apply_fixes(lines, table, fn, args.verbose)

        # 内容级校验（模拟写盘后重新读——list 级校验抓不到行尾 \n 丢失的粘连）
        old_content = ''.join(lines)
        new_content = ''.join(new_lines)
        def ts_of(content):
            return [m.group(1) for l in content.splitlines() if (m := CUE_RE.match(l))]
        old_ts = ts_of(old_content)
        new_ts = ts_of(new_content)
        if len(new_content.splitlines()) != len(old_content.splitlines()):
            raise RuntimeError(f'{fn}: 行数变了 '
                               f'{len(old_content.splitlines())} -> {len(new_content.splitlines())}，终止')
        if old_ts != new_ts:
            raise RuntimeError(f'{fn}: 时间轴被改动，终止')

        # 残留检查：表里所有错词不应再出现在正文
        residual = [w for w, _ in table_done if w in new_content]
        if residual:
            raise RuntimeError(f'{fn}: 替换后仍有残留错词: {residual}')

        # 校对版标题同步：正文修了，标题别还挂「原文」
        if out_fn.endswith('_字幕校对版.md') and new_lines and '字幕（原文）' in new_lines[0]:
            new_lines[0] = new_lines[0].replace('字幕（原文）', '字幕（校对版）')

        with open(dst, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        # 统计（按词计命中行）
        word_count = {}
        for _, _, _, wrong in hits:
            word_count[wrong] = word_count.get(wrong, 0) + 1
        total = sum(word_count.values())
        det = ' '.join(f'{w}×{c}' for w, c in word_count.items() if c) or '无'
        log(f'== {fn}: 修正 {total} 处（{det}） | 行数 {len(old_ts)}={len(new_ts)} ✅ | {out_fn}')
        if args.verbose:
            for lineno, before, after, wrong in hits:
                log(f'  L{lineno}: 「{before}」 -> 「{after}」')


# ---------- to-srt ----------

def probe_dur(mp4):
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', mp4],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except Exception:
        return None


def strip_suffix(base):
    """md 文件名去 原文/校对版 后缀，露出与 mp4 同名的 base"""
    for suf in ('_字幕校对版', '_字幕原文'):
        if base.endswith(suf):
            return base[:-len(suf)]
    return base


def cmd_tosrt(args):
    md = args.md
    base = os.path.splitext(os.path.basename(md))[0]
    stripped = strip_suffix(base)
    dur = args.dur
    out_dir = args.video if args.video else os.path.dirname(md) or '.'

    if dur is None and args.video:
        mp4 = os.path.join(args.video, stripped + '.mp4')
        if os.path.exists(mp4):
            dur = probe_dur(mp4)
            log(f'ffprobe {os.path.basename(mp4)}: {dur:.2f}s' if dur else 'ffprobe 失败，末块用默认时长')

    # import md_cues_to_srt（同目录的转换工具）
    sys.path.insert(0, SKILL_DIR)
    import md_cues_to_srt as mcs
    cues = mcs.parse_md(md)
    if not cues:
        raise RuntimeError(f'{md} 没有字幕行')
    srt = mcs.to_srt(cues, dur)
    out_path = os.path.join(out_dir, stripped + '.srt')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(srt)
    n_block = srt.count('\n\n') + 1 if srt.strip() else 0
    log(f'✅ {os.path.basename(md)}: {len(cues)} 条 -> {n_block} 块 -> {out_path}')


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(prog='subtitle', description='B站字幕全流程（拉取/校对/SRT）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_fetch = sub.add_parser('fetch', help='拉 B站 AI 字幕落原文 md')
    p_fetch.add_argument('bvid')
    p_fetch.add_argument('--dir', required=True, help='视频目录（内部建 字幕/ 子目录）')
    p_fetch.add_argument('--pages', default='all', help='分P选择：all 或 1,3（逗号）')
    p_fetch.add_argument('--author', default=None, help='作者名（默认从标题 by.XXX 提取）')
    p_fetch.set_defaults(func=cmd_fetch)

    p_pp = sub.add_parser('proofread', help='按替换清单出校对版（无基准校对）')
    p_pp.add_argument('target', help='原文 md 或目录（目录自动处理所有 *_字幕原文.md）')
    p_pp.add_argument('--fixes', required=True, help='fixes.json（- 从 stdin）')
    p_pp.add_argument('--force', action='store_true', help='覆盖已存在的校对版')
    p_pp.add_argument('-v', '--verbose', action='store_true', help='打逐处明细')
    p_pp.set_defaults(func=cmd_proofread)

    p_srt = sub.add_parser('to-srt', help='md → SRT 外挂字幕')
    p_srt.add_argument('md')
    p_srt.add_argument('--video', default=None, help='视频目录（输出与 mp4 同名，自动 ffprobe 时长）')
    p_srt.add_argument('--dur', type=float, default=None, help='视频时长(秒)，覆盖自动探测')
    p_srt.set_defaults(func=cmd_tosrt)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
