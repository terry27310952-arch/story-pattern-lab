from __future__ import annotations

import hashlib
import math
import random
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageOps

import card_renderer
import visual_variation_runtime


STORY_RENDERER_VERSION = "story-renderer-v7.0"


def _seed(card: dict) -> int:
    raw = "|".join(
        str(value or "")
        for value in [card.get("story_id"), card.get("story_role"), card.get("story_archetype"), card.get("slide"), card.get("headline")]
    )
    return int(hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:12], 16)


def _canvas(width: int, height: int, warm: bool = False) -> Image.Image:
    return card_renderer._gradient_background(width, height, warm=warm).convert("RGBA")


def _blurred_lights(image: Image.Image, seed: int, density: int = 18, warm: bool = True) -> None:
    rng = random.Random(seed)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    w, h = image.size
    palette = [card_renderer.ORANGE, (212, 183, 132), (108, 128, 145)] if warm else [(116, 138, 156), (188, 194, 190), card_renderer.ORANGE]
    for _ in range(density):
        r = rng.randint(max(8, w // 80), max(20, w // 28))
        x = rng.randint(-r, w + r)
        y = rng.randint(0, int(h * 0.62))
        color = rng.choice(palette)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color + (rng.randint(14, 44),))
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius=max(6, w // 38))))


def _draw_archive(image: Image.Image, card: dict, role: str) -> None:
    w, h = image.size
    rng = random.Random(_seed(card))
    _blurred_lights(image, _seed(card), density=10, warm=True)
    draw = ImageDraw.Draw(image, "RGBA")
    top = int(h * 0.08)
    bottom = int(h * 0.55)
    paper = (213, 204, 184, 52)
    ink = (232, 226, 211, 78)

    if role in {"hook", "then", "what_happened"}:
        for idx in range(3):
            x0 = int(w * (0.08 + idx * 0.26)) + rng.randint(-8, 8)
            y0 = top + rng.randint(0, int(h * 0.06))
            x1 = x0 + int(w * 0.29)
            y1 = bottom - idx * int(h * 0.015)
            draw.rounded_rectangle((x0, y0, x1, y1), radius=max(6, w // 150), fill=paper, outline=(255, 255, 255, 32), width=max(1, w // 700))
            yy = y0 + int(h * 0.05)
            for line in range(7):
                line_w = int((x1 - x0) * (0.55 + (line % 3) * 0.12))
                draw.rectangle((x0 + 20, yy, x0 + 20 + line_w, yy + max(2, w // 360)), fill=ink)
                yy += max(18, h // 42)
        y = int(h * 0.44)
        draw.line((int(w * 0.11), y, int(w * 0.88), y), fill=card_renderer.ORANGE + (95,), width=max(2, w // 300))
        for idx in range(4):
            x = int(w * (0.16 + idx * 0.22))
            r = max(5, w // 120)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=card_renderer.ORANGE + ((165 if idx in {0, 3} else 90),))
    elif role == "now":
        draw.rectangle((int(w * 0.08), int(h * 0.08), int(w * 0.92), int(h * 0.54)), fill=(4, 6, 7, 195), outline=(255, 255, 255, 28), width=max(1, w // 700))
        baseline = int(h * 0.46)
        points = []
        for idx in range(24):
            x = int(w * 0.12 + idx * (w * 0.74 / 23))
            y = baseline - int((0.12 + 0.25 * math.sin(idx / 3.2) + idx / 90) * h)
            points.append((x, y))
        draw.line(points, fill=card_renderer.ORANGE + (190,), width=max(3, w // 220))
        for x, y in points[::5]:
            r = max(4, w // 150)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(235, 230, 214, 190))
    elif role == "similarity":
        mid = w // 2
        draw.rectangle((0, 0, mid, int(h * 0.58)), fill=(110, 90, 65, 22))
        draw.rectangle((mid, 0, w, int(h * 0.58)), fill=(30, 48, 62, 35))
        draw.line((mid, int(h * 0.08), mid, int(h * 0.53)), fill=card_renderer.ORANGE + (90,), width=max(2, w // 350))
        for side in [0, 1]:
            x0 = int(w * (0.10 if side == 0 else 0.58))
            y0 = int(h * 0.18)
            pts = []
            for idx in range(8):
                x = x0 + int(idx * w * 0.035)
                y = y0 + int((0.17 - math.sin(idx / 1.7) * 0.05 + idx * 0.008) * h)
                pts.append((x, y))
            draw.line(pts, fill=(220, 216, 205, 130), width=max(2, w // 380))
    else:
        draw.line((int(w * 0.10), int(h * 0.20), int(w * 0.90), int(h * 0.20)), fill=(255, 255, 255, 35), width=2)
        draw.line((int(w * 0.10), int(h * 0.40), int(w * 0.90), int(h * 0.40)), fill=card_renderer.ORANGE + (75,), width=max(2, w // 400))
        draw.polygon([(int(w * 0.42), int(h * 0.15)), (int(w * 0.58), int(h * 0.28)), (int(w * 0.42), int(h * 0.43))], fill=card_renderer.ORANGE + (35,))


def _draw_money_flow(image: Image.Image, card: dict, role: str) -> None:
    w, h = image.size
    rng = random.Random(_seed(card))
    _blurred_lights(image, _seed(card), density=14, warm=False)
    draw = ImageDraw.Draw(image, "RGBA")
    top, bottom = int(h * 0.10), int(h * 0.52)
    if role == "flow_size":
        for idx, ht in enumerate([0.22, 0.34, 0.48, 0.62, 0.82]):
            x0 = int(w * (0.13 + idx * 0.15))
            y1 = bottom
            y0 = y1 - int((bottom - top) * ht)
            draw.rounded_rectangle((x0, y0, x0 + int(w * 0.08), y1), radius=max(4, w // 190), fill=card_renderer.ORANGE + (35 + idx * 15,), outline=card_renderer.ORANGE + (75,), width=2)
        return
    nodes = []
    count = 6 if role not in {"price_gap", "watch"} else 4
    for idx in range(count):
        x = int(w * (0.12 + idx * (0.76 / max(1, count - 1))))
        y = int(top + (bottom - top) * (0.25 + rng.random() * 0.48))
        nodes.append((x, y))
    for idx in range(len(nodes) - 1):
        x1, y1 = nodes[idx]
        x2, y2 = nodes[idx + 1]
        draw.line((x1, y1, x2, y2), fill=card_renderer.ORANGE + (80 + idx * 15,), width=max(2, w // 300))
        dx, dy = x2 - x1, y2 - y1
        length = max(1.0, math.hypot(dx, dy))
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        tip = (x2, y2)
        base_x, base_y = x2 - ux * 22, y2 - uy * 22
        draw.polygon([tip, (int(base_x + px * 9), int(base_y + py * 9)), (int(base_x - px * 9), int(base_y - py * 9))], fill=card_renderer.ORANGE + (150,))
    for idx, (x, y) in enumerate(nodes):
        r = max(7, w // 110) if idx in {0, len(nodes) - 1} else max(4, w // 155)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(230, 225, 214, 155) if idx == 0 else card_renderer.ORANGE + (150,))
    if role == "price_gap":
        y = int(h * 0.43)
        draw.line((int(w * 0.12), y, int(w * 0.88), y), fill=(230, 225, 214, 55), width=2)
        draw.line((int(w * 0.12), y - int(h * 0.14), int(w * 0.88), y + int(h * 0.03)), fill=(227, 105, 90, 150), width=max(3, w // 280))


def _draw_policy(image: Image.Image, card: dict, role: str) -> None:
    w, h = image.size
    _blurred_lights(image, _seed(card), density=10, warm=True)
    draw = ImageDraw.Draw(image, "RGBA")
    x0, y0, x1, y1 = int(w * 0.15), int(h * 0.08), int(w * 0.85), int(h * 0.54)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=max(8, w // 120), fill=(224, 217, 199, 32), outline=(255, 255, 255, 50), width=2)
    yy = y0 + int(h * 0.07)
    for idx, ratio in enumerate([0.74, 0.86, 0.62, 0.80, 0.48, 0.70]):
        draw.rounded_rectangle((x0 + 34, yy, x0 + 34 + int((x1 - x0 - 68) * ratio), yy + max(3, w // 340)), radius=2, fill=(245, 240, 224, 60))
        yy += max(21, h // 35)
    if role in {"new_rule", "timeline", "watch"}:
        cx, cy = int(w * 0.72), int(h * 0.20)
        r = max(26, w // 24)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=card_renderer.ORANGE + (150,), width=max(2, w // 320))
        draw.line((cx - r // 2, cy, cx + r // 2, cy), fill=card_renderer.ORANGE + (125,), width=3)


def _draw_power(image: Image.Image, card: dict, role: str) -> None:
    w, h = image.size
    _blurred_lights(image, _seed(card), density=12, warm=False)
    draw = ImageDraw.Draw(image, "RGBA")
    mid = w // 2
    top, bottom = int(h * 0.11), int(h * 0.53)
    left_h = 0.62 if role in {"old_order", "hook"} else 0.42
    right_h = 0.42 if role in {"old_order", "hook"} else 0.78
    draw.rounded_rectangle((int(w * 0.13), bottom - int((bottom - top) * left_h), int(w * 0.42), bottom), radius=18, fill=(220, 220, 216, 24), outline=(230, 230, 225, 45), width=2)
    draw.rounded_rectangle((int(w * 0.58), bottom - int((bottom - top) * right_h), int(w * 0.87), bottom), radius=18, fill=card_renderer.ORANGE + (28,), outline=card_renderer.ORANGE + (80,), width=2)
    y = int(h * 0.32)
    draw.line((mid - 80, y, mid + 80, y), fill=card_renderer.ORANGE + (150,), width=max(3, w // 250))
    draw.polygon([(mid + 80, y), (mid + 50, y - 16), (mid + 50, y + 16)], fill=card_renderer.ORANGE + (180,))


def _draw_crisis(image: Image.Image, card: dict, role: str) -> None:
    w, h = image.size
    _blurred_lights(image, _seed(card), density=9, warm=False)
    draw = ImageDraw.Draw(image, "RGBA")
    rng = random.Random(_seed(card))
    center = (int(w * 0.50), int(h * 0.29))
    nodes = []
    for idx in range(8):
        angle = idx / 8 * math.pi * 2
        radius = int(w * (0.16 + 0.04 * (idx % 2)))
        nodes.append((int(center[0] + math.cos(angle) * radius), int(center[1] + math.sin(angle) * radius * 0.72)))
    for node in nodes:
        draw.line((center[0], center[1], node[0], node[1]), fill=(227, 105, 90, 65), width=2)
        r = max(5, w // 140)
        draw.ellipse((node[0] - r, node[1] - r, node[0] + r, node[1] + r), fill=(227, 105, 90, 135))
    rr = max(18, w // 32)
    draw.ellipse((center[0] - rr, center[1] - rr, center[0] + rr, center[1] + rr), fill=(227, 105, 90, 50), outline=(227, 105, 90, 150), width=3)
    if role == "contagion":
        for _ in range(4):
            x = rng.randint(int(w * 0.12), int(w * 0.88))
            y = rng.randint(int(h * 0.12), int(h * 0.47))
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=card_renderer.ORANGE + (120,))


def _draw_generic(image: Image.Image, card: dict, role: str) -> None:
    w, h = image.size
    _blurred_lights(image, _seed(card), density=16, warm=role in {"hook", "watch"})
    draw = ImageDraw.Draw(image, "RGBA")
    rng = random.Random(_seed(card))
    base = int(h * 0.50)
    for idx in range(16):
        x0 = int(w * 0.06 + idx * w * 0.058)
        height = rng.randint(int(h * 0.08), int(h * 0.28))
        draw.rectangle((x0, base - height, x0 + int(w * 0.038), base), fill=(90, 104, 112, 28 + (idx % 5) * 6))
    points = []
    for idx in range(15):
        x = int(w * 0.08 + idx * w * 0.06)
        y = int(h * (0.35 + 0.07 * math.sin(idx * 0.8 + (_seed(card) % 13))))
        points.append((x, y))
    draw.line(points, fill=card_renderer.ORANGE + (120,), width=max(2, w // 350))


def _story_base(card: dict, width: int, height: int) -> Image.Image:
    external = card_renderer._load_visual_asset(card, width, height)
    if external is not None and card.get("card_type") != "brand_outro":
        return external.convert("RGBA")
    if card.get("card_type") == "brand_outro":
        return visual_variation_runtime._visual_base(card_renderer, card, width, height)
    archetype = str(card.get("story_archetype") or "")
    role = str(card.get("story_role") or "hook")
    image = _canvas(width, height, warm=archetype in {"historical_parallel", "policy_change", "hidden_giant"})
    if archetype == "historical_parallel":
        _draw_archive(image, card, role)
    elif archetype == "money_flow":
        _draw_money_flow(image, card, role)
    elif archetype == "policy_change":
        _draw_policy(image, card, role)
    elif archetype == "power_shift":
        _draw_power(image, card, role)
    elif archetype == "crisis_or_risk":
        _draw_crisis(image, card, role)
    else:
        _draw_generic(image, card, role)
    return image


def render_story_card_image(card: dict, width: int = 1080, height: int = 1350) -> Image.Image:
    variant = str((card.get("visual_direction") or {}).get("format_variant") or "full_bleed_bottom")
    base = _story_base(card, width, height)
    image = visual_variation_runtime._compose(card_renderer, card, base, variant, width, height)
    card_renderer._film_grain(image, strength=7)
    return image.convert("RGB")


def render_story_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
    output = BytesIO()
    render_story_card_image(card, width=width, height=height).save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_card_image(card: dict, width: int = 1080, height: int = 1350) -> Image.Image:
    if (card.get("qa") or {}).get("mode") == "story" or card.get("card_type") == "story_editorial":
        return render_story_card_image(card, width=width, height=height)
    return card_renderer.render_card_image(card, width=width, height=height)


def render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
    if (card.get("qa") or {}).get("mode") == "story" or card.get("card_type") == "story_editorial":
        return render_story_card_png(card, width=width, height=height)
    return card_renderer.render_card_png(card, width=width, height=height)
