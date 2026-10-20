# -*- coding: utf-8 -*-
"""Draw a clean 512x512 tile with a channel's name - only used when no real logo exists anywhere."""
import hashlib
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, 'fonts', 'Poppins-Bold.ttf')
S, R = 512, 72
PALETTE = [((36, 99, 175), (12, 36, 80)), ((112, 48, 160), (40, 18, 70)), ((20, 130, 110), (8, 55, 50)),
           ((190, 70, 40), (80, 25, 15)), ((60, 70, 90), (22, 26, 36)), ((150, 40, 80), (60, 12, 32))]


def render(title, path):
    from PIL import Image, ImageDraw, ImageFont
    c1, c2 = PALETTE[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(PALETTE)]
    img = Image.new('RGBA', (S, S))
    d = ImageDraw.Draw(img)
    for y in range(S):
        t = y / (S - 1)
        d.line([(0, y), (S, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)) + (255,))
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], R, fill=255)
    img.putalpha(mask)
    words = title.split()
    best = None
    for size in range(150, 30, -6):                      # biggest size whose wrapped lines fit
        f = ImageFont.truetype(FONT, size)
        lines, cur = [], ''
        for w in words:
            trial = (cur + ' ' + w).strip()
            if d.textlength(trial, font=f) <= S * 0.84:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) * size * 1.12 <= S * 0.8 and all(d.textlength(l, font=f) <= S * 0.84 for l in lines):
            best = (f, lines)
            break
    f, lines = best or (ImageFont.truetype(FONT, 32), [title[:28]])
    lh = f.size * 1.12
    y = (S - lh * len(lines)) / 2 - f.size * 0.08
    for l in lines:
        w = d.textlength(l, font=f)
        d.text(((S - w) / 2, y), l, font=f, fill=(255, 255, 255, 255))
        y += lh
    tmp = path + '.tmp'
    img.save(tmp, format='PNG', optimize=True)
    os.replace(tmp, path)
    return path


def tile_path(cache_dir, title):
    title = re.sub(r'\s+', ' ', title).strip()[:80] or 'TV'
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, hashlib.sha1(title.encode()).hexdigest()[:20] + '.png')
    if not os.path.exists(path):
        render(title, path)
    return path
