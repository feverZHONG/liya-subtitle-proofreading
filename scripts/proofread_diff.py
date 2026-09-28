#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字幕校对第一步：解析 SRT + 完整性检查 + 规范化全文 diff。

用法: python3 proofread_diff.py <subtitle.srt> <原文.txt>
输出: SRT 块数/序号缺失/时间轴重叠 + 规范化匹配度 + replace/delete 差异块。
"""
import re, sys, difflib

def parse_srt(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        raw = f.read()
    blocks = re.split(r'\r?\n\r?\n', raw.strip())
    parsed = []
    bad = 0
    for b in blocks:
        lines = b.split('\r\n') if '\r' in b else b.split('\n')
        if len(lines) >= 2 and re.match(r'^\d+$', lines[0].strip()) and '-->' in lines[1]:
            num = int(lines[0].strip())
            time_line = lines[1].strip()
            text = ''.join(l.strip() for l in lines[2:] if l.strip())
            parsed.append({'num': num, 'time': time_line, 'text': text})
        else:
            bad += 1
    return parsed, bad

def to_ms(t):
    h, m, s = t.split(':')
    return int(h) * 3600000 + int(m) * 60000 + int(float(s.replace(',', '.')) * 1000)

def norm(s):
    """归一：去引号/标点/空白 + 阿拉伯数字→中文数字（AI 转写「1号」→「一号」）。"""
    s = s.replace('“', '').replace('”', '').replace('‘', '').replace('’', '')
    s = s.replace('"', '').replace("'", '')
    s = re.sub(r'[\s，。！？、；：,.!?;:（）()《》<>「」『』…·—\-—–]', '', s)
    cn = {'0': '零', '1': '一', '2': '二', '3': '三', '4': '四',
          '5': '五', '6': '六', '7': '七', '8': '八', '9': '九'}
    return re.sub(r'\d', lambda m: cn[m.group()], s)

def main():
    if len(sys.argv) != 3:
        print('用法: proofread_diff.py <subtitle.srt> <原文.txt>')
        sys.exit(1)
    srt_path, txt_path = sys.argv[1], sys.argv[2]

    parsed, bad = parse_srt(srt_path)
    nums = [p['num'] for p in parsed]
    print(f'SRT 块数: {len(parsed)}  解析失败块: {bad}')
    if nums:
        missing = [i for i in range(1, max(nums) + 1) if i not in nums]
        print(f'序号范围: {min(nums)}-{max(nums)}  缺失: {len(missing)} {missing[:20]}')

    # 时间轴重叠
    overlap = 0
    for i in range(1, len(parsed)):
        if to_ms(parsed[i-1]['time'].split(' --> ')[1]) > to_ms(parsed[i]['time'].split(' --> ')[0]):
            overlap += 1
            if overlap <= 3:
                print(f'  时间轴重叠: #{parsed[i-1]["num"]} vs #{parsed[i]["num"]}')
    print(f'时间轴重叠: {overlap}')

    # 规范化全文 diff
    srt_full = norm(''.join(p['text'] for p in parsed))
    with open(txt_path, 'r', encoding='utf-8-sig') as f:
        txt_norm = norm(f.read())
    print(f'原文规范字符: {len(txt_norm)}  字幕规范字符: {len(srt_full)}')

    sm = difflib.SequenceMatcher(None, txt_norm, srt_full, autojunk=False)
    ops = sm.get_opcodes()
    eq = sum(a2 - a1 for tag, a1, a2, b1, b2 in ops if tag == 'equal')
    pct = eq / len(txt_norm) * 100 if txt_norm else 0
    print(f'匹配度: {eq}/{len(txt_norm)} = {pct:.2f}%  (>98% = 对齐良好，剩余差异即错字候选)')

    print('\n=== replace/delete 差异块（原文侧，含上下文）===')
    for tag, a1, a2, b1, b2 in ops:
        if tag in ('replace', 'delete') and a2 - a1 >= 2:
            print(f'[{tag}] 原文 …{txt_norm[max(0, a1-12):a2+12]}…')
            if tag == 'replace':
                print(f'      字幕 …{srt_full[max(0, b1-12):b2+12]}…')
            print()

if __name__ == '__main__':
    main()
