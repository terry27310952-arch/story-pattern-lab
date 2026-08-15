from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont


DISPLAY_BRAND_LABEL = "キヨサキ"
BG = (5, 7, 7)
BG_WARM = (12, 9, 7)
OFF_WHITE = (244, 241, 235)
ORANGE = (246, 159, 25)
GREEN = (113, 202, 149)
RED = (227, 105, 90)


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
    for ch in text:
        yield ch


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
    target = (23, 16, 10) if warm else (7, 13, 15)
    base = Image.new("RGB", (width, height), base_color)
    px = base.load()
    for y in range(height):
        for x in range(width):
            radial = max(0.0, 1.0 - (((x - width * 0.64) / (width * 0.72)) ** 2 + ((y - height * 0.22) / (height * 0.50)) ** 2))
            glow = radial * (0.68 if warm else 0.33)
            px[x, y] = tuple(int(base_color[i] * (1 - glow) + target[i] * glow) for i in range(3))
    return base


def _draw_top_brand(draw: ImageDraw.ImageDraw, scale: float) -> None:
    draw.text((int(70 * scale), int(58 * scale)), DISPLAY_BRAND_LABEL, font=_font(int(27 * scale), True), fill=OFF_WHITE)


def _draw_bottom_gradient(image: Image.Image, top_ratio: float = 0.50) -> None:
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    px = overlay.load()
    start = int(height * top_ratio)
    for y in range(start, height):
        t = (y - start) / max(1, height - start)
        alpha = int(min(245, (t ** 1.6) * 255))
        for x in range(width):
            px[x, y] = (0, 0, 0, alpha)
    image.alpha_composite(overlay)


def _draw_soft_grid(draw: ImageDraw.ImageDraw, width: int, height: int, scale: float) -> None:
    top = int(150 * scale)
    bottom = int(height * 0.58)
    left = int(65 * scale)
    right = width - int(65 * scale)
    for x in range(left, right, max(1, int(95 * scale))):
        draw.line((x, top, x, bottom), fill=(255, 255, 255, 14), width=max(1, int(scale)))
    for y in range(top, bottom, max(1, int(78 * scale))):
        draw.line((left, y, right, y), fill=(255, 255, 255, 14), width=max(1, int(scale)))


def _draw_metric_strip(draw, metrics: list[tuple[str, str]], width: int, y: int, scale: float) -> None:
    if not metrics:
        return
    left = int(70 * scale)
    max_w = width - int(140 * scale)
    cell_w = max_w // max(1, len(metrics))
    for i, (label, value) in enumerate(metrics):
        x = left + i * cell_w
        draw.text((x, y), label.upper(), font=_font(int(18 * scale)), fill=(175, 170, 162, 190))
        draw.text((x, y + int(28 * scale)), value, font=_font(int(27 * scale), True), fill=OFF_WHITE)


def _draw_market_visual(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    _draw_soft_grid(draw, width, height, scale)
    cx, cy = int(width * 0.68), int(height * 0.27)
    for radius, alpha in [(230, 18), (170, 24), (110, 34)]:
        r = int(radius * scale)
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=(246, 159, 25, alpha), width=max(1, int(2*scale)))
    values = [0.40, 0.47, 0.43, 0.55, 0.49, 0.59, 0.52, 0.62, 0.58, 0.67, 0.61]
    left = int(width * 0.12)
    step = int(width * 0.065)
    for i, value in enumerate(values):
        x = left + i * step
        y = int(height * (0.50 - value * 0.25))
        body_h = int((32 + (i % 3) * 14) * scale)
        color = (112, 183, 147, 125) if i % 3 != 1 else (223, 105, 90, 100)
        draw.line((x, y-body_h, x, y+body_h), fill=color, width=max(2, int(3*scale)))
        draw.rectangle((x-int(8*scale), y-int(12*scale), x+int(8*scale), y+int(16*scale)), fill=color)
    metrics = []
    for metric_id in ["btc_price", "btc_7d", "fear_greed"]:
        metric = _metric_map(card).get(metric_id)
        if metric:
            metrics.append((str(metric.get("label") or metric_id), str(metric.get("value") or "")))
    _draw_metric_strip(draw, metrics[:3], width, int(height * 0.57), scale)


def _draw_price_visual(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    _draw_soft_grid(draw, width, height, scale)
    top, bottom = int(height * 0.14), int(height * 0.57)
    left, right = int(width * 0.14), int(width * 0.88)
    support = _metric_raw(card, "btc_primary_support") or _metric_raw(card, "btc_support")
    resistance = _metric_raw(card, "btc_primary_resistance") or _metric_raw(card, "btc_resistance")
    current = _metric_raw(card, "btc_price")
    numeric = [float(v) for v in [support, resistance, current] if isinstance(v, (int, float))]
    if len(numeric) >= 2:
        low, high = min(numeric), max(numeric)
        if high == low:
            high = low + 1
        def py(value: float) -> int:
            return int(bottom - ((value - low) / (high - low)) * (bottom-top))
        if resistance is not None:
            y = py(float(resistance))
            draw.rectangle((left, y-int(22*scale), right, y+int(22*scale)), fill=(227, 105, 90, 22))
            draw.line((left, y, right, y), fill=(227, 105, 90, 165), width=max(2, int(3*scale)))
            draw.text((left, y-int(55*scale)), "RESISTANCE", font=_font(int(20*scale), True), fill=(227, 105, 90, 210))
            draw.text((right-int(190*scale), y-int(55*scale)), _metric_value(card, "btc_primary_resistance") or _metric_value(card, "btc_resistance"), font=_font(int(24*scale), True), fill=OFF_WHITE)
        if support is not None:
            y = py(float(support))
            draw.rectangle((left, y-int(22*scale), right, y+int(22*scale)), fill=(113, 202, 149, 18))
            draw.line((left, y, right, y), fill=(113, 202, 149, 170), width=max(2, int(3*scale)))
            draw.text((left, y-int(55*scale)), "SUPPORT", font=_font(int(20*scale), True), fill=(113, 202, 149, 220))
            draw.text((right-int(190*scale), y-int(55*scale)), _metric_value(card, "btc_primary_support") or _metric_value(card, "btc_support"), font=_font(int(24*scale), True), fill=OFF_WHITE)
        if current is not None:
            y = py(float(current))
            r = int(9 * scale)
            draw.ellipse((int(width*0.50)-r, y-r, int(width*0.50)+r, y+r), fill=ORANGE+(255,))
            draw.text((int(width*0.53), y-int(18*scale)), _metric_value(card, "btc_price"), font=_font(int(25*scale), True), fill=OFF_WHITE)


def _draw_derivatives_visual(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    _draw_soft_grid(draw, width, height, scale)
    left = int(width * 0.10)
    top = int(height * 0.16)
    chart_bottom = int(height * 0.49)
    bar_w = int(24 * scale)
    gap = int(23 * scale)
    heights = [0.30, 0.44, 0.37, 0.58, 0.50, 0.66, 0.61, 0.74, 0.68, 0.76, 0.64, 0.70]
    for i, h in enumerate(heights):
        x = left + i * (bar_w + gap)
        y = chart_bottom - int((chart_bottom-top) * h)
        draw.rounded_rectangle((x, y, x+bar_w, chart_bottom), radius=int(4*scale), fill=(246, 159, 25, 90 + (i % 4) * 20))
    line_points = []
    for i, h in enumerate([0.55,0.59,0.57,0.64,0.62,0.69,0.67,0.71,0.70,0.75,0.74,0.78]):
        x = left + i * (bar_w + gap) + bar_w//2
        y = chart_bottom - int((chart_bottom-top) * h)
        line_points.append((x, y))
    draw.line(line_points, fill=(255,255,255,120), width=max(2,int(3*scale)))
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
    _draw_metric_strip(draw, metrics[:3], width, int(height * 0.54), scale)


def _draw_news_visual(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    source = card.get("source") or {}
    publisher = str(source.get("publisher") or "MARKET NEWS")
    title = str(source.get("display_headline_ja") or source.get("short_title") or card.get("headline") or "")
    x0, y0 = int(width*0.10), int(height*0.15)
    w, h = int(width*0.76), int(height*0.34)
    for dx, dy, alpha in [(24, 18, 26), (12, 9, 38)]:
        draw.rounded_rectangle((x0+int(dx*scale), y0+int(dy*scale), x0+w+int(dx*scale), y0+h+int(dy*scale)), radius=int(8*scale), fill=(255,255,255,alpha))
    draw.rounded_rectangle((x0, y0, x0+w, y0+h), radius=int(8*scale), fill=(235,231,220,24), outline=(255,255,255,40), width=max(1,int(scale)))
    draw.text((x0+int(34*scale), y0+int(30*scale)), publisher.upper(), font=_font(int(20*scale), True), fill=(ORANGE[0],ORANGE[1],ORANGE[2],220))
    title_font = _font(int(38*scale), True)
    ty = y0+int(78*scale)
    for line in _wrap(draw, title, title_font, w-int(68*scale), 4):
        draw.text((x0+int(34*scale), ty), line, font=title_font, fill=OFF_WHITE)
        ty += int(52*scale)
    draw.line((x0+int(34*scale), y0+h-int(48*scale), x0+w-int(34*scale), y0+h-int(48*scale)), fill=(255,255,255,40), width=max(1,int(scale)))


def _draw_scenario_visual(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    top = int(height*0.15)
    bottom = int(height*0.55)
    centers = [int(width*0.22), int(width*0.50), int(width*0.78)]
    labels = [("BULL", GREEN), ("BASE", ORANGE), ("BEAR", RED)]
    for i, (label, color) in enumerate(labels):
        cx = centers[i]
        draw.text((cx-int(48*scale), top-int(10*scale)), label, font=_font(int(24*scale), True), fill=color)
        if i == 0:
            pts = [(cx,bottom),(cx-int(20*scale),int(height*0.42)),(cx+int(28*scale),int(height*0.34)),(cx+int(10*scale),int(height*0.24))]
        elif i == 1:
            pts = [(cx,bottom),(cx+int(18*scale),int(height*0.44)),(cx-int(10*scale),int(height*0.36)),(cx+int(7*scale),int(height*0.28))]
        else:
            pts = [(cx,bottom),(cx+int(18*scale),int(height*0.45)),(cx-int(28*scale),int(height*0.39)),(cx-int(8*scale),int(height*0.31)),(cx-int(32*scale),int(height*0.25))]
        draw.line(pts, fill=color+(150,), width=max(3,int(5*scale)))
        for x, y in pts:
            r = int(6 * scale)
            draw.ellipse((x-r,y-r,x+r,y+r), fill=color+(220,))
    support = _metric_value(card, "btc_primary_support") or _metric_value(card, "btc_support")
    resistance = _metric_value(card, "btc_primary_resistance") or _metric_value(card, "btc_resistance")
    if support or resistance:
        draw.text((int(width*0.10), int(height*0.57)), " / ".join(v for v in [support, resistance] if v), font=_font(int(25*scale), True), fill=(235,235,230,190))


def _draw_trade_visual(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    top = int(height*0.17)
    box_h = int(110*scale)
    gap = int(28*scale)
    x0, x1 = int(width*0.10), int(width*0.90)
    plan = card.get("trade_plan") or {}
    rows = [
        ("ENTRY", (plan.get("entry") or {}).get("condition") or "条件成立まで待つ", GREEN),
        ("WAIT", (plan.get("wait") or {}).get("condition") or "レンジ内は待機", ORANGE),
        ("INVALID", (plan.get("invalid") or {}).get("condition") or "無効化条件を優先", RED),
    ]
    for i, (label, text, color) in enumerate(rows):
        y = top + i * (box_h + gap)
        draw.rounded_rectangle((x0,y,x1,y+box_h), radius=int(14*scale), fill=(255,255,255,12), outline=color+(90,), width=max(1,int(2*scale)))
        draw.text((x0+int(28*scale), y+int(21*scale)), label, font=_font(int(25*scale), True), fill=color)
        draw.text((x0+int(190*scale), y+int(20*scale)), " ".join(str(text or "").split())[:42], font=_font(int(25*scale), True), fill=OFF_WHITE)


def _draw_outro_visual(image: Image.Image, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    cx, cy = int(width*0.50), int(height*0.30)
    glow = Image.new("RGBA", image.size, (0,0,0,0))
    gd = ImageDraw.Draw(glow, "RGBA")
    for r, a in [(230,18),(170,28),(120,40)]:
        rr = int(r * scale)
        gd.ellipse((cx-rr,cy-rr,cx+rr,cy+rr), fill=(246,159,25,a))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=max(2,int(24*scale)))))
    draw = ImageDraw.Draw(image, "RGBA")
    head_r = int(62 * scale)
    draw.ellipse((cx-head_r,cy-int(115*scale)-head_r,cx+head_r,cy-int(115*scale)+head_r), fill=(3,3,3,255), outline=(246,159,25,150), width=max(2,int(3*scale)))
    draw.rounded_rectangle((cx-int(150*scale),cy-int(60*scale),cx+int(150*scale),cy+int(260*scale)), radius=int(80*scale), fill=(4,4,4,255), outline=(246,159,25,110), width=max(2,int(3*scale)))
    draw.line((cx-int(90*scale),cy+int(90*scale),cx,cy+int(140*scale),cx+int(90*scale),cy+int(90*scale)), fill=(246,159,25,95), width=max(2,int(3*scale)))


def _draw_editorial_copy(image: Image.Image, card: dict, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    left = int(72 * scale)
    right = width - int(72 * scale)
    headline_font = _font(int(62 * scale), True)
    body_font = _font(int(30 * scale), True)
    footer_font = _font(int(18 * scale))
    headline_lines = _wrap(draw, str(card.get("headline") or ""), headline_font, right-left, 3)
    body_lines = _wrap(draw, _body(card), body_font, right-left, 3)
    footer_y = height - int(52 * scale)
    body_line_h = int(44 * scale)
    body_y = footer_y - int(58 * scale) - len(body_lines) * body_line_h
    headline_line_h = int(76 * scale)
    headline_y = body_y - int(42 * scale) - len(headline_lines) * headline_line_h
    for line in headline_lines:
        draw.text((left, headline_y), line, font=headline_font, fill=ORANGE)
        headline_y += headline_line_h
    for line in body_lines:
        draw.text((left, body_y), line, font=body_font, fill=OFF_WHITE)
        body_y += body_line_h
    draw.text((left, footer_y), _footer(card), font=footer_font, fill=(145,140,133,210))


def render_card_image(card: dict, width: int = 1080, height: int = 1350) -> Image.Image:
    scale = width / 1080.0
    card_type = str(card.get("card_type") or "market_conclusion")
    image = _gradient_background(width, height, warm=card_type in {"news_context", "brand_outro"}).convert("RGBA")
    _draw_top_brand(ImageDraw.Draw(image, "RGBA"), scale)
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
        _draw_market_visual(image, card, scale)
    _draw_bottom_gradient(image, top_ratio=0.47 if card_type != "brand_outro" else 0.50)
    _draw_editorial_copy(image, card, scale)
    return image.convert("RGB")


def render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
    image = render_card_image(card, width=width, height=height)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
