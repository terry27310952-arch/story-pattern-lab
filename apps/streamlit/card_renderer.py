from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DISPLAY_BRAND_LABEL = "キヨサキ"
BG = (5, 7, 7)
BG_WARM = (14, 10, 7)
OFF_WHITE = (244, 241, 235)
MUTED = (168, 163, 155)
ORANGE = (246, 159, 25)
GREEN = (113, 202, 149)
RED = (227, 105, 90)
BLUE = (93, 153, 190)

_FONT_CANDIDATES = {
    "regular": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}


def _font(size: int, bold: bool = False):
    key = "bold" if bold else "regular"
    for candidate in _FONT_CANDIDATES[key]:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size, index=0)
            except Exception:
                continue
    return ImageFont.load_default()


def _metric_map(card: dict) -> dict[str, dict]:
    return {str(item.get("id")): item for item in (card.get("metrics") or []) if item.get("id")}


def _metric_value(card: dict, metric_id: str, default: str = "") -> str:
    return str((_metric_map(card).get(metric_id) or {}).get("value") or default)


def _metric_raw(card: dict, metric_id: str):
    return (_metric_map(card).get(metric_id) or {}).get("raw_value")


def _footer(card: dict) -> str:
    footer = str(card.get("footer") or "").strip()
    if footer:
        return footer
    source = card.get("source") or {}
    publisher = str(source.get("publisher") or "").strip()
    title = str(source.get("short_title") or "").strip()
    parts = [DISPLAY_BRAND_LABEL]
    if publisher:
        parts.append(publisher)
    if title:
        parts.append(title)
    return " · ".join(parts)


def _body(card: dict) -> str:
    for value in [card.get("key_message"), (card.get("insight") or {}).get("text"), card.get("subheadline")]:
        text = " ".join(str(value or "").split())
        if text:
            return text
    return ""


def _char_breaks(text: str) -> Iterable[str]:
    yield from text


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int = 3) -> list[str]:
    text = " ".join(str(text or "").split())
    if not text:
        return []
    if draw.textlength(text, font=font) <= max_width:
        return [text]
    lines: list[str] = []
    current = ""
    for ch in _char_breaks(text):
        candidate = current + ch
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current.rstrip())
            current = ch.lstrip()
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if len(lines) < max_lines and current:
        lines.append(current.rstrip())
    lines = lines[:max_lines]
    if len(lines) == max_lines and len("".join(lines)) < len(text):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _gradient_background(width: int, height: int, warm: bool = False) -> Image.Image:
    base_color = BG_WARM if warm else BG
    target = (30, 19, 10) if warm else (8, 18, 21)
    base = Image.new("RGB", (width, height), base_color)
    px = base.load()
    for y in range(height):
        for x in range(width):
            radial = max(0.0, 1.0 - (((x - width * 0.66) / (width * 0.76)) ** 2 + ((y - height * 0.22) / (height * 0.55)) ** 2))
            glow = radial * (0.76 if warm else 0.42)
            px[x, y] = tuple(int(base_color[i] * (1 - glow) + target[i] * glow) for i in range(3))
    return base


def _load_visual_asset(card: dict, width: int, height: int) -> Image.Image | None:
    direction = card.get("visual_direction") or {}
    candidates = [
        card.get("visual_asset_path"),
        card.get("background_image_path"),
        direction.get("visual_asset_path"),
        direction.get("background_image_path"),
        direction.get("generated_scene_path"),
    ]
    for value in candidates:
        if not value:
            continue
        path = Path(str(value)).expanduser()
        if not path.exists() or not path.is_file():
            continue
        try:
            image = Image.open(path).convert("RGB")
            ratio_target = width / height
            ratio_src = image.width / image.height
            if ratio_src > ratio_target:
                new_w = int(image.height * ratio_target)
                left = max(0, (image.width - new_w) // 2)
                image = image.crop((left, 0, left + new_w, image.height))
            else:
                new_h = int(image.width / ratio_target)
                top = max(0, (image.height - new_h) // 2)
                image = image.crop((0, top, image.width, top + new_h))
            return image.resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")
        except Exception:
            continue
    return None


def _draw_top_brand(draw: ImageDraw.ImageDraw, scale: float) -> None:
    draw.text((int(70 * scale), int(58 * scale)), DISPLAY_BRAND_LABEL, font=_font(int(27 * scale), True), fill=OFF_WHITE)


def _draw_bottom_gradient(image: Image.Image, top_ratio: float = 0.50) -> None:
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    px = overlay.load()
    start = int(height * top_ratio)
    for y in range(start, height):
        t = (y - start) / max(1, height - start)
        alpha = int(min(248, (t ** 1.35) * 255))
        for x in range(width):
            px[x, y] = (0, 0, 0, alpha)
    image.alpha_composite(overlay)


def _film_grain(image: Image.Image, strength: int = 9) -> None:
    width, height = image.size
    grain = Image.effect_noise((max(1, width // 2), max(1, height // 2)), 32).resize((width, height))
    grain = grain.convert("L").point(lambda p: max(0, min(255, 128 + (p - 128) * strength / 32)))
    layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    layer.putalpha(grain.point(lambda p: int(abs(p - 128) * 0.24)))
    image.alpha_composite(layer)


def _draw_blurred_lights(image: Image.Image, scale: float, warm: bool = True, density: int = 34) -> None:
    width, height = image.size
    lights = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(lights, "RGBA")
    palette = [(246, 159, 25), (255, 211, 132), (111, 154, 171)] if warm else [(90, 150, 174), (190, 214, 220), (246, 159, 25)]
    for i in range(density):
        x = int(width * (0.05 + ((i * 37) % 91) / 100.0 * 0.90))
        y = int(height * (0.08 + ((i * 53) % 57) / 100.0 * 0.42))
        r = int((4 + (i % 5) * 3) * scale)
        color = palette[i % len(palette)]
        alpha = 35 + (i % 4) * 16
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color + (alpha,))
    image.alpha_composite(lights.filter(ImageFilter.GaussianBlur(radius=max(2, int(8 * scale)))))


def _draw_soft_grid(draw: ImageDraw.ImageDraw, width: int, height: int, scale: float, alpha: int = 14) -> None:
    top = int(150 * scale)
    bottom = int(height * 0.58)
    left = int(65 * scale)
    right = width - int(65 * scale)
    for x in range(left, right, max(1, int(95 * scale))):
        draw.line((x, top, x, bottom), fill=(255, 255, 255, alpha), width=max(1, int(scale)))
    for y in range(top, bottom, max(1, int(78 * scale))):
        draw.line((left, y, right, y), fill=(255, 255, 255, alpha), width=max(1, int(scale)))


def _draw_metric_strip(draw, metrics: list[tuple[str, str]], width: int, y: int, scale: float, compact: bool = False) -> None:
    if not metrics:
        return
    left = int(70 * scale)
    max_w = width - int(140 * scale)
    cell_w = max_w // max(1, len(metrics))
    label_size = int((15 if compact else 18) * scale)
    value_size = int((23 if compact else 27) * scale)
    for i, (label, value) in enumerate(metrics):
        x = left + i * cell_w
        draw.text((x, y), label.upper(), font=_font(label_size), fill=(175, 170, 162, 190))
        draw.text((x, y + int(26 * scale)), value, font=_font(value_size, True), fill=OFF_WHITE)


def _draw_city_scene(image: Image.Image, card: dict, scale: float) -> None:
    width, height = image.size
    _draw_blurred_lights(image, scale, warm=True, density=46)
    draw = ImageDraw.Draw(image, "RGBA")
    horizon = int(height * 0.47)
    blocks = [
        (0.02, 0.34, 0.16, 0.58), (0.14, 0.27, 0.31, 0.58), (0.29, 0.38, 0.43, 0.58),
        (0.41, 0.23, 0.59, 0.58), (0.57, 0.31, 0.72, 0.58), (0.70, 0.19, 0.89, 0.58), (0.87, 0.37, 0.99, 0.58),
    ]
    for idx, (x0, y0, x1, y1) in enumerate(blocks):
        draw.rectangle((int(width * x0), int(height * y0), int(width * x1), int(height * y1)), fill=(4 + idx, 7 + idx, 8 + idx, 245))
        bx0, by0, bx1, by1 = int(width * x0), int(height * y0), int(width * x1), int(height * y1)
        for yy in range(by0 + int(18 * scale), by1 - int(12 * scale), max(1, int(34 * scale))):
            for xx in range(bx0 + int(13 * scale), bx1 - int(8 * scale), max(1, int(28 * scale))):
                if ((xx + yy + idx) // max(1, int(10 * scale))) % 4 == 0:
                    draw.rectangle((xx, yy, xx + int(8 * scale), yy + int(4 * scale)), fill=(246, 159, 25, 30))
    draw.polygon([(0, horizon), (width, horizon - int(18 * scale)), (width, int(height * 0.64)), (0, int(height * 0.66))], fill=(2, 4, 5, 210))
    draw.line((0, horizon, width, horizon - int(18 * scale)), fill=(255, 255, 255, 22), width=max(1, int(2 * scale)))
    points = []
    for i, v in enumerate([0.48, 0.51, 0.49, 0.55, 0.53, 0.58, 0.54, 0.60, 0.57, 0.61, 0.59]):
        x = int(width * (0.12 + i * 0.071))
        y = int(height * (0.53 - v * 0.10))
        points.append((x, y))
    draw.line(points, fill=(246, 159, 25, 65), width=max(2, int(3 * scale)))
    metrics = []
    for metric_id in ["btc_price", "btc_7d", "fear_greed"]:
        metric = _metric_map(card).get(metric_id)
        if metric:
            metrics.append((str(metric.get("label") or metric_id), str(metric.get("value") or "")))
    _draw_metric_strip(draw, metrics[:3], width, int(height * 0.57), scale, compact=True)


def _draw_price_visual(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    x0, y0, x1, y1 = int(width * 0.08), int(height * 0.12), int(width * 0.92), int(height * 0.58)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=int(12 * scale), fill=(6, 11, 12, 218), outline=(255, 255, 255, 22), width=max(1, int(scale)))
    _draw_soft_grid(draw, width, height, scale, alpha=13)
    support = _metric_raw(card, "btc_primary_support") or _metric_raw(card, "btc_support")
    resistance = _metric_raw(card, "btc_primary_resistance") or _metric_raw(card, "btc_resistance")
    current = _metric_raw(card, "btc_price")
    numeric = [float(v) for v in [support, resistance, current] if isinstance(v, (int, float))]
    top, bottom = int(height * 0.18), int(height * 0.52)
    left, right = int(width * 0.14), int(width * 0.86)
    if len(numeric) >= 2:
        low, high = min(numeric), max(numeric)
        if high == low:
            high = low + 1

        def py(value: float) -> int:
            return int(bottom - ((value - low) / (high - low)) * (bottom - top))

        if resistance is not None:
            y = py(float(resistance))
            draw.rectangle((left, y - int(16 * scale), right, y + int(16 * scale)), fill=(227, 105, 90, 23))
            draw.line((left, y, right, y), fill=(227, 105, 90, 170), width=max(2, int(3 * scale)))
            draw.text((left, y - int(47 * scale)), "RESISTANCE", font=_font(int(18 * scale), True), fill=RED)
            draw.text((right - int(190 * scale), y - int(47 * scale)), _metric_value(card, "btc_primary_resistance") or _metric_value(card, "btc_resistance"), font=_font(int(23 * scale), True), fill=OFF_WHITE)
        if support is not None:
            y = py(float(support))
            draw.rectangle((left, y - int(16 * scale), right, y + int(16 * scale)), fill=(113, 202, 149, 19))
            draw.line((left, y, right, y), fill=(113, 202, 149, 172), width=max(2, int(3 * scale)))
            draw.text((left, y - int(47 * scale)), "SUPPORT", font=_font(int(18 * scale), True), fill=GREEN)
            draw.text((right - int(190 * scale), y - int(47 * scale)), _metric_value(card, "btc_primary_support") or _metric_value(card, "btc_support"), font=_font(int(23 * scale), True), fill=OFF_WHITE)
        if current is not None:
            y = py(float(current))
            cx = int(width * 0.50)
            r = int(8 * scale)
            draw.ellipse((cx - r, y - r, cx + r, y + r), fill=ORANGE + (255,))
            draw.text((cx + int(28 * scale), y - int(18 * scale)), _metric_value(card, "btc_price"), font=_font(int(24 * scale), True), fill=OFF_WHITE)
    draw.line((x0, int(height * 0.60), x1, int(height * 0.60)), fill=(255, 255, 255, 15), width=max(1, int(scale)))


def _draw_derivatives_visual(image: Image.Image, card: dict, scale: float) -> None:
    width, height = image.size
    _draw_blurred_lights(image, scale, warm=False, density=30)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.polygon([(int(width * 0.05), int(height * 0.52)), (int(width * 0.95), int(height * 0.50)), (width, int(height * 0.66)), (0, int(height * 0.67))], fill=(3, 5, 6, 235))
    panel_specs = [(0.08, 0.13, 0.34, 0.39), (0.37, 0.11, 0.63, 0.37), (0.66, 0.14, 0.91, 0.40)]
    for idx, (a, b, c, d) in enumerate(panel_specs):
        x0, y0, x1, y1 = int(width * a), int(height * b), int(width * c), int(height * d)
        draw.rounded_rectangle((x0, y0, x1, y1), radius=int(7 * scale), fill=(5, 12, 15, 224), outline=(255, 255, 255, 24), width=max(1, int(scale)))
        for j in range(5):
            yy = y0 + int((28 + j * 28) * scale)
            color = ORANGE if (j + idx) % 3 == 0 else (120, 160, 173)
            draw.line((x0 + int(22 * scale), yy, x1 - int((34 + j * 8) * scale), yy), fill=color + (38,), width=max(1, int(2 * scale)))
        if idx == 1:
            pts = []
            for j, v in enumerate([0.55, 0.48, 0.61, 0.57, 0.66, 0.63, 0.72, 0.69]):
                xx = x0 + int(20 * scale) + j * int(31 * scale)
                yy = y1 - int(28 * scale) - int((y1 - y0) * 0.45 * v)
                pts.append((xx, yy))
            draw.line(pts, fill=(246, 159, 25, 110), width=max(2, int(3 * scale)))
    cx = int(width * 0.78)
    base_y = int(height * 0.55)
    draw.ellipse((cx - int(38 * scale), base_y - int(155 * scale), cx + int(38 * scale), base_y - int(79 * scale)), fill=(1, 2, 2, 245))
    draw.polygon([(cx - int(90 * scale), base_y - int(85 * scale)), (cx + int(90 * scale), base_y - int(85 * scale)), (cx + int(125 * scale), base_y + int(60 * scale)), (cx - int(120 * scale), base_y + int(60 * scale))], fill=(2, 3, 3, 245))
    draw.arc((cx - int(43 * scale), base_y - int(160 * scale), cx + int(43 * scale), base_y - int(74 * scale)), start=250, end=70, fill=ORANGE + (135,), width=max(2, int(3 * scale)))
    metrics = []
    for metric_id in ["funding", "oi_change_24h", "rsi14"]:
        metric = _metric_map(card).get(metric_id)
        if metric:
            metrics.append((str(metric.get("label") or metric_id), str(metric.get("value") or "")))
    if not metrics:
        for metric_id in ["funding", "open_interest", "rsi14"]:
            metric = _metric_map(card).get(metric_id)
            if metric:
                metrics.append((str(metric.get("label") or metric_id), str(metric.get("value") or "")))
    _draw_metric_strip(draw, metrics[:3], width, int(height * 0.57), scale, compact=True)


def _news_display_title(card: dict) -> str:
    source = card.get("source") or {}
    title = str(source.get("display_headline_ja") or "").strip()
    if title:
        return title
    raw = str(source.get("short_title") or card.get("headline") or "").strip()
    low = raw.lower()
    if "supply" in low and ("bitcoin" in low or "btc" in low):
        return "BTC供給の希少性が再び焦点に"
    if "etf" in low and ("inflow" in low or "flow" in low):
        return "ETF資金フローに再び注目"
    if "chainlink" in low:
        return "Chainlinkへの期待が再浮上"
    if "regulation" in low or "sec" in low:
        return "規制材料が市場の焦点に"
    return raw[:52]


def _draw_news_visual(image: Image.Image, card: dict, scale: float) -> None:
    width, height = image.size
    _draw_blurred_lights(image, scale, warm=True, density=22)
    draw = ImageDraw.Draw(image, "RGBA")
    source = card.get("source") or {}
    publisher = str(source.get("publisher") or "MARKET NEWS")
    title = _news_display_title(card)
    for i in range(7):
        x = int(width * (0.05 + i * 0.145))
        draw.rectangle((x, int(height * 0.10), x + int(width * 0.09), int(height * 0.43)), fill=(16 + i * 2, 14 + i, 11, 110), outline=(255, 255, 255, 12), width=max(1, int(scale)))
    draw.polygon([(0, int(height * 0.44)), (width, int(height * 0.42)), (width, int(height * 0.64)), (0, int(height * 0.67))], fill=(5, 4, 3, 235))
    x0, y0 = int(width * 0.13), int(height * 0.16)
    w, h = int(width * 0.62), int(height * 0.31)
    for dx, dy, alpha in [(20, 16, 24), (10, 8, 38)]:
        draw.rounded_rectangle((x0 + int(dx * scale), y0 + int(dy * scale), x0 + w + int(dx * scale), y0 + h + int(dy * scale)), radius=int(8 * scale), fill=(235, 231, 220, alpha))
    paper = (224, 218, 204, 235)
    draw.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=int(8 * scale), fill=paper, outline=(255, 255, 255, 55), width=max(1, int(scale)))
    draw.rectangle((x0 + int(28 * scale), y0 + int(68 * scale), x0 + int(190 * scale), y0 + h - int(34 * scale)), fill=(64, 58, 49, 220))
    for k in range(4):
        yy = y0 + int((85 + k * 37) * scale)
        draw.line((x0 + int(215 * scale), yy, x0 + w - int((36 + k * 18) * scale), yy), fill=(48, 43, 38, 90), width=max(2, int(3 * scale)))
    draw.text((x0 + int(28 * scale), y0 + int(25 * scale)), publisher.upper(), font=_font(int(19 * scale), True), fill=(183, 112, 26, 255))
    title_font = _font(int(32 * scale), True)
    ty = y0 + int(70 * scale)
    for line in _wrap(draw, title, title_font, w - int(250 * scale), 3):
        draw.text((x0 + int(215 * scale), ty), line, font=title_font, fill=(40, 36, 31, 255))
        ty += int(46 * scale)
    draw.line((x0, y0 + h, x0 + w, y0 + h), fill=ORANGE + (55,), width=max(2, int(3 * scale)))


def _draw_scenario_visual(image: Image.Image, card: dict, scale: float) -> None:
    width, height = image.size
    _draw_blurred_lights(image, scale, warm=False, density=16)
    draw = ImageDraw.Draw(image, "RGBA")
    vanish = (int(width * 0.50), int(height * 0.19))
    baseline = int(height * 0.57)
    lanes = [("BULL", GREEN, int(width * 0.19)), ("BASE", ORANGE, int(width * 0.50)), ("BEAR", RED, int(width * 0.81))]
    for idx, (label, color, cx) in enumerate(lanes):
        draw.text((cx - int(52 * scale), int(height * 0.13)), label, font=_font(int(22 * scale), True), fill=color)
        left = cx - int(86 * scale)
        right = cx + int(86 * scale)
        target_x = vanish[0] + (idx - 1) * int(62 * scale)
        draw.polygon([(left, baseline), (right, baseline), (target_x, vanish[1])], fill=color + (14,))
        draw.line((left, baseline, target_x, vanish[1]), fill=color + (92,), width=max(2, int(3 * scale)))
        draw.line((right, baseline, target_x, vanish[1]), fill=color + (50,), width=max(1, int(2 * scale)))
        for j, t in enumerate([0.18, 0.43, 0.70]):
            y = int(baseline - (baseline - vanish[1]) * t)
            x = int(cx + (target_x - cx) * t)
            r = int((8 - j) * scale)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color + (180,))
    support = _metric_value(card, "btc_primary_support") or _metric_value(card, "btc_support")
    resistance = _metric_value(card, "btc_primary_resistance") or _metric_value(card, "btc_resistance")
    ma50 = _metric_value(card, "ma50")
    ma20 = _metric_value(card, "ma20")
    hierarchy = " → ".join(v for v in [ma50, ma20, resistance] if v)
    if hierarchy:
        draw.text((int(width * 0.10), int(height * 0.59)), f"UP {hierarchy}", font=_font(int(21 * scale), True), fill=(235, 235, 230, 180))
    elif support or resistance:
        draw.text((int(width * 0.10), int(height * 0.59)), " / ".join(v for v in [support, resistance] if v), font=_font(int(23 * scale), True), fill=(235, 235, 230, 180))


def _normalize_trade_text(text: str) -> str:
    raw = " ".join(str(text or "").split())
    low = raw.lower()
    if "above close" in low:
        price = raw.split()[0] if raw.split() else ""
        return f"{price}を終値で回復".strip()
    if "inside range" in low:
        return "レンジ内は待機"
    if "close break" in low:
        price = raw.split()[0] if raw.split() else ""
        return f"{price}を終値で割る".strip()
    return raw


def _draw_trade_visual(image: Image.Image, card: dict, scale: float) -> None:
    width, height = image.size
    _draw_blurred_lights(image, scale, warm=True, density=16)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.polygon([(0, int(height * 0.49)), (width, int(height * 0.46)), (width, int(height * 0.65)), (0, int(height * 0.68))], fill=(3, 3, 3, 238))
    x0, x1 = int(width * 0.10), int(width * 0.90)
    top = int(height * 0.15)
    row_h = int(82 * scale)
    gap = int(24 * scale)
    plan = card.get("trade_plan") or {}
    rows = [
        ("ENTRY", _normalize_trade_text((plan.get("entry") or {}).get("condition") or "条件成立まで待つ"), GREEN),
        ("WAIT", _normalize_trade_text((plan.get("wait") or {}).get("condition") or "レンジ内は待機"), ORANGE),
        ("INVALID", _normalize_trade_text((plan.get("invalid") or {}).get("condition") or "無効化条件を優先"), RED),
    ]
    for i, (label, text, color) in enumerate(rows):
        y = top + i * (row_h + gap)
        draw.rounded_rectangle((x0, y, x1, y + row_h), radius=int(10 * scale), fill=(6, 9, 9, 180), outline=color + (55,), width=max(1, int(scale)))
        draw.rectangle((x0, y, x0 + int(7 * scale), y + row_h), fill=color + (185,))
        draw.text((x0 + int(28 * scale), y + int(21 * scale)), label, font=_font(int(23 * scale), True), fill=color)
        draw.text((x0 + int(180 * scale), y + int(18 * scale)), text[:48], font=_font(int(24 * scale), True), fill=OFF_WHITE)
    hx, hy = int(width * 0.79), int(height * 0.54)
    draw.ellipse((hx - int(45 * scale), hy - int(15 * scale), hx + int(70 * scale), hy + int(45 * scale)), fill=(1, 1, 1, 235))
    draw.line((hx - int(60 * scale), hy + int(15 * scale), hx - int(160 * scale), hy + int(88 * scale)), fill=(1, 1, 1, 235), width=max(8, int(30 * scale)))
    draw.line((hx + int(30 * scale), hy, hx + int(110 * scale), hy - int(70 * scale)), fill=(246, 159, 25, 75), width=max(2, int(3 * scale)))


def _draw_outro_visual(image: Image.Image, scale: float) -> None:
    width, height = image.size
    _draw_blurred_lights(image, scale, warm=True, density=14)
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    cx, cy = int(width * 0.52), int(height * 0.29)
    for r, a in [(250, 20), (185, 32), (130, 46)]:
        rr = int(r * scale)
        gd.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=ORANGE + (a,))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=max(3, int(30 * scale)))))
    draw = ImageDraw.Draw(image, "RGBA")
    shoulder_y = int(height * 0.34)
    torso_bottom = int(height * 0.62)
    body = [(int(width * 0.27), torso_bottom), (int(width * 0.32), shoulder_y), (int(width * 0.43), int(height * 0.29)), (int(width * 0.61), int(height * 0.29)), (int(width * 0.73), shoulder_y), (int(width * 0.78), torso_bottom)]
    draw.polygon(body, fill=(2, 2, 2, 255))
    head_box = (cx - int(70 * scale), int(height * 0.16), cx + int(70 * scale), int(height * 0.31))
    draw.ellipse(head_box, fill=(1, 1, 1, 255))
    draw.rectangle((cx - int(37 * scale), int(height * 0.28), cx + int(37 * scale), int(height * 0.36)), fill=(2, 2, 2, 255))
    draw.line((int(width * 0.38), int(height * 0.33), cx, int(height * 0.48), int(width * 0.46), int(height * 0.61)), fill=(70, 67, 63, 155), width=max(2, int(4 * scale)))
    draw.line((int(width * 0.66), int(height * 0.33), cx, int(height * 0.48), int(width * 0.58), int(height * 0.61)), fill=(70, 67, 63, 155), width=max(2, int(4 * scale)))
    draw.arc(head_box, start=235, end=55, fill=ORANGE + (195,), width=max(2, int(4 * scale)))
    draw.line((int(width * 0.32), shoulder_y, int(width * 0.27), torso_bottom), fill=ORANGE + (80,), width=max(2, int(3 * scale)))
    draw.line((int(width * 0.73), shoulder_y, int(width * 0.78), torso_bottom), fill=ORANGE + (80,), width=max(2, int(3 * scale)))
    gy = int(height * 0.55)
    draw.ellipse((cx - int(95 * scale), gy - int(24 * scale), cx - int(6 * scale), gy + int(30 * scale)), fill=(3, 3, 3, 255), outline=(65, 62, 58, 135), width=max(1, int(2 * scale)))
    draw.ellipse((cx + int(6 * scale), gy - int(24 * scale), cx + int(95 * scale), gy + int(30 * scale)), fill=(3, 3, 3, 255), outline=(65, 62, 58, 135), width=max(1, int(2 * scale)))


def _draw_editorial_copy(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    left = int(72 * scale)
    right = width - int(72 * scale)
    card_type = str(card.get("card_type") or "")
    headline_size = 57 if card_type != "brand_outro" else 54
    headline_font = _font(int(headline_size * scale), True)
    body_font = _font(int(29 * scale), True)
    footer_font = _font(int(17 * scale))
    headline_lines = _wrap(draw, str(card.get("headline") or ""), headline_font, right - left, 3)
    body_lines = _wrap(draw, _body(card), body_font, right - left, 3)
    footer_y = height - int(48 * scale)
    body_line_h = int(42 * scale)
    body_y = footer_y - int(56 * scale) - len(body_lines) * body_line_h
    headline_line_h = int(70 * scale)
    headline_y = body_y - int(38 * scale) - len(headline_lines) * headline_line_h
    if card_type == "brand_outro":
        headline_y = max(int(height * 0.72), headline_y)
    for line in headline_lines:
        draw.text((left, headline_y), line, font=headline_font, fill=ORANGE)
        headline_y += headline_line_h
    for line in body_lines:
        draw.text((left, body_y), line, font=body_font, fill=OFF_WHITE)
        body_y += body_line_h
    draw.text((left, footer_y), _footer(card), font=footer_font, fill=(145, 140, 133, 210))


def render_card_image(card: dict, width: int = 1080, height: int = 1350) -> Image.Image:
    scale = width / 1080.0
    card_type = str(card.get("card_type") or "market_conclusion")
    external = _load_visual_asset(card, width, height)
    if external is not None and card_type not in {"key_levels", "trade_plan"}:
        image = external.convert("RGBA")
    else:
        image = _gradient_background(width, height, warm=card_type in {"news_context", "brand_outro", "trade_plan"}).convert("RGBA")
        if card_type == "key_levels":
            _draw_price_visual(image, card, scale)
        elif card_type == "derivatives":
            _draw_derivatives_visual(image, card, scale)
        elif card_type == "news_context":
            _draw_news_visual(image, card, scale)
        elif card_type == "scenarios":
            _draw_scenario_visual(image, card, scale)
        elif card_type == "trade_plan":
            _draw_trade_visual(image, card, scale)
        elif card_type == "brand_outro":
            _draw_outro_visual(image, scale)
        else:
            _draw_city_scene(image, card, scale)
    _draw_top_brand(ImageDraw.Draw(image, "RGBA"), scale)
    _draw_bottom_gradient(image, top_ratio=0.50 if card_type != "brand_outro" else 0.56)
    _film_grain(image, strength=8)
    _draw_editorial_copy(image, card, scale)
    return image.convert("RGB")


def render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
    image = render_card_image(card, width=width, height=height)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
