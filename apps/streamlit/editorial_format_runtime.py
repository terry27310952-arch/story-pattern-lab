from __future__ import annotations

import copy
import hashlib
import random
import time
from collections import deque


EDITORIAL_FORMAT_RUNTIME_VERSION = "editorial-format-v4.5"
RECENT_EDITORIAL_FAMILIES: deque[str] = deque(maxlen=5)

# These families change the information journey, not just the visual skin.
# The final brand outro is always kept last.
EDITORIAL_FAMILIES: dict[str, dict] = {
    "contradiction_first": {
        "order": ["market_conclusion", "key_levels", "derivatives", "news_context", "scenarios", "trade_plan"],
        "frame": "contradiction",
    },
    "news_to_price": {
        "order": ["news_context", "market_conclusion", "key_levels", "derivatives", "scenarios", "trade_plan"],
        "frame": "news_decode",
    },
    "data_to_action": {
        "order": ["derivatives", "key_levels", "market_conclusion", "scenarios", "news_context", "trade_plan"],
        "frame": "evidence_ladder",
    },
    "decision_tree": {
        "order": ["market_conclusion", "scenarios", "key_levels", "trade_plan", "derivatives", "news_context"],
        "frame": "if_then",
    },
    "question_chain": {
        "order": ["key_levels", "market_conclusion", "news_context", "derivatives", "scenarios", "trade_plan"],
        "frame": "question",
    },
    "risk_first": {
        "order": ["market_conclusion", "trade_plan", "key_levels", "derivatives", "news_context", "scenarios"],
        "frame": "risk_filter",
    },
}

HEADLINE_BANK: dict[str, dict[str, list[str]]] = {
    "market_conclusion": {
        "contradiction": [
            "センチメントは弱い。\nでも、価格はまだ崩れていない。",
            "弱気なのに、まだ崩れない。",
        ],
        "news_decode": ["材料より先に、いまの価格を見る", "ニュースの前に、現在地を確認する"],
        "evidence_ladder": ["数字を並べると、まだ方向は決まっていない", "強弱より、いま残っている矛盾を見る"],
        "if_then": ["予想ではなく、条件で方向を決める", "強気か弱気かは、次の条件で変わる"],
        "question": ["なぜ、弱いのに崩れないのか", "いま本当に弱いのは、価格かセンチメントか"],
        "risk_filter": ["最初に見るのは、上値より崩れる条件", "上がる理由より、崩れる条件を先に置く"],
    },
    "key_levels": {
        "contradiction": ["まず見るのはこの2点", "価格の答えは、この上下にある"],
        "news_decode": ["材料を読む前に、価格の境界を置く", "ニュースを判断するための価格帯"],
        "evidence_ladder": ["現在地を数字で固定する", "まず、価格の地図を作る"],
        "if_then": ["上ならここ。下ならここ。", "分岐はこのレンジから始まる"],
        "question": ["上か下か。どこで答えが出る？", "どの価格を超えれば見方が変わる？"],
        "risk_filter": ["守れなければ、見方を変える", "先に無効化ラインを置く"],
    },
    "derivatives": {
        "contradiction": ["絶対値だけでは読まない", "ポジションがあっても、方向とは限らない"],
        "news_decode": ["ニュースより先物はどう傾いたか", "材料の後ろで、ポジションを見る"],
        "evidence_ladder": ["Funding、OI、RSIを分けて読む", "先物は3つの数字で温度を見る"],
        "if_then": ["OIが増えた時だけ、次の解釈へ", "Fundingだけでは方向を決めない"],
        "question": ["本当にロング優勢なのか？", "ポジションは増えたのか、それとも残っているだけか"],
        "risk_filter": ["偏りが強いほど、逆回転も見る", "先物の偏りを追いかけない"],
    },
    "news_context": {
        "contradiction": ["材料と価格は、別々に確認する", "ニュースが出ても、反応は別問題"],
        "news_decode": ["このニュースは、何を変えるのか", "ヘッドラインを市場の言葉に直す"],
        "evidence_ladder": ["ニュースは証拠の一つに下げる", "材料は、価格と並べて初めて使う"],
        "if_then": ["反応データがある時だけ、価格と結ぶ", "材料が価格に残れば、次の判断へ"],
        "question": ["このニュースは、本当にBTC材料か？", "市場はこの材料を買っているのか？"],
        "risk_filter": ["材料だけでは、ポジションを増やさない", "反応がなければ、ニュースの重みを下げる"],
    },
    "scenarios": {
        "contradiction": ["次の動きは3つに分ける", "上・横・下。予想より条件で分ける"],
        "news_decode": ["材料が効くなら、価格はこの順で動く", "ニュース後の経路を3つに分ける"],
        "evidence_ladder": ["数字を、3つの経路に変換する", "データの最後は、シナリオに落とす"],
        "if_then": ["IF / THENで3つの道を作る", "条件が変われば、シナリオも変える"],
        "question": ["次に起きるのは、上・横・下のどれか", "どの条件で次の道に入る？"],
        "risk_filter": ["強気シナリオより、崩れ方を先に決める", "シナリオは無効化条件から作る"],
    },
    "trade_plan": {
        "contradiction": ["条件を先に固定する", "入る条件より、入らない条件を先に決める"],
        "news_decode": ["材料ではなく、執行条件に落とす", "ニュースを見た後に決めるのは、この3つだけ"],
        "evidence_ladder": ["最後はENTRY / WAIT / INVALID", "データを行動に変える"],
        "if_then": ["IF ENTRY / IF WAIT / IF INVALID", "条件が揃うまで、何もしない"],
        "question": ["いま入る理由はある？", "入らない条件まで決まっているか？"],
        "risk_filter": ["ENTRYよりINVALIDを先に見る", "間違えた時の行動を先に決める"],
    },
}

BODY_MODE = {
    "contradiction": "tension_then_evidence",
    "news_decode": "what_why_reaction",
    "evidence_ladder": "fact_then_interpretation",
    "if_then": "condition_then_action",
    "question": "question_then_answer",
    "risk_filter": "risk_then_permission",
}


def _fingerprint(brief: dict, resources: list[dict] | None = None) -> str:
    material = [
        str(brief.get("title") or ""),
        str(brief.get("one_line") or ""),
        str(brief.get("generated_at") or ""),
        str(time.time_ns()),
    ]
    for item in (resources or [])[:10]:
        material.append(str(item.get("title") or item.get("short_title") or ""))
    return hashlib.sha256("|".join(material).encode("utf-8", errors="ignore")).hexdigest()


def select_editorial_family(seed_hex: str, recent: list[str] | None = None) -> str:
    names = list(EDITORIAL_FAMILIES)
    recent_names = list(recent or RECENT_EDITORIAL_FAMILIES)
    previous = recent_names[-1] if recent_names else ""
    candidates = [name for name in names if name != previous]
    if len(recent_names) >= 3:
        recent_set = set(recent_names[-3:])
        fresher = [name for name in candidates if name not in recent_set]
        if fresher:
            candidates = fresher
    rng = random.Random(int(seed_hex[:16], 16))
    return rng.choice(candidates or names)


def _sort_cards(cards: list[dict], order: list[str]) -> list[dict]:
    outro = [card for card in cards if card.get("card_type") == "brand_outro"]
    content = [card for card in cards if card.get("card_type") != "brand_outro"]
    rank = {card_type: i for i, card_type in enumerate(order)}
    # Preserve relative order for repeated roles while allowing briefing-level story order.
    indexed = list(enumerate(content))
    indexed.sort(key=lambda pair: (rank.get(str(pair[1].get("card_type")), 999), pair[0]))
    sorted_cards = [card for _, card in indexed]
    return sorted_cards + outro[:1]


def _source_headline(card: dict) -> str:
    source = card.get("source") or {}
    return str(source.get("display_headline_ja") or "").strip()


def _rewrite_headline(card: dict, frame: str, rng: random.Random) -> None:
    card_type = str(card.get("card_type") or "")
    if card_type == "brand_outro":
        return
    if card_type == "news_context":
        source_headline = _source_headline(card)
        # When a proper localized source headline exists, news-first families should
        # actually surface the news rather than another generic market slogan.
        if source_headline and frame in {"news_decode", "question"}:
            card["headline"] = source_headline
            return
    options = (HEADLINE_BANK.get(card_type) or {}).get(frame) or []
    if options:
        card["headline"] = rng.choice(options)


def _apply_format_metadata(card: dict, family: str, frame: str, position: int) -> None:
    card["editorial_format"] = {
        "family": family,
        "frame": frame,
        "body_mode": BODY_MODE.get(frame, "fact_then_interpretation"),
        "story_position": position,
        "purpose": "briefing-specific editorial narrative; do not reuse a fixed card sequence",
    }
    direction = card.setdefault("visual_direction", {})
    direction["editorial_family"] = family
    direction["editorial_frame"] = frame


def apply_editorial_format_to_package(
    package: dict,
    brief: dict,
    resources: list[dict] | None = None,
    *,
    seed_hex: str | None = None,
    recent: list[str] | None = None,
) -> dict:
    next_package = copy.deepcopy(package or {})
    seed_hex = seed_hex or _fingerprint(brief or {}, resources)
    family = select_editorial_family(seed_hex, recent=recent)
    if recent is None:
        RECENT_EDITORIAL_FAMILIES.append(family)
    rule = EDITORIAL_FAMILIES[family]
    frame = str(rule["frame"])
    rng = random.Random(int(seed_hex[16:32], 16))

    for set_label, cards in (next_package.get("cards") or {}).items():
        arranged = _sort_cards(list(cards or []), list(rule["order"]))
        for index, card in enumerate(arranged, start=1):
            card["slide"] = index
            card["set"] = set_label
            _rewrite_headline(card, frame, rng)
            _apply_format_metadata(card, family, frame, index)
        next_package["cards"][set_label] = arranged

    quality = next_package.setdefault("content_quality", {})
    quality["editorial_blueprint"] = {
        "runtime": EDITORIAL_FORMAT_RUNTIME_VERSION,
        "family": family,
        "frame": frame,
        "order": list(rule["order"]),
        "policy": "new briefing selects a different narrative family; content order and copy framing vary while canonical data and brand outro remain locked",
    }
    return next_package


def apply_reasoning_patch(reasoning_engine) -> None:
    if getattr(reasoning_engine, "_kiyosaki_editorial_format_version", None) == EDITORIAL_FORMAT_RUNTIME_VERSION:
        return
    original = reasoning_engine.generate_content_package

    def generate_content_package(brief: dict, resources: list[dict], custom_card_count: int, config: dict, output_locale: str):
        package = original(brief, resources, custom_card_count, config, output_locale)
        return apply_editorial_format_to_package(package, brief, resources)

    reasoning_engine.generate_content_package = generate_content_package
    reasoning_engine._kiyosaki_editorial_format_version = EDITORIAL_FORMAT_RUNTIME_VERSION
