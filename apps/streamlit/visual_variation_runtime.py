from __future__ import annotations

import copy
import hashlib
import random
import time
from collections import deque
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageOps


VISUAL_VARIATION_RUNTIME_VERSION = "visual-blueprint-v4.4"

# Brand invariants stay fixed. The rest of the composition is allowed to move.
DISPLAY_BRAND_LABEL = "キヨサキ"
RECENT_BLUEPRINTS: deque[str] = deque(maxlen=6)

# Each briefing selects one deck family. The card role still controls what information
# is shown, but the composition shell is not hard-wired 1:1 to the role anymore.
DECK_FAMILIES: dict[str, dict[str, str]] = {
    "documentary": {
        "market_conclusion": "full_bleed_bottom",
        "key_levels": "split_top",
        "derivatives": "split_left",
        "news_context": "newspaper_panel",
        "scenarios": "poster_center",
        "trade_plan": "rule_board",
        "brand_outro": "brand_locked",
    },
    "magazine": {
        "market_conclusion": "poster_center",
        "key_levels": "data_monument",
        "derivatives": "split_top",
        "news_context": "full_bleed_bottom",
        "scenarios": "split_left",
        "trade_plan": "top_caption",
        "brand_outro": "brand_locked",
    },
    "asymmetric": {
        "market_conclusion": "split_left",
        "key_levels": "poster_center",
        "derivatives": "data_monument",
        "news_context": "newspaper_panel",
        "scenarios": "top_caption",
        "trade_plan": "split_top",
        "brand_outro": "brand_locked",
    },
    "terminal_noir": {
        "market_conclusion": "top_caption",
        "key_levels": "data_monument",
        "derivatives": "full_bleed_bottom",
        "news_context": "split_left",
        "scenarios": "poster_center",
        "trade_plan": "rule_board",
        "brand_outro": "brand_locked",
    },
    "minimal_editorial": {
        "market_conclusion": "poster_center",
        "key_levels": "split_left",
        "derivatives": "top_caption",
        "news_context": "newspaper_panel",
        "scenarios": "full_bleed_bottom",
        "trade_plan": "split_top",
        "brand_outro": "brand_locked",
    },
    "data_story": {
        "market_conclusion": "data_monument",
        "key_levels": "full_bleed_bottom",
        "derivatives": "split_left",
        "news_context": "top_caption",
        "scenarios": "split_top",
        "trade_plan": "rule_board",
        "brand_outro": "brand_locked",
    },
}

# If a carousel contains an unusual repeated role, use a different shell rather than
# showing the same composition twice in a row.
ALTERNATE_VARIANTS = [
    "full_bleed_bottom",
    "split_top",
    "split_left",
    "poster_center",
    "top_caption",
    "data_monument",
]

FORMAT_PROMPTS = {
    "full_bleed_bottom": "full-bleed documentary image; uninterrupted upper visual; editorial copy sits in the lower third",
    "split_top": "image-led top panel occupying about 58 percent; strong editorial text panel below; visible hard rhythm change from adjacent cards",
    "split_left": "asymmetric vertical split; visual mass on the left and editorial typography on the right; premium magazine composition",
    "poster_center": "poster-like centered visual with a large centered headline crossing the darker middle-lower area; minimal supporting copy",
    "top_caption": "headline and short context near the top; primary visual develops below it; strong negative space and no dashboard-box look",
    "data_monument": "one dominant market number or level behaves like a visual monument; supporting data is secondary and sparse",
    "newspaper_panel": "editorial newspaper or research-note composition integrated into a dark photographic environment; tactile print feeling",
    "rule_board": "execution-rule composition with ENTRY WAIT INVALID as a deliberate editorial board, not generic white form fields",
    "brand_locked": "locked closing brand poster",
}


def _fingerprint(brief: dict, resources: list[dict] | None = None) -> str:
    source_titles = []
    for item in (resources or [])[:12]:
        source_titles.append(str(item.get("title") or item.get("short_title") or ""))
    material = "|".join(
        [
            str(brief.get("title") or ""),
            str(brief.get("one_line") or ""),
            str(brief.get("generated_at") or brief.get("as_of") or ""),
            *source_titles,
            # A fresh briefing generation should be allowed to receive a fresh visual
            # language even when the underlying market text is similar.
            str(time.time_ns()),
        ]
    )
    return hashlib.sha256(material.encode("utf-8", errors="ignore")).hexdigest()


def _select_family(seed_hex: str) -> str:
    rng = random.Random(int(seed_hex[:16], 16))
    names = list(DECK_FAMILIES)
    recent_families = {item.split(":", 1)[0] for item in RECENT_BLUEPRINTS}
    candidates = [name for name in names if name not in recent_families]
    if not candidates:
        # After every family has been used, only avoid the immediately previous one.
        previous = RECENT_BLUEPRINTS[-1].split(":", 1)[0] if RECENT_BLUEPRINTS else ""
        candidates = [name for name in names if name != previous] or names
    return rng.choice(candidates)


def _variant_for_card(card: dict, family: str, previous_variant: str | None, rng: random.Random) -> str:
    card_type = str(card.get("card_type") or "market_conclusion")
    if card_type == "brand_outro":
        return "brand_locked"
    variant = DECK_FAMILIES[family].get(card_type, "full_bleed_bottom")
    if variant == previous_variant:
        alternatives = [item for item in ALTERNATE_VARIANTS if item != previous_variant]
        variant = rng.choice(alternatives)
    return variant


def _update_image_prompts(card: dict, variant: str) -> None:
    direction = card.setdefault("visual_direction", {})
    prompts = dict(direction.get("image_prompts") or {})
    variation_clause = FORMAT_PROMPTS.get(variant, FORMAT_PROMPTS["full_bleed_bottom"])
    no_mark_clause = (
        " Do not add a K monogram, orange K symbol, arrow-like brand mark, decorative logo, badge, watermark or icon before the brand name."
        " The deterministic renderer adds only the text キヨサキ at top-left."
    )
    outro_clause = ""
    if card.get("card_type") == "brand_outro":
        outro_clause = (
            " FINAL CARD CHARACTER LOCK: centered front-facing faceless adult male, smooth completely black featureless face, broad tailored black suit,"
            " black shirt, black tie, black leather gloves clasped calmly at the lower abdomen, straight restrained posture, waist-up framing,"
            " warm orange rim light tracing the head and shoulders, sparse warm dust, near-black studio background. Keep this silhouette language consistent."
        )
    for ratio in ("4:5", "9:16"):
        base = str(prompts.get(ratio) or "").strip()
        clause = f" Composition variant for this briefing: {variation_clause}."
        prompts[ratio] = (base + clause + no_mark_clause + outro_clause).strip()
    direction["image_prompts"] = prompts


def apply_blueprint_to_package(package: dict, brief: dict, resources: list[dict] | None = None) -> dict:
    next_package = copy.deepcopy(package or {})
    seed_hex = _fingerprint(brief or {}, resources)
    family = _select_family(seed_hex)
    signature = f"{family}:{seed_hex[:10]}"
    RECENT_BLUEPRINTS.append(signature)
    rng = random.Random(int(seed_hex[16:32], 16))

    cards_by_set = next_package.get("cards") or {}
    for set_label, cards in cards_by_set.items():
        previous_variant: str | None = None
        for card in cards or []:
            variant = _variant_for_card(card, family, previous_variant, rng)
            previous_variant = variant
            direction = card.setdefault("visual_direction", {})
            direction["deck_family"] = family
            direction["format_variant"] = variant
            direction["visual_blueprint_id"] = signature
            direction["format_instruction"] = FORMAT_PROMPTS.get(variant, "")
            direction["brand_mark_policy"] = "text-only キヨサキ; no K monogram/icon"
            if card.get("card_type") == "brand_outro":
                direction["character_style_lock"] = {
                    "face": "smooth fully featureless black face; no eyes nose mouth",
                    "wardrobe": "tailored black suit, black shirt, black tie, black leather gloves",
                    "pose": "front-facing, waist-up, hands clasped calmly at lower abdomen",
                    "lighting": "warm orange rim light around head and shoulders",
                    "mood": "quiet premium anonymous financial observer",
                }
            _update_image_prompts(card, variant)

    quality = next_package.setdefault("content_quality", {})
    quality["visual_blueprint"] = {
        "id": signature,
        "family": family,
        "runtime": VISUAL_VARIATION_RUNTIME_VERSION,
        "policy": "fresh briefing-level deck family; role-aware composition; no adjacent identical shell; locked brand outro character",
    }
    return next_package


def apply_reasoning_patch(reasoning_engine) -> None:
    current = getattr(reasoning_engine, "_kiyosaki_visual_variation_version", None)
    if current == VISUAL_VARIATION_RUNTIME_VERSION:
        return
    original = reasoning_engine.generate_content_package

    def generate_content_package(brief: dict, resources: list[dict], custom_card_count: int, config: dict, output_locale: str):
        package = original(brief, resources, custom_card_count, config, output_locale)
        return apply_blueprint_to_package(package, brief, resources)

    reasoning_engine.generate_content_package = generate_content_package
    reasoning_engine._kiyosaki_visual_variation_version = VISUAL_VARIATION_RUNTIME_VERSION


def _visual_base(card_renderer, card: dict, width: int, height: int) -> Image.Image:
    scale = width / 1080.0
    card_type = str(card.get("card_type") or "market_conclusion")
    external = card_renderer._load_visual_asset(card, width, height)
    if external is not None and card_type not in {"key_levels", "trade_plan", "brand_outro"}:
        return external.convert("RGBA")

    image = card_renderer._gradient_background(
        width,
        height,
        warm=card_type in {"news_context", "brand_outro", "trade_plan"},
    ).convert("RGBA")
    if card_type == "key_levels":
        card_renderer._draw_price_visual(image, card, scale)
    elif card_type == "derivatives":
        card_renderer._draw_derivatives_visual(image, card, scale)
    elif card_type == "news_context":
        card_renderer._draw_news_visual(image, card, scale)
    elif card_type == "scenarios":
        card_renderer._draw_scenario_visual(image, card, scale)
    elif card_type == "trade_plan":
        card_renderer._draw_trade_visual(image, card, scale)
    elif card_type == "brand_outro":
        _draw_locked_outro(card_renderer, image, scale)
    else:
        card_renderer._draw_city_scene(image, card, scale)
    return image


def _draw_brand(card_renderer, draw: ImageDraw.ImageDraw, scale: float, x: int | None = None, y: int | None = None) -> None:
    # Text only. Never draw the K glyph/monogram that appeared in the mock generation.
    x = x if x is not None else int(70 * scale)
    y = y if y is not None else int(58 * scale)
    draw.text((x, y), DISPLAY_BRAND_LABEL, font=card_renderer._font(int(27 * scale), True), fill=card_renderer.OFF_WHITE)


def _headline_and_body(card_renderer, image: Image.Image, card: dict, scale: float, box: tuple[int, int, int, int], align: str = "left", headline_color=None) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    left, top, right, bottom = box
    headline_color = headline_color or card_renderer.ORANGE
    headline = str(card.get("headline") or "")
    body = card_renderer._body(card)
    headline_font = card_renderer._font(int(52 * scale), True)
    body_font = card_renderer._font(int(27 * scale), True)
    h_lines = card_renderer._wrap(draw, headline, headline_font, right - left, 3)
    b_lines = card_renderer._wrap(draw, body, body_font, right - left, 3)
    h_step = int(64 * scale)
    b_step = int(40 * scale)
    total = len(h_lines) * h_step + (int(28 * scale) if b_lines else 0) + len(b_lines) * b_step
    y = max(top, top + max(0, (bottom - top - total) // 2))
    for line in h_lines:
        text_w = int(draw.textlength(line, font=headline_font))
        x = left if align == "left" else (right - text_w if align == "right" else left + max(0, (right - left - text_w) // 2))
        draw.text((x, y), line, font=headline_font, fill=headline_color)
        y += h_step
    if b_lines:
        y += int(18 * scale)
    for line in b_lines:
        text_w = int(draw.textlength(line, font=body_font))
        x = left if align == "left" else (right - text_w if align == "right" else left + max(0, (right - left - text_w) // 2))
        draw.text((x, y), line, font=body_font, fill=card_renderer.OFF_WHITE)
        y += b_step


def _footer(card_renderer, image: Image.Image, card: dict, scale: float, x: int | None = None) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    x = x if x is not None else int(70 * scale)
    draw.text(
        (x, image.height - int(44 * scale)),
        card_renderer._footer(card),
        font=card_renderer._font(int(16 * scale)),
        fill=(145, 140, 133, 205),
    )


def _primary_metric(card: dict) -> tuple[str, str]:
    preferred = ["btc_price", "btc_primary_resistance", "btc_primary_support", "funding", "rsi14", "open_interest"]
    metric_map = {str(item.get("id")): item for item in (card.get("metrics") or []) if item.get("id")}
    for key in preferred:
        item = metric_map.get(key)
        if item and item.get("value"):
            return str(item.get("label") or key), str(item.get("value"))
    for item in (card.get("metrics") or []):
        if item.get("value"):
            return str(item.get("label") or ""), str(item.get("value"))
    return "", ""


def _draw_locked_outro(card_renderer, image: Image.Image, scale: float) -> None:
    """Locked final-card silhouette based on the approved Kiyosaki brand language."""
    width, height = image.size
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    cx, cy = int(width * 0.50), int(height * 0.255)
    for r, a in [(280, 12), (210, 22), (150, 34), (105, 46)]:
        rr = int(r * scale)
        gd.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=card_renderer.ORANGE + (a,))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=max(4, int(36 * scale)))))
    draw = ImageDraw.Draw(image, "RGBA")

    # sparse dust
    for i in range(34):
        x = int(width * (0.08 + ((i * 43) % 83) / 100.0 * 0.84))
        y = int(height * (0.07 + ((i * 61) % 59) / 100.0 * 0.53))
        if int(width * 0.32) < x < int(width * 0.68) and int(height * 0.10) < y < int(height * 0.59):
            continue
        rr = max(1, int((1 + i % 2) * scale))
        draw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=card_renderer.ORANGE + (30 + (i % 4) * 8,))

    # smooth featureless head + jaw
    head = (int(width * 0.420), int(height * 0.115), int(width * 0.580), int(height * 0.305))
    draw.ellipse(head, fill=(1, 1, 1, 255))
    draw.polygon(
        [
            (int(width * 0.438), int(height * 0.230)),
            (int(width * 0.562), int(height * 0.230)),
            (int(width * 0.548), int(height * 0.325)),
            (int(width * 0.500), int(height * 0.346)),
            (int(width * 0.452), int(height * 0.325)),
        ],
        fill=(1, 1, 1, 255),
    )
    # neck and broad black suit
    draw.rectangle((int(width * 0.462), int(height * 0.305), int(width * 0.538), int(height * 0.390)), fill=(2, 2, 2, 255))
    shoulder_y, waist_y = int(height * 0.345), int(height * 0.650)
    draw.polygon(
        [
            (int(width * 0.225), waist_y),
            (int(width * 0.255), int(height * 0.435)),
            (int(width * 0.320), shoulder_y),
            (int(width * 0.435), int(height * 0.325)),
            (int(width * 0.565), int(height * 0.325)),
            (int(width * 0.680), shoulder_y),
            (int(width * 0.745), int(height * 0.435)),
            (int(width * 0.775), waist_y),
        ],
        fill=(3, 3, 3, 255),
    )
    # lapels + black tie with only textural contrast
    lapel = (64, 61, 56, 155)
    draw.line((int(width * 0.335), shoulder_y, int(width * 0.455), int(height * 0.455), int(width * 0.475), int(height * 0.600)), fill=lapel, width=max(2, int(4 * scale)))
    draw.line((int(width * 0.665), shoulder_y, int(width * 0.545), int(height * 0.455), int(width * 0.525), int(height * 0.600)), fill=lapel, width=max(2, int(4 * scale)))
    draw.polygon(
        [
            (int(width * 0.484), int(height * 0.370)),
            (int(width * 0.516), int(height * 0.370)),
            (int(width * 0.523), int(height * 0.410)),
            (int(width * 0.507), int(height * 0.565)),
            (int(width * 0.493), int(height * 0.565)),
            (int(width * 0.477), int(height * 0.410)),
        ],
        fill=(10, 10, 10, 255),
    )
    # orange rim on silhouette edges
    draw.arc(head, start=205, end=335, fill=card_renderer.ORANGE + (205,), width=max(2, int(4 * scale)))
    draw.arc(head, start=25, end=155, fill=card_renderer.ORANGE + (205,), width=max(2, int(4 * scale)))
    draw.line((int(width * 0.320), shoulder_y, int(width * 0.255), int(height * 0.435)), fill=card_renderer.ORANGE + (92,), width=max(2, int(3 * scale)))
    draw.line((int(width * 0.680), shoulder_y, int(width * 0.745), int(height * 0.435)), fill=card_renderer.ORANGE + (92,), width=max(2, int(3 * scale)))
    # clasped black leather gloves at lower abdomen
    gy = int(height * 0.565)
    left_glove = (cx - int(108 * scale), gy - int(27 * scale), cx + int(5 * scale), gy + int(35 * scale))
    right_glove = (cx - int(5 * scale), gy - int(27 * scale), cx + int(108 * scale), gy + int(35 * scale))
    draw.ellipse(left_glove, fill=(4, 4, 4, 255), outline=(72, 68, 62, 150), width=max(1, int(2 * scale)))
    draw.ellipse(right_glove, fill=(4, 4, 4, 255), outline=(72, 68, 62, 150), width=max(1, int(2 * scale)))
    for dx in [-74, -52, -30, 30, 52, 74]:
        draw.line((cx + int(dx * scale), gy - int(8 * scale), cx + int((dx + (8 if dx < 0 else -8)) * scale), gy + int(14 * scale)), fill=(92, 86, 78, 70), width=max(1, int(scale)))


def _compose(card_renderer, card: dict, base: Image.Image, variant: str, width: int, height: int) -> Image.Image:
    scale = width / 1080.0
    card_type = str(card.get("card_type") or "")
    if card_type == "brand_outro" or variant == "brand_locked":
        image = base.copy().convert("RGBA")
        card_renderer._draw_bottom_gradient(image, top_ratio=0.58)
        _draw_brand(card_renderer, ImageDraw.Draw(image, "RGBA"), scale)
        _headline_and_body(card_renderer, image, card, scale, (int(72 * scale), int(height * 0.70), width - int(72 * scale), height - int(75 * scale)))
        _footer(card_renderer, image, card, scale)
        return image

    if variant == "split_top" or variant == "rule_board":
        image = Image.new("RGBA", (width, height), card_renderer.BG + (255,))
        visual_h = int(height * (0.58 if variant == "split_top" else 0.61))
        image.alpha_composite(ImageOps.fit(base, (width, visual_h), method=Image.Resampling.LANCZOS), (0, 0))
        panel = Image.new("RGBA", (width, height - visual_h), (4, 5, 5, 255))
        image.alpha_composite(panel, (0, visual_h))
        _draw_brand(card_renderer, ImageDraw.Draw(image, "RGBA"), scale)
        _headline_and_body(card_renderer, image, card, scale, (int(72 * scale), visual_h + int(30 * scale), width - int(72 * scale), height - int(65 * scale)))
        _footer(card_renderer, image, card, scale)
        return image

    if variant == "split_left":
        image = Image.new("RGBA", (width, height), card_renderer.BG + (255,))
        visual_w = int(width * 0.57)
        image.alpha_composite(ImageOps.fit(base, (visual_w, height), method=Image.Resampling.LANCZOS), (0, 0))
        # darken copy side while keeping a faint warm seam
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle((visual_w, 0, width, height), fill=(5, 6, 6, 255))
        draw.line((visual_w, int(height * 0.08), visual_w, int(height * 0.92)), fill=card_renderer.ORANGE + (46,), width=max(1, int(2 * scale)))
        _draw_brand(card_renderer, draw, scale, x=visual_w + int(42 * scale), y=int(58 * scale))
        _headline_and_body(card_renderer, image, card, scale, (visual_w + int(42 * scale), int(height * 0.24), width - int(42 * scale), int(height * 0.86)), align="left")
        _footer(card_renderer, image, card, scale, x=visual_w + int(42 * scale))
        return image

    if variant == "poster_center":
        image = ImageOps.fit(base, (width, height), method=Image.Resampling.LANCZOS).convert("RGBA")
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay, "RGBA")
        od.rectangle((0, int(height * 0.43), width, height), fill=(0, 0, 0, 124))
        image.alpha_composite(overlay)
        _draw_brand(card_renderer, ImageDraw.Draw(image, "RGBA"), scale)
        _headline_and_body(card_renderer, image, card, scale, (int(90 * scale), int(height * 0.50), width - int(90 * scale), int(height * 0.89)), align="center")
        _footer(card_renderer, image, card, scale)
        return image

    if variant == "top_caption":
        image = Image.new("RGBA", (width, height), card_renderer.BG + (255,))
        visual_y = int(height * 0.30)
        visual_h = int(height * 0.70)
        image.alpha_composite(ImageOps.fit(base, (width, visual_h), method=Image.Resampling.LANCZOS), (0, visual_y))
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rectangle((0, 0, width, visual_y + int(20 * scale)), fill=(4, 5, 5, 255))
        _draw_brand(card_renderer, draw, scale)
        _headline_and_body(card_renderer, image, card, scale, (int(72 * scale), int(height * 0.095), width - int(72 * scale), visual_y - int(12 * scale)), align="left")
        _footer(card_renderer, image, card, scale)
        return image

    if variant == "data_monument":
        image = Image.new("RGBA", (width, height), card_renderer.BG + (255,))
        visual_h = int(height * 0.43)
        image.alpha_composite(ImageOps.fit(base, (width, visual_h), method=Image.Resampling.LANCZOS), (0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        _draw_brand(card_renderer, draw, scale)
        label, value = _primary_metric(card)
        if value:
            draw.text((int(72 * scale), int(height * 0.48)), label.upper(), font=card_renderer._font(int(22 * scale), True), fill=card_renderer.MUTED)
            value_font = card_renderer._font(int(84 * scale), True)
            draw.text((int(72 * scale), int(height * 0.515)), value, font=value_font, fill=card_renderer.ORANGE)
        _headline_and_body(card_renderer, image, card, scale, (int(72 * scale), int(height * 0.66), width - int(72 * scale), int(height * 0.91)))
        _footer(card_renderer, image, card, scale)
        return image

    if variant == "newspaper_panel":
        image = ImageOps.fit(base, (width, height), method=Image.Resampling.LANCZOS).convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        panel = (int(width * 0.08), int(height * 0.52), int(width * 0.92), int(height * 0.93))
        draw.rounded_rectangle(panel, radius=int(10 * scale), fill=(9, 9, 8, 236), outline=card_renderer.ORANGE + (42,), width=max(1, int(scale)))
        _draw_brand(card_renderer, draw, scale)
        _headline_and_body(card_renderer, image, card, scale, (panel[0] + int(36 * scale), panel[1] + int(26 * scale), panel[2] - int(36 * scale), panel[3] - int(36 * scale)))
        _footer(card_renderer, image, card, scale)
        return image

    # full_bleed_bottom fallback
    image = ImageOps.fit(base, (width, height), method=Image.Resampling.LANCZOS).convert("RGBA")
    card_renderer._draw_bottom_gradient(image, top_ratio=0.47)
    _draw_brand(card_renderer, ImageDraw.Draw(image, "RGBA"), scale)
    _headline_and_body(card_renderer, image, card, scale, (int(72 * scale), int(height * 0.66), width - int(72 * scale), int(height * 0.91)))
    _footer(card_renderer, image, card, scale)
    return image


def apply_renderer_patch(card_renderer) -> None:
    if getattr(card_renderer, "_kiyosaki_visual_renderer_version", None) == VISUAL_VARIATION_RUNTIME_VERSION:
        return

    def render_card_image(card: dict, width: int = 1080, height: int = 1350) -> Image.Image:
        direction = card.get("visual_direction") or {}
        variant = str(direction.get("format_variant") or "full_bleed_bottom")
        base = _visual_base(card_renderer, card, width, height)
        image = _compose(card_renderer, card, base, variant, width, height)
        card_renderer._film_grain(image, strength=7)
        return image.convert("RGB")

    def render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
        image = render_card_image(card, width=width, height=height)
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    card_renderer.render_card_image = render_card_image
    card_renderer.render_card_png = render_card_png
    card_renderer._kiyosaki_visual_renderer_version = VISUAL_VARIATION_RUNTIME_VERSION
