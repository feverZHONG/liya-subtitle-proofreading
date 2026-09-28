#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字幕重建 v10 定版：以原稿 txt 行为基础分块，块长 8-26 字

用法:
    python3 rebuild_srt.py <srt> <txt> [out] [--max-len 22]

产出:
    out 默认 <srt 去扩展名>-校对版.srt（原文件不动）

原理（2026-08-13 实战 v10 定版，取代 v9）:
    v9 贪心合并到平均 23.8 字被否决（过长+切出半句难看）。
    v10 改为以原文行为基础分块：
    1. 字幕文本 ↔ 原文规范化全局对齐（SequenceMatcher + 双坐标系映射）
    2. 每块文本 = 原文原始片段（带标点），规范化匹配度 100%
    3. 以原文行为语义单元重建分块：
       - 章节标题行（^[1-9]号/^第[一二三]层/^副型[一二三]）强制独立成块
       - 短行合并（<8 字并入相邻，合并后 <= max_len+4）
       - 长行拆分（>max_len 按标点拆；无内标点 <=30 保留完整句）
       - ≤4 字引导词块并入前块（避免一闪而过）
    4. 时间轴 = u0/u1 在覆盖它的原字幕块内插值（避免相邻块重叠）
    实战结果: 1590 → 1324 块, 平均 9.5 → 13.7 字, 匹配度 100%。
"""
import re, sys, difflib

def norm(s):
    s = s.replace('“', '').replace('”', '').replace('‘', '').replace('’', '')
    s = s.replace('"', '').replace("'", '')
    s = re.sub(r'[\s，。！？、；：,.!?;:（）()《》<>「」『』…·—\-—–]', '', s)
    cn = {'0':'零','1':'一','2':'二','3':'三','4':'四','5':'五','6':'六','7':'七','8':'八','9':'九'}
    s = re.sub(r'\d', lambda m: cn[m.group()], s)
    return s

def parse_srt(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        raw = f.read()
    blocks = re.split(r'\r?\n\r?\n', raw.strip())
    parsed = []
    for b in blocks:
        ls = b.split('\r\n') if '\r' in b else b.split('\n')
        if len(ls) >= 2 and re.match(r'^\d+$', ls[0].strip()) and '-->' in ls[1]:
            t = ls[1].strip().split(' --> ')
            parsed.append({
                'num': int(ls[0].strip()),
                'start': t[0],
                'end': t[1],
                'text': ''.join(l.strip() for l in ls[2:] if l.strip())
            })
    return parsed

HEADING_RE = re.compile(r'^[1-9]号[:：]|^第[一二三]层[:：]|^副型[一二三][:：]')
def is_heading(text):
    return bool(HEADING_RE.search(text))

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    srt_path, txt_path = sys.argv[1], sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else re.sub(r'\.srt$', '', srt_path) + '-校对版.srt'
    max_len = 22
    if '--max-len' in sys.argv:
        max_len = int(sys.argv[sys.argv.index('--max-len') + 1])
    MAXLEN = max_len

    parsed = parse_srt(srt_path)
    print(f'原 SRT 块数: {len(parsed)}')

    with open(txt_path, 'r', encoding='utf-8-sig') as f:
        txt_raw = f.read()

    # ---- 2. 原文行 → 规范化区间 ----
    raw_lines = [l.strip() for l in txt_raw.replace('\r\n', '\n').split('\n') if l.strip()]
    line_units = []  # (text, u0, u1)
    pos = 0
    for line in raw_lines:
        ln = norm(line)
        if ln:
            line_units.append((line, pos, pos + len(ln)))
            pos += len(ln)
    print(f'原文行: {len(line_units)}, 规范拼接: {pos}')

    # ---- 3. 长行拆分（> MAXLEN 按标点拆）+ 短段合并 ----
    units = []  # (text, u0, u1)
    for line, u0, u1 in line_units:
        if len(line) <= MAXLEN:
            units.append((line, u0, u1))
            continue
        # 无内标点（逗号/顿号/分号/冒号，不含结尾）且 <= 30 字：保留完整句，不拆
        inner = re.findall(r'[，、；：]', line[:-1] if len(line) > 1 else '')
        if not inner and len(line) <= 30:
            units.append((line, u0, u1))
            continue
        parts = re.findall(r'[^。！？；，、]+[。！？；，、]?', line)
        cur = ''
        cur_u0 = u0
        for p in parts:
            # ⚠️ 纯标点/引号段（无汉字字母数字）直接并入前段——findall 会把孤立右引号切成独立段
            if cur and not re.search(r'[\u4e00-\u9fff0-9a-zA-Z]', p):
                cur += p
                continue
            if len(cur) + len(p) <= MAXLEN:
                cur += p
            else:
                if cur:
                    units.append((cur, cur_u0, cur_u0 + len(norm(cur))))
                    cur_u0 += len(norm(cur))
                cur = p
                while len(cur) > MAXLEN:  # 单段超长硬切：优先在最后内标点后切
                    seg = cur[:MAXLEN]
                    last_punct = max([seg.rfind(c) for c in '，、；：'])
                    cut_at = last_punct + 1 if last_punct >= 10 else MAXLEN
                    rest = cur[cut_at:]
                    # ⚠️ 剩余太短（基本只剩标点）→ 不切，整段保留（允许超到 MAXLEN+6）
                    if len(rest) <= 4 and len(cur) <= MAXLEN + 6:
                        break
                    units.append((seg[:cut_at], cur_u0, cur_u0 + len(norm(seg[:cut_at]))))
                    cur_u0 += len(norm(seg[:cut_at]))
                    cur = rest
        if cur:
            units.append((cur, cur_u0, cur_u0 + len(norm(cur))))
    # 碎尾段（<8 字）并入前段（前段+目标 <= MAXLEN+8）；目标段是标题则不合并
    refined = []
    for text, u0, u1 in units:
        if refined and len(refined[-1][0]) < 8 and not is_heading(text) \
           and len(refined[-1][0]) + len(text) <= MAXLEN + 8:
            prev_text, prev_u0, _ = refined[-1]
            refined[-1] = (prev_text + text, prev_u0, u1)
        else:
            refined.append((text, u0, u1))
    units = refined
    print(f'拆分后单元数: {len(units)}')

    # ---- 4. 短单元合并（<8 字并入，合并后 <= MAXLEN+4）+ 章节标题独立成块 ----
    merged_units = []
    cur_text = ''
    cur_u0 = 0
    cur_u1 = 0
    def flush():
        nonlocal cur_text
        if cur_text:
            merged_units.append((cur_text, cur_u0, cur_u1))
            cur_text = ''
    for text, u0, u1 in units:
        if is_heading(text):
            flush()
            merged_units.append((text, u0, u1))
            continue
        if not cur_text:
            cur_text = text
            cur_u0, cur_u1 = u0, u1
        elif len(cur_text) < 8 and len(cur_text) + len(text) <= MAXLEN + 4:
            cur_text += text
            cur_u1 = u1
        else:
            merged_units.append((cur_text, cur_u0, cur_u1))
            cur_text = text
            cur_u0, cur_u1 = u0, u1
    flush()
    print(f'合并后单元数: {len(merged_units)}')

    # ---- 5. 原字幕块 → 原文区间（规范化对齐 + 双坐标系） ----
    norm_texts = [norm(p['text']) for p in parsed]
    sub_norm = ''.join(norm_texts)
    txt_norm = ''.join(norm(l) for l in raw_lines)

    # 原文规范化字符 → 原始位置
    txt_norm_chars, raw_positions = [], []
    for idx, ch in enumerate(txt_raw):
        cn = norm(ch)
        if cn:
            txt_norm_chars.append(cn)
            raw_positions.append(idx)

    matching = difflib.SequenceMatcher(None, sub_norm, txt_norm, autojunk=False).get_matching_blocks()

    cmap = [0] * (len(sub_norm) + 1)
    for idx, (si, tj, n) in enumerate(matching):
        for k in range(n):
            cmap[si + k] = tj + k
        if idx > 0:
            prev_si, prev_tj, prev_n = matching[idx - 1]
            gap_s = si - (prev_si + prev_n)
            gap_t = tj - (prev_tj + prev_n)
            base_s, base_t = prev_si + prev_n, prev_tj + prev_n
            if gap_s > 0:
                for k in range(gap_s):
                    cmap[base_s + k] = base_t + int((k + 1) * gap_t / gap_s)
        else:
            if si > 0:
                for k in range(si):
                    cmap[k] = int(k * tj / si) if si else 0
    # ⚠️ 末尾补赋值
    last_si, last_tj, last_n = matching[-1]
    end_s = last_si + last_n
    if end_s <= len(sub_norm):
        gap_t = len(txt_norm) - (last_tj + last_n)
        gap_s = len(sub_norm) - end_s
        base_t = last_tj + last_n
        for k in range(gap_s + 1):
            cmap[end_s + k] = base_t + (int((k + 1) * gap_t / gap_s) if gap_s else 0)

    block_ranges = []
    pos = 0
    for nt in norm_texts:
        s0, s1 = pos, pos + len(nt)
        pos = s1
        block_ranges.append((cmap[min(s0, len(cmap)-1)], cmap[min(s1, len(cmap)-1)]))

    # ---- 6. 单元 → 时间轴（u0/u1 插值，避免相邻块重叠） ----
    def to_ms(t):
        h, m, s = t.split(':')
        return int(h)*3600000 + int(m)*60000 + int(float(s.replace(',', '.'))*1000)
    def from_ms(ms):
        h = ms // 3600000; ms %= 3600000
        m = ms // 60000; ms %= 60000
        s = ms / 1000
        return f'{h:02d}:{m:02d}:{s:06.3f}'.replace('.', ',')

    def t_at(u):
        if u <= block_ranges[0][0]:
            return parsed[0]['start']
        if u >= block_ranges[-1][1]:
            return parsed[-1]['end']
        for k in range(len(block_ranges)):
            a0, a1 = block_ranges[k]
            if a0 <= u < a1:
                s = to_ms(parsed[k]['start'])
                e = to_ms(parsed[k]['end'])
                frac = (u - a0) / max(1, a1 - a0)
                return from_ms(int(s + (e - s) * frac))
        return parsed[-1]['end']

    out_blocks = []
    for text, u0, u1 in merged_units:
        t_start = t_at(u0)
        t_end = t_at(u1)
        if to_ms(t_end) > to_ms(t_start):
            out_blocks.append({'start': t_start, 'end': t_end, 'text': text})

    # 后处理：≤4 字引导词/短句块并入前块（避免一闪而过），前块不超 32 字
    final_blocks = []
    for m in out_blocks:
        if final_blocks and len(m['text']) <= 4 and len(final_blocks[-1]['text']) + len(m['text']) <= 32:
            final_blocks[-1]['text'] += m['text']
            final_blocks[-1]['end'] = m['end']
        else:
            final_blocks.append(dict(m))
    out_blocks = final_blocks

    # ---- 7. 写文件 ----
    out_lines = []
    for idx, m in enumerate(out_blocks, 1):
        out_lines.append(str(idx))
        out_lines.append(f'{m["start"]} --> {m["end"]}')
        out_lines.append(m['text'])
        out_lines.append('')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines).rstrip('\n') + '\n')

    lens = [len(m['text']) for m in out_blocks]
    print(f'输出块数: {len(out_blocks)} (原 {len(parsed)})')
    print(f'块长: 最短={min(lens)} 最长={max(lens)} 平均={sum(lens)/len(lens):.1f}')
    for th in [8, 10, 15, 20, 25]:
        cnt = sum(1 for l in lens if l < th)
        print(f'  <{th}字: {cnt} 块 ({cnt/len(lens)*100:.1f}%)')
    srt_new = norm(''.join(m['text'] for m in out_blocks))
    eq = sum(a2-a1 for tag,a1,a2,b1,b2 in
             difflib.SequenceMatcher(None, txt_norm, srt_new, autojunk=False).get_opcodes()
             if tag == 'equal')
    print(f'规范化匹配度: {eq}/{len(txt_norm)} = {eq/len(txt_norm)*100:.2f}%')
    print(f'已写出: {out_path}')

if __name__ == '__main__':
    main()
