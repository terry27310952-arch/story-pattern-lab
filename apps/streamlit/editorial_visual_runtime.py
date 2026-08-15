from __future__ import annotations

from copy import deepcopy
from typing import Callable


DISPLAY_BRAND_LABEL = "キヨサキ"

CHARACTER_BIBLE = {
    "identity": "anonymous adult male financial observer",
    "face": "face completely hidden in shadow; no visible eyes, nose, mouth or expression",
    "wardrobe": "tailored black suit, black shirt, black tie, black leather gloves",
    "lighting": "warm orange rim light, restrained low-key cinematic lighting",
    "mood": "quiet, analytical, institutional, premium, non-promotional",
}

VISUAL_STORY_RULES = {
    "documentary_cover": {
        "character_required": True,
        "character_presence": 0.48,
        "subject": "cinematic Japanese market environment at night with the anonymous analyst as the visual anchor",
        "camera": "medium-wide documentary portrait",
        "text_zone": "bottom",
        "image_strategy": "generated_documentary_scene",
        "information_density": "low",
    },
    "market_environment": {
        "character_required": False,
        "character_presence": 0.0,
        "subject": "cinematic institutional market environment that visualizes the day's market tension without showing a presenter",
        "camera": "wide documentary scene",
        "text_zone": "bottom",
        "image_strategy": "generated_market_environment",
        "information_density": "low",
    },
    "price_instrument": {
        "character_required": False,
        "character_presence": 0.0,
        "subject": "full-frame institutional Bitcoin price monitor and restrained market structure visualization, photographed as a physical financial instrument",
        "camera": "close editorial instrument shot",
        "text_zone": "bottom",
        "image_strategy": "generated_price_visual",
        "information_density": "medium",
    },
    "institutional_desk": {
        "character_required": True,
        "character_presence": 0.24,
        "subject": "institutional derivatives desk with restrained data screens, analyst reviewing positioning rather than presenting to camera",
        "camera": "over-shoulder documentary shot",
        "text_zone": "bottom",
        "image_strategy": "generated_documentary_scene",
        "information_density": "medium",
    },
    "editorial_documentary": {
        "character_required": False,
        "character_presence": 0.0,
        "subject": "documentary visual representing the actual news subject or institution, not a generic crypto trading screen",
        "camera": "editorial news photograph",
        "text_zone": "bottom",
        "image_strategy": "generated_news_visual",
        "information_density": "low",
    },
    "symbolic_paths": {
        "character_required": False,
        "character_presence": 0.0,
        "subject": "three restrained diverging market paths in a realistic dark institutional space, clearly suggesting Bull Base Bear without fantasy graphics",
        "camera": "wide symbolic documentary composition",
        "text_zone": "bottom",
        "image_strategy": "generated_symbolic_scene",
        "information_density": "medium",
    },
    "decision_scene": {
        "character_required": True,
        "character_presence": 0.30,
        "subject": "anonymous analyst at a dark desk reviewing a printed execution plan and pointing to one decision area with a black leather glove",
        "camera": "medium three-quarter documentary shot",
        "text_zone": "bottom",
        "image_strategy": "generated_documentary_scene",
        "information_density": "medium",
    },
    "brand_poster": {
        "character_required": True,
        "character_presence": 0.62,
        "subject": "minimal premium black studio portrait for the closing brand card, strong anonymous analyst silhouette and warm orange rim light",
        "camera": "medium-close brand portrait",
        "text_zone": "bottom",
        "image_strategy": "generated_brand_poster",
        "information_density": "low",
    },
}


def _metric_value(card: dict, metric_id: str, default: str = "") -> str:
    for metric in card.get("metrics") or []:
        if metric.get("id") == metric_id:
            return str(metric.get("value") or default)
    return default


def _source_subject(card: dict) -> str:
    source = card.get("source") or {}
    relevance = source.get("asset_relevance") or {}
    asset = str(relevance.get("primary_asset") or "").strip()
    headline = str(source.get("display_headline_ja") or source.get("short_title") or "").strip()
    publisher = str(source.get("publisher") or "").strip()
    parts = [item for item in [asset, headline, publisher] if item]
    return " / ".join(parts[:3])


def visual_story_mode(card: dict) -> str:
    card_type = card.get("card_type")
    slide = int(card.get("slide") or 1)
    if card_type == "brand_outro":
        return "brand_poster"
    if card_type == "market_conclusion" and slide == 1:
        return "documentary_cover"
    if card_type == "market_conclusion":
        return "market_environment"
    if card_type == "key_levels":
        return "price_instrument"
    if card_type == "derivatives":
        return "institutional_desk"
    if card_type == "news_context":
        return "editorial_documentary"
    if card_type == "scenarios":
        return "symbolic_paths"
    if card_type == "trade_plan":
        return "decision_scene"
    return "market_environment"


def visual_story_for_card(card: dict) -> dict:
    mode = visual_story_mode(card)
    base = deepcopy(VISUAL_STORY_RULES[mode])
    source_subject = _source_subject(card)

    if mode == "editorial_documentary" and source_subject:
        base["subject"] = (
            "documentary editorial image based on the real news subject: "
            f"{source_subject}. Show the institution, asset context, location or real-world business theme rather than a generic chart."
        )
    elif mode == "price_instrument":
        support = _metric_value(card, "btc_primary_support") or _metric_value(card, "btc_support")
        resistance = _metric_value(card, "btc_primary_resistance") or _metric_value(card, "btc_resistance")
        cluster = _metric_value(card, "btc_resistance_cluster")
        detail = " / ".join(item for item in [support, resistance, cluster] if item)
        if detail:
            base["subject"] += f" Renderer will later overlay the locked price structure {detail}; do not draw readable numbers in the image."
    elif mode == "institutional_desk":
        funding = _metric_value(card, "funding")
        oi_delta = _metric_value(card, "oi_change_24h") or _metric_value(card, "oi_change_4h")
        if funding or oi_delta:
            base["subject"] += f" The visual should suggest funding and open-interest monitoring ({funding} / {oi_delta}) without readable generated text."
    elif mode == "symbolic_paths":
        support = _metric_value(card, "btc_primary_support") or _metric_value(card, "btc_support")
        resistance = _metric_value(card, "btc_primary_resistance") or _metric_value(card, "btc_resistance")
        if support or resistance:
            base["subject"] += " The renderer will overlay exact Bull/Base/Bear levels separately."

    base.update(
        {
            "mode": mode,
            "shell": "full_bleed_documentary",
            "brand_label": DISPLAY_BRAND_LABEL,
            "gradient": "bottom_black",
            "headline_style": "orange_bold",
            "body_style": "white_editorial",
            "source_style": "small_muted_footer",
            "metrics_style": "plain_inline_only_when_essential",
            "max_headline_lines": 3,
            "max_body_lines": 4,
            "show_all_internal_fields": False,
            "reference_style": "full-bleed documentary image + bottom black gradient + orange headline + concise white body",
        }
    )
    return base


def _character_prompt() -> str:
    return (
        "Anonymous adult male financial observer, face completely hidden in shadow with absolutely no visible eyes, nose, mouth or expression, "
        "tailored black suit, black shirt, black tie, black leather gloves, realistic fabric and leather texture, warm orange rim light, "
        "quiet analytical institutional presence, premium low-key cinematic realism."
    )


def _ratio_phrase(engine, ratio: str) -> str:
    profile = ((getattr(engine, "OBSERVER_BRAND_SYSTEM", {}) or {}).get("aspect_ratios", {}) or {}).get(ratio, {})
    width = profile.get("width", 1080)
    height = profile.get("height", 1350 if ratio == "4:5" else 1920)
    return f"{ratio} vertical composition, {width}x{height}"


def build_visual_story_prompt(engine, card: dict, story: dict, ratio: str) -> str:
    character_required = bool(story.get("character_required"))
    character_clause = _character_prompt() if character_required else (
        "No presenter, no human mascot, no anonymous suited character in this frame. Let the market subject itself carry the visual story."
    )
    ratio_phrase = _ratio_phrase(engine, ratio)
    return (
        "Create a premium documentary-style financial editorial image for a Japanese Instagram carousel. "
        "The image must be full-bleed, photographic, realistic, cinematic and visually specific to this card's subject. "
        "Do not create a generic black UI card and do not place boxed KPI widgets across the frame. "
        f"Primary visual subject: {story.get('subject')}. "
        f"{character_clause} "
        f"Camera: {story.get('camera')}. "
        "Composition: the upper 60-68 percent should be a strong uninterrupted documentary visual; the lower 32-40 percent should naturally fall into darker tones "
        "so a deterministic renderer can add a black bottom gradient, bold orange Japanese headline, concise white body copy and a small source footer. "
        "Leave clean negative space in the lower third. Do not render any readable Japanese or English text, logos, tickers, watermarks, price labels or article screenshots in the generated image. "
        "Restrained black, charcoal, warm tungsten and orange visual language; realistic environments; no glossy crypto-ad aesthetic. "
        "Avoid cyberpunk neon overload, holograms, floating coins, money rain, luxury flex, influencer thumbnails, sci-fi armor, cartoon or anime. "
        f"{ratio_phrase}."
    )


def _apply_story_to_direction(engine, card: dict, direction: dict) -> dict:
    story = visual_story_for_card(card)
    next_direction = dict(direction or {})
    next_direction["visual_story"] = story
    next_direction["composition_type"] = "full_bleed_documentary"
    next_direction["render_shell"] = "documentary_editorial"
    next_direction["text_zone"] = "bottom"
    next_direction["overlay_gradient"] = "bottom_black"
    next_direction["headline_style"] = "orange_bold"
    next_direction["body_style"] = "white_editorial"
    next_direction["character_present"] = bool(story.get("character_required"))
    next_direction["character_visibility"] = float(story.get("character_presence") or 0.0)
    next_direction["primary_visual"] = story.get("subject")
    next_direction["image_strategy"] = story.get("image_strategy")
    next_direction["information_density"] = story.get("information_density")
    next_direction["image_prompts"] = {
        "4:5": build_visual_story_prompt(engine, card, story, "4:5"),
        "9:16": build_visual_story_prompt(engine, card, story, "9:16"),
    }
    if not story.get("character_required"):
        # Keep legacy shot metadata untouched for old validators, but make the canonical
        # visual-story contract explicit that no character is rendered on this frame.
        next_direction["character_runtime"] = {
            "present": False,
            "shot": "none",
            "pose": "none",
            "presence": 0.0,
        }
    else:
        next_direction["character_runtime"] = {
            "present": True,
            "shot": next_direction.get("character_shot"),
            "pose": next_direction.get("character_pose"),
            "presence": next_direction.get("character_visibility"),
        }
    return next_direction


EDITORIAL_SHELL_CSS = r"""
/* Kiyosaki documentary editorial carousel shell.
   Inspired by the supplied Instagram reference: full-bleed visual, bottom black
   gradient, orange headline, concise white body, and a small brand label. */
.observer-preview {
    position: relative !important;
    width: min(100%, 430px) !important;
    aspect-ratio: 4 / 5 !important;
    overflow: hidden !important;
    border-radius: 4px !important;
    border: 0 !important;
    padding: 0 !important;
    color: #f7f3eb !important;
    background: #090909 !important;
    box-shadow: 0 16px 38px rgba(0,0,0,.22) !important;
    isolation: isolate !important;
}
.observer-preview::after {
    content: "" !important;
    position: absolute !important;
    inset: 0 !important;
    z-index: 2 !important;
    pointer-events: none !important;
    background: linear-gradient(180deg, rgba(0,0,0,0) 37%, rgba(0,0,0,.08) 49%, rgba(0,0,0,.74) 69%, rgba(0,0,0,.98) 100%) !important;
}
.observer-preview .observer-copy {
    position: absolute !important;
    inset: 0 !important;
    max-width: none !important;
    z-index: 4 !important;
    pointer-events: none !important;
}
.observer-preview .observer-eyebrow {
    position: absolute !important;
    top: 24px !important;
    left: 28px !important;
    margin: 0 !important;
    color: rgba(255,255,255,.94) !important;
    font-size: .72rem !important;
    line-height: 1 !important;
    font-weight: 800 !important;
    letter-spacing: .08em !important;
    text-transform: none !important;
    text-shadow: 0 2px 10px rgba(0,0,0,.45) !important;
}
.observer-preview .observer-headline {
    position: absolute !important;
    left: 28px !important;
    right: 28px !important;
    bottom: 118px !important;
    margin: 0 !important;
    color: #f5a623 !important;
    font-size: 1.72rem !important;
    line-height: 1.13 !important;
    font-weight: 850 !important;
    letter-spacing: -.035em !important;
    text-shadow: 0 2px 18px rgba(0,0,0,.58) !important;
    white-space: pre-line !important;
}
.observer-preview .observer-sub {
    display: none !important;
}
.observer-preview .observer-message {
    position: absolute !important;
    left: 28px !important;
    right: 28px !important;
    bottom: 58px !important;
    margin: 0 !important;
    color: rgba(255,255,255,.94) !important;
    font-size: .89rem !important;
    line-height: 1.50 !important;
    font-weight: 520 !important;
    display: -webkit-box !important;
    -webkit-line-clamp: 3 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    text-shadow: 0 1px 12px rgba(0,0,0,.70) !important;
}
.observer-preview .observer-source {
    position: absolute !important;
    left: 28px !important;
    right: 28px !important;
    bottom: 19px !important;
    z-index: 5 !important;
    color: rgba(255,255,255,.50) !important;
    font-size: .63rem !important;
    line-height: 1.2 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}
.observer-preview .observer-metrics {
    position: absolute !important;
    left: 28px !important;
    right: 28px !important;
    bottom: 192px !important;
    z-index: 4 !important;
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 7px 14px !important;
    background: transparent !important;
}
.observer-preview .observer-metric {
    border: 0 !important;
    background: transparent !important;
    padding: 0 !important;
    border-radius: 0 !important;
    min-width: 0 !important;
}
.observer-preview .observer-metric span {
    display: block !important;
    color: rgba(255,255,255,.48) !important;
    font-size: .55rem !important;
    line-height: 1 !important;
    margin: 0 0 3px 0 !important;
}
.observer-preview .observer-metric strong {
    color: rgba(255,255,255,.94) !important;
    font-size: .78rem !important;
    line-height: 1.05 !important;
    font-weight: 720 !important;
}
.observer-preview .observer-metric.support strong { color: #b8d9c2 !important; }
.observer-preview .observer-metric.risk strong,
.observer-preview .observer-metric.resistance strong { color: #e6b0a8 !important; }

/* Main visual changes by card role. Layout stays branded and consistent while the
   visual subject changes, matching the rhythm of the supplied documentary carousel. */
.observer-preview.hero_character {
    background:
        radial-gradient(circle at 67% 28%, rgba(238,153,73,.23), transparent 24%),
        linear-gradient(145deg, #080909 0%, #11110f 45%, #030303 100%) !important;
}
.observer-preview.hero_character .observer-figure {
    display: block !important;
    position: absolute !important;
    z-index: 1 !important;
    left: 32% !important;
    right: auto !important;
    bottom: 82px !important;
    width: 50% !important;
    height: 70% !important;
    opacity: .96 !important;
    filter: drop-shadow(-12px 0 22px rgba(241,112,36,.22)) !important;
}
.observer-preview.chart_primary {
    background:
        linear-gradient(180deg, rgba(8,15,18,.05), rgba(2,4,5,.40)),
        repeating-linear-gradient(0deg, rgba(255,255,255,.045) 0 1px, transparent 1px 42px),
        repeating-linear-gradient(90deg, rgba(255,255,255,.035) 0 1px, transparent 1px 58px),
        radial-gradient(circle at 68% 30%, rgba(66,121,135,.28), transparent 30%),
        #071013 !important;
}
.observer-preview.chart_primary::before {
    content: "" !important;
    position: absolute !important;
    z-index: 1 !important;
    left: 6% !important;
    right: 6% !important;
    top: 21% !important;
    height: 28% !important;
    opacity: .78 !important;
    background:
        linear-gradient(164deg, transparent 0 16%, rgba(239,168,82,.75) 16.5% 17.5%, transparent 18% 36%, rgba(239,168,82,.75) 36.5% 37.5%, transparent 38% 55%, rgba(239,168,82,.75) 55.5% 56.5%, transparent 57% 74%, rgba(239,168,82,.75) 74.5% 75.5%, transparent 76%),
        linear-gradient(180deg, transparent 48%, rgba(255,255,255,.12) 49%, transparent 50%) !important;
    filter: drop-shadow(0 0 12px rgba(239,168,82,.22)) !important;
}
.observer-preview.chart_primary .observer-figure { display: none !important; }
.observer-preview.chart_primary .observer-metrics { display: flex !important; }

.observer-preview.data_primary {
    background:
        radial-gradient(circle at 72% 26%, rgba(227,142,61,.14), transparent 24%),
        repeating-linear-gradient(0deg, rgba(255,255,255,.022) 0 1px, transparent 1px 32px),
        linear-gradient(135deg, #071013, #0d1111 48%, #050606) !important;
}
.observer-preview.data_primary::before {
    content: "" !important;
    position: absolute !important;
    z-index: 1 !important;
    left: 9% !important;
    right: 9% !important;
    top: 16% !important;
    height: 30% !important;
    border: 1px solid rgba(255,255,255,.07) !important;
    background:
        linear-gradient(90deg, rgba(255,255,255,.035) 0 31%, transparent 31% 34%, rgba(255,255,255,.028) 34% 66%, transparent 66% 69%, rgba(255,255,255,.035) 69% 100%),
        linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.012)) !important;
}
.observer-preview.data_primary .observer-figure {
    display: block !important;
    width: 25% !important;
    height: 36% !important;
    right: 8% !important;
    bottom: 38% !important;
    opacity: .72 !important;
}
.observer-preview.data_primary .observer-metrics { display: flex !important; }

.observer-preview.news_primary {
    background:
        linear-gradient(160deg, rgba(15,12,10,.05), rgba(0,0,0,.35)),
        radial-gradient(circle at 35% 24%, rgba(211,173,126,.18), transparent 28%),
        #171411 !important;
}
.observer-preview.news_primary::before {
    content: "" !important;
    position: absolute !important;
    z-index: 1 !important;
    left: 11% !important;
    top: 13% !important;
    width: 72% !important;
    height: 38% !important;
    transform: rotate(-2deg) !important;
    border: 1px solid rgba(255,255,255,.09) !important;
    background:
        repeating-linear-gradient(180deg, rgba(255,255,255,.12) 0 2px, transparent 2px 15px),
        linear-gradient(145deg, rgba(245,239,226,.10), rgba(255,255,255,.025)) !important;
    box-shadow: 18px 16px 0 rgba(255,255,255,.025) !important;
}
.observer-preview.news_primary .observer-figure { display: none !important; }
.observer-preview.news_primary .observer-metrics { display: none !important; }

.observer-preview.scenario_primary {
    background:
        linear-gradient(155deg, rgba(12,13,13,.12), rgba(0,0,0,.30)),
        #070808 !important;
}
.observer-preview.scenario_primary::before {
    content: "" !important;
    position: absolute !important;
    z-index: 1 !important;
    left: 7% !important;
    right: 7% !important;
    top: 11% !important;
    height: 45% !important;
    background:
        linear-gradient(116deg, transparent 0 27%, rgba(239,168,82,.34) 27.4% 28.5%, transparent 29%),
        linear-gradient(90deg, transparent 0 49%, rgba(255,255,255,.16) 49.4% 50.6%, transparent 51%),
        linear-gradient(64deg, transparent 0 71%, rgba(167,184,177,.22) 71.4% 72.5%, transparent 73%) !important;
    filter: drop-shadow(0 0 14px rgba(239,168,82,.14)) !important;
}
.observer-preview.scenario_primary .observer-figure { display: none !important; }
.observer-preview.scenario_primary .observer-metrics { display: flex !important; }

.observer-preview.character_side {
    background:
        radial-gradient(circle at 70% 27%, rgba(237,145,58,.17), transparent 26%),
        linear-gradient(145deg, #0b0c0c, #12100e 50%, #050505) !important;
}
.observer-preview.character_side .observer-figure {
    display: block !important;
    width: 30% !important;
    height: 48% !important;
    right: 6% !important;
    bottom: 32% !important;
    opacity: .84 !important;
}

.observer-preview.minimal_text {
    background:
        radial-gradient(circle at 58% 27%, rgba(111,131,137,.20), transparent 30%),
        linear-gradient(150deg, #0a0e10, #151719 50%, #050606) !important;
}
.observer-preview.minimal_text .observer-figure { display: none !important; }
.observer-preview.minimal_text .observer-metrics { display: none !important; }

.observer-preview.brand_outro {
    background:
        radial-gradient(circle at 50% 28%, rgba(241,112,36,.28), transparent 26%),
        linear-gradient(180deg, #050505 0%, #0b0907 54%, #000 100%) !important;
}
.observer-preview.brand_outro .observer-figure {
    display: block !important;
    left: 25% !important;
    right: auto !important;
    top: 12% !important;
    bottom: auto !important;
    width: 50% !important;
    height: 58% !important;
    opacity: .98 !important;
}
.observer-preview.brand_outro .observer-metrics { display: none !important; }
.observer-preview.brand_outro .observer-headline {
    color: #fff7eb !important;
    text-align: center !important;
    bottom: 118px !important;
}
.observer-preview.brand_outro .observer-message {
    text-align: center !important;
    bottom: 54px !important;
}
"""


def _install_streamlit_shell_patch() -> None:
    try:
        import streamlit as st
    except Exception:
        return

    if getattr(st, "_kiyosaki_editorial_shell_patch", False):
        return

    original_markdown: Callable = st.markdown

    def markdown(body, *args, **kwargs):
        if isinstance(body, str) and ".observer-preview" in body and "<style" in body:
            body = body + "\n<style>\n" + EDITORIAL_SHELL_CSS + "\n</style>"
        return original_markdown(body, *args, **kwargs)

    st.markdown = markdown
    st._kiyosaki_editorial_shell_patch = True


def apply_editorial_visual_patch(reasoning_engine) -> None:
    """Upgrade the visual layer to a documentary Instagram-carousel grammar.

    The supplied reference keeps the shell consistent while changing the main
    visual on every slide. This patch therefore preserves the existing card data,
    reasoning, QA and exports, but replaces the visual-story contract and preview
    shell. Character identity remains prompt-based and no reference image is
    required for runtime generation.
    """
    if getattr(reasoning_engine, "_kiyosaki_editorial_visual_patch_applied", False):
        _install_streamlit_shell_patch()
        return

    original_visual_system: Callable = reasoning_engine.editor_pass_visual_system

    def editor_pass_visual_system(cards: list[dict]) -> list[dict]:
        enriched = original_visual_system(cards)
        for card in enriched:
            card["visual_direction"] = _apply_story_to_direction(
                reasoning_engine,
                card,
                card.get("visual_direction") or {},
            )
        return enriched

    reasoning_engine.editor_pass_visual_system = editor_pass_visual_system
    reasoning_engine.CHARACTER_BIBLE = CHARACTER_BIBLE
    reasoning_engine.VISUAL_STORY_RULES = VISUAL_STORY_RULES
    reasoning_engine.visual_story_for_card = visual_story_for_card
    reasoning_engine.build_visual_story_prompt = lambda card, story, ratio: build_visual_story_prompt(
        reasoning_engine, card, story, ratio
    )
    reasoning_engine.EDITORIAL_SHELL_CSS = EDITORIAL_SHELL_CSS

    brand_system = getattr(reasoning_engine, "OBSERVER_BRAND_SYSTEM", None)
    if isinstance(brand_system, dict):
        brand_system.pop("reference_asset_path", None)
        brand_system["character_consistency_source"] = "character_bible"
        brand_system["character_bible"] = CHARACTER_BIBLE
        brand_system["editorial_shell"] = {
            "layout": "full_bleed_documentary",
            "text_zone": "bottom",
            "gradient": "bottom_black",
            "headline": "orange_bold",
            "body": "white_editorial",
            "brand_label": DISPLAY_BRAND_LABEL,
        }

    reasoning_engine._kiyosaki_editorial_visual_patch_applied = True
    _install_streamlit_shell_patch()
