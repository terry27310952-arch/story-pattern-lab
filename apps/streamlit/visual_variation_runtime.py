from __future__ import annotations

import copy
import hashlib
import random
import time
from collections import deque
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageOps


VISUAL_VARIATION_RUNTIME_VERSION = "visual-blueprint-v5.0"

# Brand invariants stay fixed. The rest of the composition is allowed to move.
DISPLAY_BRAND_LABEL = "キヨサキ"
RECENT_BLUEPRINTS: deque[str] = deque(maxlen=6)
RECENT_SCENES: deque[str] = deque(maxlen=24)

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


def _scene(
    scene_id: str,
    environment: str,
    action: str,
    body_orientation: str,
    hand_action: str,
    props: tuple[str, ...],
    camera_distance: str,
    camera_height: str,
    camera_side: str,
    lens: str,
    lighting: str,
    foreground: str,
    background: str,
    character_scale: float,
    character_crop: str,
    character_position: str,
    motion_state: str,
    negative_space: str,
    character_present: bool = True,
) -> dict:
    return {
        "id": scene_id,
        "environment": environment,
        "action": action,
        "body_orientation": body_orientation,
        "hand_action": hand_action,
        "props": list(props),
        "camera_distance": camera_distance,
        "camera_height": camera_height,
        "camera_side": camera_side,
        "lens": lens,
        "lighting": lighting,
        "foreground": foreground,
        "background": background,
        "character_scale": character_scale,
        "character_crop": character_crop,
        "character_position": character_position,
        "motion_state": motion_state,
        "negative_space": negative_space,
        "character_present": character_present,
    }


# These are physical scenes, not abstract pose labels. The image model receives a
# visible action, body geometry, hand interaction, lens and location on every card.
SCENE_ARCHETYPES: dict[str, list[dict]] = {
    "market_conclusion": [
        _scene(
            "market_wall_observer",
            "real institutional trading room at night",
            "standing several meters from a wall of market monitors and studying the whole room rather than posing for camera",
            "three-quarter rear view with shoulders turned about thirty degrees away from camera",
            "left gloved hand holds a thin folded market report at thigh level; right hand hangs naturally",
            ("folded market report", "monitor wall"),
            "medium-wide",
            "waist height",
            "rear left",
            "35mm documentary lens",
            "monitor spill with one restrained warm practical behind the subject",
            "soft blurred edge of a nearby monitor",
            "real trading desks and dim operators' screens softly out of focus",
            0.30,
            "three-quarter full body",
            "right_center",
            "still observational pause",
            "large clean area on the left for the main thesis",
        ),
        _scene(
            "market_window_risk_check",
            "private high-floor market office overlooking a night city",
            "standing beside the window and checking a tablet before turning back toward the market screens",
            "clean side profile with torso facing the window",
            "one gloved hand holds a tablet low; the other rests naturally in a trouser pocket",
            ("tablet", "window glass"),
            "medium",
            "chest height",
            "side right",
            "50mm documentary lens",
            "cool city spill with a narrow warm rim from the room",
            "dark window frame crossing one edge",
            "distant city lights and subdued reflections",
            0.34,
            "knees-up side profile",
            "right_lower",
            "quiet risk check",
            "upper-left negative space for headline copy",
        ),
        _scene(
            "market_corridor_walk",
            "dim institutional operations corridor connecting trading rooms",
            "walking away from the camera toward a brighter dealing room with a report tucked under one arm",
            "rear three-quarter walking posture",
            "right arm carries a slim report folder; left arm swings naturally",
            ("report folder",),
            "wide",
            "low waist height",
            "rear center",
            "28mm documentary lens",
            "practical ceiling lights with faint warm edge light",
            "soft doorway edge in foreground",
            "open trading room glowing at the end of the corridor",
            0.20,
            "full body small",
            "center_lower",
            "walking",
            "open upper and left field for editorial copy",
        ),
        _scene(
            "market_desk_lean",
            "dark research desk inside a real trading office",
            "standing at the desk and leaning forward slightly to compare a printed chart with a distant monitor",
            "three-quarter side view, torso angled toward the desk",
            "both gloved hands rest apart on the desk surface, never clasped",
            ("printed chart", "desk lamp", "keyboard"),
            "medium-wide",
            "slightly above desk height",
            "front left",
            "40mm documentary lens",
            "soft tungsten desk lamp plus low monitor light",
            "out-of-focus paper corner near lens",
            "monitor wall remains distant and secondary",
            0.28,
            "thigh-up",
            "right_center",
            "active comparison",
            "left half kept dark and clean for the conclusion",
        ),
    ],
    "key_levels": [
        _scene(
            "level_wall_point",
            "institutional trading room with one large physical wall monitor",
            "standing with his back to camera and indicating one horizontal price area on the wall display",
            "straight back view with body weight shifted slightly to the left leg",
            "right arm raised; index finger points toward the monitor while left arm stays relaxed",
            ("wall monitor",),
            "wide",
            "waist height",
            "rear right",
            "35mm documentary lens",
            "low monitor spill and subtle warm rim light",
            "dark desk edge at the bottom of frame",
            "other screens remain soft and subordinate",
            0.20,
            "full body small",
            "left_edge",
            "precise pointing action",
            "center and upper-right remain open for support/resistance typography",
        ),
        _scene(
            "level_glass_board_mark",
            "glass analysis wall inside an institutional office",
            "marking a single horizontal level on transparent glass while market screens glow behind it",
            "side profile, shoulders perpendicular to camera",
            "right gloved hand uses a white grease pencil on the glass; left hand holds the cap",
            ("glass board", "grease pencil"),
            "medium",
            "eye level",
            "side left",
            "50mm documentary lens",
            "cool monitor light through glass with restrained orange edge light",
            "blurred glass reflection near lens",
            "real market screens visible through the glass without readable generated text",
            0.27,
            "waist-up side profile",
            "right_edge",
            "marking",
            "left-center reserved for the two key levels",
        ),
        _scene(
            "level_over_shoulder_map",
            "standing terminal station with a large monitor and printed market map",
            "cross-checking a printed market map against a screen from over the shoulder",
            "rear three-quarter standing posture",
            "left hand holds the printout; right hand rests on the terminal desk beside the keyboard",
            ("printed market map", "keyboard", "monitor"),
            "medium-close over shoulder",
            "shoulder height",
            "rear left",
            "55mm documentary lens",
            "monitor spill with almost no fill light",
            "shoulder and printout create a natural foreground frame",
            "single terminal screen dominates the background",
            0.25,
            "upper torso over shoulder",
            "left_lower",
            "cross-checking",
            "right half kept clear for numeric hierarchy",
        ),
        _scene(
            "level_glove_price_map",
            "dark physical research table with a printed Bitcoin structure chart",
            "reviewing the price map from directly above; only the observer's forearms and black leather gloves enter the frame",
            "head and torso outside the frame",
            "one glove holds a metal pen over a level while the other pins the paper flat",
            ("printed chart", "metal pen", "ruler"),
            "close overhead detail",
            "top-down",
            "overhead",
            "70mm detail lens",
            "single warm desk practical with deep falloff",
            "paper edge and pen tip in crisp focus",
            "dark desk texture with no monitor wall",
            0.10,
            "hands-only detail",
            "bottom_left",
            "measured annotation",
            "upper half open for support/resistance copy",
        ),
    ],
    "derivatives": [
        _scene(
            "derivatives_sideways_tablet",
            "private derivatives desk with restrained futures screens",
            "sitting sideways to the desk while cross-checking a tablet against two monitors",
            "seated three-quarter rear profile",
            "left hand holds a tablet; right gloved hand operates the mouse",
            ("tablet", "mouse", "two monitors"),
            "medium-wide",
            "seated eye level",
            "rear right",
            "50mm documentary lens",
            "monitor spill and a distant tungsten desk lamp",
            "blurred monitor edge in foreground",
            "futures screens softly visible without readable generated text",
            0.29,
            "seated knees-up",
            "right_lower",
            "active data cross-check",
            "upper-left left clean for funding/OI information",
        ),
        _scene(
            "derivatives_terminal_switch",
            "standing execution console inside a dark trading room",
            "adjusting one physical terminal control while watching a derivatives screen",
            "side-rear standing posture",
            "right gloved fingers adjust a small console control; left hand rests on the desk edge",
            ("terminal console", "monitor"),
            "medium close",
            "chest height",
            "rear left",
            "60mm documentary lens",
            "localized screen light with narrow warm rim",
            "terminal rack creates a dark foreground strip",
            "rows of subdued operations terminals",
            0.24,
            "waist-up rear profile",
            "right_center",
            "precise terminal adjustment",
            "left side reserved for metrics",
        ),
        _scene(
            "derivatives_printout_compare",
            "long institutional research desk",
            "standing over two derivatives printouts and comparing them before looking back to the market wall",
            "three-quarter front-side view with face still hidden by shadow and viewing angle",
            "hands spread apart, each glove touching a different sheet",
            ("two printouts", "calculator", "desk"),
            "medium",
            "slightly high",
            "front right",
            "45mm documentary lens",
            "warm desk practical with cool ambient screen spill",
            "calculator blurred in near foreground",
            "distant market wall in soft focus",
            0.26,
            "thigh-up",
            "left_lower",
            "comparative analysis",
            "upper-right kept open for derivatives headline",
        ),
        _scene(
            "derivatives_server_aisle",
            "narrow infrastructure aisle between terminal and server racks",
            "walking slowly through the aisle while checking a tablet of positioning data",
            "rear side walking posture",
            "both hands support the tablet at waist level without clasping",
            ("tablet", "server racks"),
            "wide",
            "waist height",
            "rear left",
            "32mm documentary lens",
            "cool rack LEDs with very restrained warm edge light",
            "rack edge close to lens",
            "long repeating aisle perspective",
            0.19,
            "full body small",
            "right_edge",
            "slow walking review",
            "left-center negative space for data copy",
        ),
    ],
    "news_context": [
        _scene(
            "news_report_reading",
            "quiet institutional briefing desk with one practical lamp",
            "reading a printed research report before looking toward the market screens",
            "side profile seated or standing at desk, face hidden by darkness",
            "both hands hold opposite corners of the report",
            ("printed research report", "desk lamp"),
            "medium",
            "chest height",
            "side right",
            "50mm documentary lens",
            "warm practical pool with deep surrounding shadow",
            "soft lamp shade edge in foreground",
            "dark office shelves and distant screens",
            0.25,
            "waist-up side profile",
            "right_lower",
            "focused reading",
            "left and upper field for news interpretation",
        ),
        _scene(
            "news_briefing_walk",
            "institutional corridor outside a research room",
            "walking toward camera at an angle while carrying a slim briefing folder, never presenting to camera",
            "three-quarter walking posture with head turned toward an open briefing-room doorway",
            "left hand carries folder at side; right hand lightly touches the door frame",
            ("briefing folder", "doorway"),
            "wide",
            "waist height",
            "front left",
            "35mm documentary lens",
            "practical corridor light and dim warm room spill",
            "door frame in foreground",
            "briefing room visible in the background",
            0.20,
            "full body small",
            "left_edge",
            "walking transition",
            "right half kept open for source context",
        ),
        _scene(
            "news_pinboard_review",
            "dark research wall with pinned physical documents and one monitor",
            "pinning a new printed clipping to the research wall and comparing it with existing material",
            "over-shoulder standing view",
            "right glove pins the clipping; left hand holds two additional sheets",
            ("printed clipping", "pinboard", "paper sheets"),
            "medium over shoulder",
            "shoulder height",
            "rear right",
            "55mm documentary lens",
            "soft task light on paper with low orange rim",
            "blurred shoulder edge in foreground",
            "tactile research wall with unreadable paper detail",
            0.24,
            "upper torso over shoulder",
            "right_center",
            "document placement",
            "left column open for headline and interpretation",
        ),
        _scene(
            "news_institution_establishing",
            "real-world institution, exchange, office, data center or city location semantically connected to the source story",
            "documentary establishing shot of the actual subject environment with no presenter in frame",
            "none",
            "none",
            (),
            "wide establishing",
            "human eye level",
            "observational",
            "28mm documentary lens",
            "available practical light with restrained cinematic contrast",
            "real architectural or street foreground detail",
            "people may appear only as incidental unidentifiable background staff",
            0.0,
            "no character",
            "none",
            "observational establishing shot",
            "one side naturally darker for copy",
            False,
        ),
    ],
    "scenarios": [
        _scene(
            "scenario_three_screen_room",
            "wide dark strategy room with three physically separated monitor zones",
            "standing small in the center and comparing the three zones without pointing",
            "straight back view, feet planted shoulder width apart",
            "arms hang naturally at the sides",
            ("three monitor zones",),
            "very wide",
            "waist height",
            "rear center",
            "28mm documentary lens",
            "low practical room light with thin warm rim",
            "desk silhouettes at both lower corners",
            "three distinct screen groups form a realistic visual fork",
            0.13,
            "full body very small",
            "bottom_center",
            "still comparison",
            "three broad visual lanes remain readable",
        ),
        _scene(
            "scenario_overhead_sheets",
            "large dark conference table",
            "arranging three separate scenario sheets from a top-down viewpoint; only black-gloved hands are visible",
            "head and torso outside frame",
            "left glove moves one sheet while right glove holds a pen above the center sheet",
            ("three scenario sheets", "pen"),
            "overhead detail",
            "top-down",
            "overhead",
            "65mm overhead lens",
            "soft warm table light with strong edge falloff",
            "table texture fills the frame",
            "no monitor wall; physical planning materials only",
            0.08,
            "hands-only detail",
            "bottom_center",
            "arranging options",
            "three clear paper zones with copy space around them",
        ),
        _scene(
            "scenario_corridor_junction",
            "real institutional corridor that splits into three visible directions",
            "pausing at the junction and looking toward one route while keeping the body centered",
            "rear full-body silhouette",
            "hands remain separated and relaxed at the sides",
            ("corridor junction",),
            "very wide",
            "low waist height",
            "rear center",
            "24mm documentary lens",
            "real ceiling practicals with subtle warm backlight",
            "dark doorway edge in foreground",
            "three architectural directions create the scenario metaphor without fantasy graphics",
            0.12,
            "full body small",
            "bottom_center",
            "hesitation before decision",
            "upper half open for Bull/Base/Bear copy",
        ),
        _scene(
            "scenario_glass_room",
            "glass-walled institutional strategy room overlooking three market workstations",
            "standing behind the glass and observing the three workstations from a distance",
            "three-quarter rear silhouette",
            "one hand loosely holds a report at the side; the other remains relaxed",
            ("glass wall", "report", "three workstations"),
            "wide",
            "chest height",
            "rear right",
            "35mm documentary lens",
            "dim office practicals and controlled reflections",
            "glass reflection crosses foreground",
            "three workstations create distinct realistic zones",
            0.16,
            "full body small",
            "left_lower",
            "quiet scenario review",
            "right and upper areas kept open for scenario labels",
        ),
    ],
    "trade_plan": [
        _scene(
            "plan_notebook_rules",
            "dark execution desk with a physical notebook and printed chart",
            "writing one execution rule into the notebook while checking the printed chart",
            "head mostly outside frame; torso only partially visible",
            "right gloved hand writes with a pen; left glove keeps the chart flat",
            ("notebook", "pen", "printed chart"),
            "close overhead three-quarter",
            "slightly high",
            "front right",
            "70mm detail lens",
            "focused warm desk light with near-black falloff",
            "pen and notebook edge in foreground",
            "single muted monitor far behind",
            0.14,
            "hands and torso detail",
            "right_lower",
            "writing",
            "left and upper field reserved for ENTRY WAIT INVALID",
        ),
        _scene(
            "plan_close_report",
            "institutional trading desk at the end of a review session",
            "closing a report folder after making a decision and turning slightly away from the desk",
            "side three-quarter standing posture",
            "right glove closes the folder; left hand rests separately on the desk edge",
            ("report folder", "desk"),
            "medium",
            "chest height",
            "side left",
            "50mm documentary lens",
            "low tungsten practical with distant monitor spill",
            "folder corner close to lens",
            "market screens soft and secondary",
            0.25,
            "thigh-up side view",
            "right_center",
            "decision completed",
            "left half dark enough for rule copy",
        ),
        _scene(
            "plan_phone_alert",
            "quiet side area of a trading floor beside a dark window",
            "checking one price alert on a phone before returning to the desk",
            "side profile standing posture",
            "right glove holds phone at waist level; left hand remains in pocket",
            ("phone", "window"),
            "medium-wide",
            "waist height",
            "side right",
            "45mm documentary lens",
            "cool window spill with faint orange rim",
            "window mullion in foreground",
            "trading room visible behind through glass",
            0.23,
            "knees-up side profile",
            "left_lower",
            "alert check",
            "upper-right kept open for execution conditions",
        ),
        _scene(
            "plan_table_point",
            "dark conference table inside the trading office",
            "standing over a printed execution plan and indicating one line for the final decision",
            "three-quarter side standing posture",
            "right index finger points to the paper; left glove rests open on another part of the table",
            ("printed execution plan", "conference table"),
            "medium-wide",
            "slightly high",
            "front left",
            "40mm documentary lens",
            "single warm overhead practical and minimal monitor spill",
            "paper corner blurred near lens",
            "empty chairs and dark screens in background",
            0.24,
            "thigh-up",
            "right_lower",
            "rule confirmation",
            "left and top kept clean for the action framework",
        ),
        _scene(
            "plan_doorway_pause",
            "doorway between a dim office and the active trading room",
            "pausing in the doorway and looking back toward the monitor wall before choosing not to enter",
            "rear three-quarter full body posture",
            "both arms stay relaxed and separated at the sides",
            ("doorway",),
            "wide",
            "waist height",
            "rear left",
            "32mm documentary lens",
            "warm room spill behind with dark foreground",
            "door frame forms a strong foreground border",
            "monitor wall glows in the room beyond",
            0.18,
            "full body small",
            "right_edge",
            "pause before action",
            "left two-thirds available for WAIT/INVALID copy",
        ),
        _scene(
            "plan_glove_pen_detail",
            "matte black desk with one clean execution sheet",
            "holding a metal pen above the execution sheet without writing yet; only forearms and black gloves are visible",
            "head and body outside frame",
            "right glove holds pen suspended above the sheet; left glove is open and separate",
            ("execution sheet", "metal pen"),
            "tight detail",
            "top-down oblique",
            "front",
            "85mm detail lens",
            "small warm task light with deep black surroundings",
            "pen tip and glove texture in sharp focus",
            "no screens required",
            0.08,
            "hands-only detail",
            "bottom_right",
            "deliberate waiting",
            "upper and left areas clear for rules",
        ),
    ],
}

OUTRO_SCENE = _scene(
    "brand_outro_locked",
    "dim real institutional trading room with market monitors softly out of focus behind the subject",
    "standing perfectly still as the recurring final brand portrait",
    "front-facing symmetrical waist-up posture",
    "both black leather-gloved hands clasped calmly at the lower abdomen",
    ("softly blurred monitor wall",),
    "medium-close",
    "eye level",
    "front",
    "70mm portrait lens",
    "warm orange rim light tracing the hair, head and shoulders; face kept completely black",
    "subtle dark desk edge if visible",
    "real trading screens softly out of focus, no readable generated text",
    0.62,
    "waist-up front portrait",
    "center",
    "completely still",
    "left side and lower third reserved for brand copy and follow CTA",
)


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


def _scene_penalty(scene: dict, previous: dict | None, used_ids: set[str], counters: dict[str, int]) -> float:
    penalty = 100.0 if scene["id"] in used_ids else 0.0
    if scene["id"] in RECENT_SCENES:
        penalty += 8.0
    if previous:
        if scene["environment"] == previous.get("environment"):
            penalty += 12.0
        if scene["camera_distance"] == previous.get("camera_distance"):
            penalty += 7.0
        if scene["body_orientation"] == previous.get("body_orientation"):
            penalty += 7.0
        if scene["character_position"] == previous.get("character_position"):
            penalty += 5.0
        if set(scene.get("props") or []) & set(previous.get("props") or []):
            penalty += 4.0
    action_text = f"{scene.get('action', '')} {scene.get('body_orientation', '')}".lower()
    if "seated" in action_text and counters.get("seated", 0) >= 1:
        penalty += 18.0
    if "front-facing" in action_text and counters.get("front", 0) >= 1:
        penalty += 12.0
    if "clasp" in str(scene.get("hand_action") or "").lower():
        penalty += 1000.0
    return penalty


def _choose_scene(card: dict, previous: dict | None, used_ids: set[str], counters: dict[str, int], rng: random.Random) -> dict:
    card_type = str(card.get("card_type") or "market_conclusion")
    if card_type == "brand_outro":
        return copy.deepcopy(OUTRO_SCENE)
    pool = SCENE_ARCHETYPES.get(card_type) or SCENE_ARCHETYPES["market_conclusion"]
    ranked = sorted(
        pool,
        key=lambda item: (_scene_penalty(item, previous, used_ids, counters), rng.random()),
    )
    return copy.deepcopy(ranked[0])


def _source_context(card: dict) -> str:
    source = card.get("source") or {}
    parts = [
        str(source.get("display_headline_ja") or "").strip(),
        str(source.get("short_title") or "").strip(),
        str(source.get("publisher") or "").strip(),
    ]
    return " / ".join(item for item in parts if item)[:260]


def _scene_signature(scene: dict) -> str:
    prop_key = ",".join(scene.get("props") or [])
    return "|".join(
        [
            str(scene.get("id") or ""),
            str(scene.get("environment") or ""),
            str(scene.get("camera_distance") or ""),
            str(scene.get("body_orientation") or ""),
            prop_key,
        ]
    )


def _apply_scene_direction(card: dict, scene: dict) -> None:
    direction = card.setdefault("visual_direction", {})
    present = bool(scene.get("character_present", True))
    direction.update(
        {
            "scene_archetype": scene["id"],
            "environment": scene["environment"],
            "character_action": scene["action"],
            "body_orientation": scene["body_orientation"],
            "hand_action": scene["hand_action"],
            "prop": list(scene.get("props") or []),
            "camera_distance": scene["camera_distance"],
            "camera_height": scene["camera_height"],
            "camera_side": scene["camera_side"],
            "lens_language": scene["lens"],
            "lighting_source": scene["lighting"],
            "foreground_element": scene["foreground"],
            "background_activity": scene["background"],
            "character_scale": scene["character_scale"],
            "character_crop": scene["character_crop"],
            "motion_state": scene["motion_state"],
            "negative_space": scene["negative_space"],
            "scene_uniqueness_key": _scene_signature(scene),
            "character_present": present,
            "character_visibility": float(scene["character_scale"]) if present else 0.0,
            "character_shot": scene["character_crop"] if present else "none",
            "character_pose": scene["action"] if present else "none",
            "character_position": scene["character_position"] if present else "none",
            "camera_angle": f"{scene['camera_height']} / {scene['camera_side']}",
            "primary_visual": f"{scene['environment']}; {scene['action']}",
            "image_strategy": "generated_documentary_scene" if present else "generated_documentary_environment",
        }
    )
    direction["character_runtime"] = {
        "present": present,
        "shot": direction["character_shot"],
        "pose": direction["character_pose"],
        "presence": direction["character_visibility"],
    }
    if isinstance(direction.get("visual_story"), dict):
        story = dict(direction["visual_story"])
        story["character_required"] = present
        story["character_presence"] = direction["character_visibility"]
        story["subject"] = direction["primary_visual"]
        story["camera"] = f"{scene['camera_distance']}, {scene['camera_height']}, {scene['camera_side']}, {scene['lens']}"
        direction["visual_story"] = story


def _build_scene_prompt(card: dict, scene: dict, variant: str, ratio: str) -> str:
    variation_clause = FORMAT_PROMPTS.get(variant, FORMAT_PROMPTS["full_bleed_bottom"])
    source_context = _source_context(card)
    ratio_clause = "4:5 vertical composition, 1080x1350" if ratio == "4:5" else "9:16 vertical composition, 1080x1920"
    present = bool(scene.get("character_present", True))
    if card.get("card_type") == "brand_outro":
        return (
            "SCENE FIRST. Create a photorealistic cinematic documentary closing frame inside a dim real institutional trading room. "
            "LOCKED KIYOSAKI CHARACTER: centered front-facing anonymous adult male, waist-up, broad tailored black suit, black shirt, black tie, "
            "black leather gloves clasped calmly at the lower abdomen. The entire face is completely swallowed by black shadow with absolutely no visible eyes, nose, mouth or expression. "
            "Warm orange rim light traces only the hair, head, shoulders and suit edges. Real trading monitors sit softly out of focus behind him. "
            "This is the only card allowed to use the clasped-hands brand pose. Keep it restrained, premium and photographic, never superheroic or poster-CGI. "
            f"Composition: {variation_clause}. Leave {scene['negative_space']}. "
            "Do not render any readable Japanese or English text, ticker labels, logos or watermarks. Do not add a K monogram, orange K symbol, arrow-like brand mark, decorative logo, badge, watermark or icon before the brand name. "
            f"{ratio_clause}."
        )
    if present:
        character_clause = (
            "Recurring KIYOSAKI observer identity: adult male in a tailored black suit, black shirt, black tie and black leather gloves. "
            "His face must remain completely unidentifiable through shadow, rear view, crop or angle; never show readable facial features. "
            "Do not default to a static portrait and do not make him pose for camera. The physical action and body geometry below are mandatory."
        )
    else:
        character_clause = "No presenter or suited observer is visible in this frame; the real-world subject environment carries the story."
    source_clause = f" Story/source context to respect: {source_context}." if source_context else ""
    return (
        "SCENE FIRST. Create a premium observational financial documentary photograph for a Japanese Instagram carousel. "
        f"Environment: {scene['environment']}. Visible action: {scene['action']}. Body geometry: {scene['body_orientation']}. "
        f"Hand interaction: {scene['hand_action']}. Props: {', '.join(scene.get('props') or ['none'])}. "
        f"Camera: {scene['camera_distance']}, {scene['camera_height']}, view from {scene['camera_side']}, {scene['lens']}. "
        f"Lighting: {scene['lighting']}. Foreground: {scene['foreground']}. Background behavior: {scene['background']}. "
        f"Motion state: {scene['motion_state']}. Character framing: {scene['character_crop']} at roughly {int(float(scene['character_scale']) * 100)} percent of the frame, positioned {scene['character_position']}. "
        f"{character_clause}{source_clause} "
        "Photorealistic real materials, natural fabric folds, realistic black leather glove texture, imperfect physical environment, optical depth and documentary lens behavior. "
        "Cinematic means light, lens and composition, not glowing CGI effects. Orange is only a restrained practical or rim accent. "
        f"Composition variant: {variation_clause}. Leave {scene['negative_space']}. "
        "Do not render any readable Japanese or English text, logos, tickers, article screenshots, watermarks or generated UI labels. "
        "Do not add a K monogram, orange K symbol, arrow-like brand mark, decorative logo, badge, watermark or icon before the brand name. "
        "Avoid repeated static standing portraits, clasped hands, presenter stance, superhero pose, cyberpunk neon overload, holograms, floating coins, money rain, luxury flex, cartoon and anime. "
        f"{ratio_clause}."
    )


def _update_image_prompts(card: dict, variant: str, scene: dict) -> None:
    direction = card.setdefault("visual_direction", {})
    direction["image_prompts"] = {
        "4:5": _build_scene_prompt(card, scene, variant, "4:5"),
        "9:16": _build_scene_prompt(card, scene, variant, "9:16"),
    }


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
        previous_scene: dict | None = None
        used_scene_ids: set[str] = set()
        counters = {"seated": 0, "front": 0}
        for card in cards or []:
            variant = _variant_for_card(card, family, previous_variant, rng)
            previous_variant = variant
            scene = _choose_scene(card, previous_scene, used_scene_ids, counters, rng)
            direction = card.setdefault("visual_direction", {})
            direction["deck_family"] = family
            direction["format_variant"] = variant
            direction["visual_blueprint_id"] = signature
            direction["format_instruction"] = FORMAT_PROMPTS.get(variant, "")
            direction["brand_mark_policy"] = "text-only キヨサキ; no K monogram/icon"
            _apply_scene_direction(card, scene)
            if card.get("card_type") == "brand_outro":
                direction["character_style_lock"] = {
                    "face": "smooth fully featureless black face; no eyes nose mouth",
                    "wardrobe": "tailored black suit, black shirt, black tie, black leather gloves",
                    "pose": "front-facing, waist-up, hands clasped calmly at lower abdomen",
                    "lighting": "warm orange rim light around hair, head and shoulders",
                    "background": "dim real trading room with monitor wall softly out of focus",
                    "mood": "quiet premium anonymous financial observer",
                }
            else:
                used_scene_ids.add(scene["id"])
                RECENT_SCENES.append(scene["id"])
                action_text = f"{scene.get('action', '')} {scene.get('body_orientation', '')}".lower()
                if "seated" in action_text:
                    counters["seated"] += 1
                if "front-facing" in action_text:
                    counters["front"] += 1
            _update_image_prompts(card, variant, scene)
            previous_scene = scene

    quality = next_package.setdefault("content_quality", {})
    quality["visual_blueprint"] = {
        "id": signature,
        "family": family,
        "runtime": VISUAL_VARIATION_RUNTIME_VERSION,
        "policy": (
            "fresh briefing-level deck family; physical scene-action archetypes; environment/action/body/hands/props/camera/lens variation; "
            "anti-repetition scoring inside each set and across recent briefings; hands-clasped pose reserved for locked brand outro"
        ),
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
