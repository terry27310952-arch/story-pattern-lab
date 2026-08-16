from __future__ import annotations

import hashlib
import re
import time

import story_article_cleaner
import story_content_pipeline_v3 as legacy
import story_source_engine_v5 as source_engine
import story_graph_engine
import story_renderer_v5 as story_renderer


STORY_CONTENT_PIPELINE_VERSION = "story-content-v10.3"
DISPLAY_BRAND_LABEL = legacy.DISPLAY_BRAND_LABEL
PROVIDER_LOCAL = legacy.PROVIDER_LOCAL
PROVIDER_OLLAMA = legacy.PROVIDER_OLLAMA
PROVIDER_OPENAI_COMPATIBLE = legacy.PROVIDER_OPENAI_COMPATIBLE
StoryGenerationResult = legacy.StoryGenerationResult

_LAYOUTS = ["full_bleed_bottom", "split_left", "top_caption", "poster_center", "newspaper_panel", "data_monument", "split_top"]
_ROLE_HEADLINES = {
    "context": "まず、事実関係を固定する",
    "actor": "この話の中心は誰か",
    "before": "これまでの前提",
    "change": "何が変わったのか",
    "deal": "動いた条件を見る",
    "scale": "数字で規模を確認する",
    "cause": "なぜ今なのか",
    "contrast": "同時に見える二つの事実",
    "evidence": "根拠を一つに絞る",
    "impact": "この変化が意味すること",
    "timeline": "時間軸で確認する",
    "watch": "次に確認する節目",
}


def _clean(value: object, limit: int = 900) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _sid(row: dict) -> str:
    return str(row.get("id") or row.get("source_id") or row.get("url") or "")


def _hero_resources(resources: list[dict], hero: dict) -> list[dict]:
    allowed = {str(v) for v in hero.get("resource_ids") or [] if v}
    return [dict(row) for row in resources or [] if _sid(row) in allowed]


def _prepare(resources: list[dict]) -> list[dict]:
    return [story_article_cleaner.clean_story_resource(dict(row)) for row in resources or [] if isinstance(row, dict)]


def _candidate_ja_ratio(candidate: dict) -> float:
    row = candidate.get("hero_resource") or {}
    return source_engine.japanese_ratio(f"{row.get('title','')} {row.get('material') or row.get('excerpt') or ''}")


def _select_hero(source_context: dict, config: dict, output_locale: str) -> tuple[dict, str]:
    candidates = [dict(c) for c in source_context.get("candidates") or []]
    if not candidates:
        return {}, "no_candidates"
    provider = str(config.get("provider") or PROVIDER_LOCAL)
    if output_locale == "ja-JP" and provider == PROVIDER_LOCAL:
        japanese = [c for c in candidates if _candidate_ja_ratio(c) >= 0.28]
        if japanese:
            return japanese[0], "local_provider_prefers_japanese_evidence"
        return {}, "local_provider_has_no_japanese_evidence"
    return candidates[0], "top_hero_with_model_translation_allowed"


def _fact_map(graph: dict) -> dict[str, dict]:
    return {str(f.get("id")): dict(f) for f in graph.get("facts") or [] if f.get("id")}


def _card_facts(graph: dict, plan_item: dict) -> list[dict]:
    fmap = _fact_map(graph)
    return [fmap[fid] for fid in [str(v) for v in plan_item.get("fact_ids") or []] if fid in fmap]


def _fact_pack(graph: dict) -> dict:
    facts = []
    years: list[str] = []
    values: list[str] = []
    for fact in graph.get("facts") or []:
        vals = [str(v) for v in fact.get("values") or [] if v]
        yrs = [str(v) for v in fact.get("years") or [] if v]
        for value in vals:
            if value not in values:
                values.append(value)
        for year in yrs:
            if year not in years:
                years.append(year)
        facts.append({
            "fact_type": fact.get("relation"),
            "text": fact.get("sentence"),
            "source_id": fact.get("source_id"),
            "value": vals[0] if vals else "",
            "values": vals,
            "value_details": fact.get("value_details") or [],
            "source_sentence": fact.get("sentence"),
            "confidence": fact.get("score"),
            "complete": fact.get("complete", True),
        })
    return {
        "source_ids": list(graph.get("source_ids") or []),
        "facts": facts,
        "years": years,
        "values": values,
        "entities": list(graph.get("entities") or []),
        "cleaner": story_article_cleaner.STORY_ARTICLE_CLEANER_VERSION,
        "graph": story_graph_engine.STORY_GRAPH_ENGINE_VERSION,
    }


def _numeric_tokens(text: str) -> set[str]:
    value = str(text or "")
    tokens: set[str] = set()
    for year in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", value):
        tokens.add(f"year:{year}")
    for symbol, number in re.findall(r"([$¥￥])\s*(\d[\d,.]*(?:\.\d+)?)", value):
        currency = "usd" if symbol == "$" else "jpy"
        tokens.add(f"money:{number.replace(',', '').rstrip('.') }:{currency}")
    for number, unit in re.findall(r"(\d[\d,.]*(?:\.\d+)?)\s*(MW|GW|メガワット|ギガワット)", value, flags=re.I):
        canonical_unit = "mw" if unit.casefold() in {"mw", "メガワット"} else "gw"
        tokens.add(f"capacity:{number.replace(',', '').rstrip('.') }:{canonical_unit}")
    for number in re.findall(r"(\d+(?:\.\d+)?)\s*%", value):
        tokens.add(f"percent:{number}")
    for number, unit in re.findall(
        r"(\d[\d,.]*(?:\.\d+)?)\s*(兆円|億円|万円|円|兆ドル|億ドル|万ドル|ドル|USD|JPY|billion|million|trillion|bn|mn)",
        value,
        flags=re.I,
    ):
        normalized = unit.casefold()
        currency = "jpy" if normalized in {"兆円", "億円", "万円", "円", "jpy"} else "usd"
        tokens.add(f"money:{number.replace(',', '').rstrip('.') }:{normalized}:{currency}")
    for number, unit in re.findall(r"(?<!\d)(\d{1,3})\s*(年間|年|years?|months?|か月|ヶ月)(?!\d)", value, flags=re.I):
        normalized_unit = unit.casefold()
        normalized_unit = "years" if normalized_unit in {"年", "年間", "year", "years"} else "months"
        tokens.add(f"duration:{number}:{normalized_unit}")
    return tokens


def _claim_ok(headline: str, body: str, evidence: str) -> bool:
    claims = _numeric_tokens(f"{headline} {body}")
    if not claims:
        return True
    supported = _numeric_tokens(evidence)
    missing = set()
    for claim in claims:
        if claim in supported:
            continue
        if claim.startswith("money:"):
            parts = claim.split(":")
            amount = parts[1] if len(parts) > 1 else ""
            currency = parts[-1] if len(parts) > 2 else ""
            if any(s.startswith(f"money:{amount}:") and s.endswith(currency) for s in supported):
                continue
        missing.add(claim)
    return not missing


def _japanese_ratio(text: str) -> float:
    return source_engine.japanese_ratio(text)


def _evidence_text(facts: list[dict]) -> str:
    chunks: list[str] = []
    for fact in facts:
        sentence = _clean(fact.get("sentence"), 650)
        if sentence and sentence not in chunks:
            chunks.append(sentence)
    return _clean(" ".join(chunks), 1100)


def _subject(plan: dict, hero: dict) -> str:
    return _clean(plan.get("subject") or next(iter(hero.get("entities") or []), ""), 100)


def _scale_values(facts: list[dict]) -> list[str]:
    out: list[str] = []
    for fact in facts:
        for detail in fact.get("value_details") or []:
            if detail.get("kind") in {"money", "capacity", "percent", "quantity", "price", "valuation"}:
                raw = str(detail.get("raw") or "")
                if raw and raw not in out:
                    out.append(raw)
    return out


def _fallback_copy(role: str, facts: list[dict], plan: dict, hero: dict) -> tuple[str, str]:
    evidence = _evidence_text(facts)
    subject = _subject(plan, hero)
    years = list(dict.fromkeys(str(y) for fact in facts for y in fact.get("years") or []))
    scale_values = _scale_values(facts)

    if role == "hook":
        headline = _clean(plan.get("headline_ja") or hero.get("headline_ja") or "今日の主役を一つに絞る", 90)
        return headline, evidence
    if role == "scale" and scale_values:
        return "数字で見ると、" + "・".join(scale_values[:3]), evidence
    if role in {"timeline", "watch"} and years:
        return "次の節目は" + "・".join(years[:3]) + "年", evidence
    if role == "before" and subject:
        return f"{subject}のこれまで", evidence
    if role in {"change", "deal"} and subject:
        return f"{subject}で変わったこと", evidence
    return _ROLE_HEADLINES.get(role, "確認できる事実"), evidence


def _model_cards(config: dict, hero: dict, plan: dict, graph: dict) -> tuple[dict[str, dict], str | None]:
    roles = [str(item.get("role")) for item in plan.get("cards") or []]
    model_raw, warning = legacy._call_model(config, hero, roles, _fact_pack(graph))
    by_role: dict[str, dict] = {}
    if isinstance(model_raw, dict):
        for item in model_raw.get("cards") or []:
            if isinstance(item, dict) and str(item.get("role")) in roles:
                by_role[str(item.get("role"))] = item
    return by_role, warning


def _layout(seed: str, index: int, used: set[str]) -> str:
    start = int(hashlib.sha1(f"{seed}:{index}".encode()).hexdigest()[:8], 16) % len(_LAYOUTS)
    for offset in range(len(_LAYOUTS)):
        candidate = _LAYOUTS[(start + offset) % len(_LAYOUTS)]
        if candidate not in used:
            used.add(candidate)
            return candidate
    return _LAYOUTS[start]


def _scene_prompt(scene_type: str, role: str, plan: dict, hero: dict, evidence: str, layout: str) -> str:
    subject = _subject(plan, hero) or "financial subject"
    return (
        "Premium Japanese documentary editorial image for a financial story. "
        f"Subject: {subject}. Story role: {role}. Scene semantics: {scene_type}. Evidence context: {_clean(evidence, 420)}. "
        f"Composition: {layout}. The scene must literally match the evidence semantics. Do not infer electricity from phrases like purchasing power. "
        "Use a real-world documentary subject when an image provider is available. No recurring market-chart wallpaper. "
        "No text inside the generated image, no captions, no glyphs, no K monogram, no orange K symbol, no decorative logo, no watermark, no floating coins."
    )


def _source_display(row: dict | None) -> dict:
    row = row or {}
    return {
        "source_id": _sid(row),
        "publisher": _clean(row.get("source"), 80),
        "short_title": _clean(row.get("title"), 140),
        "url": _clean(row.get("url"), 600),
        "source_quality": {"story_score": row.get("story_score"), "risk_score": row.get("risk_score")},
    }


def _outro(total: int, tag: str, brand: dict | None) -> dict:
    return legacy._outro(total, tag, brand)


def generate_story_package(
    resources: list[dict],
    total_card_count: int,
    config: dict,
    output_locale: str = "ja-JP",
    brand: dict | None = None,
    generation_seed: str | None = None,
) -> StoryGenerationResult:
    if output_locale != "ja-JP":
        return StoryGenerationResult({}, error="Storytelling mode requires ja-JP output.")

    prepared = _prepare(resources)
    ranked = source_engine.annotate_resources(prepared)
    if not ranked:
        return StoryGenerationResult({}, error="No story resources are available.")

    source_context = source_engine.story_context(ranked)
    hero, hero_selection_reason = _select_hero(source_context, config, output_locale)
    if not hero:
        return StoryGenerationResult(
            {},
            error="Japanese Story generation blocked: local deterministic mode needs Japanese source evidence. Use an external reasoning model for non-Japanese Hero sources.",
        )

    source_context["hero_story"] = hero
    source_context["hero_selection_reason"] = hero_selection_reason
    hero_rows = _hero_resources(ranked, hero)
    if not hero_rows:
        return StoryGenerationResult({}, error="Hero Story has no isolated source resources.")

    hero_resource = dict(hero.get("hero_resource") or hero_rows[0])
    cluster_scores: dict[str, float] = {}
    cluster_ok = True
    for row in hero_rows:
        score = 1.0 if _sid(row) == _sid(hero_resource) else source_engine.event_similarity(hero_resource, row)
        cluster_scores[_sid(row)] = score
        if score < 0.47:
            cluster_ok = False
    if not cluster_ok:
        return StoryGenerationResult({}, error="Hero Story cluster contains resources from different events.")

    graph = story_graph_engine.extract_fact_graph(hero, hero_rows)
    total_card_count = max(5, min(9, int(total_card_count or 7)))
    plan = story_graph_engine.build_story_plan(hero, graph, total_card_count - 1)
    if plan.get("error") or not plan.get("cards"):
        return StoryGenerationResult({}, error=str(plan.get("error") or "Story plan could not be built from evidence."))

    hero["archetype"] = plan.get("archetype_tag")
    hero["headline_ja"] = plan.get("headline_ja")
    hero["story_plan_version"] = plan.get("version")

    seed = generation_seed or hashlib.sha1(f"{hero.get('id')}|{time.time_ns()}".encode()).hexdigest()[:16]
    model_by_role, model_warning = _model_cards(config, hero, plan, graph)
    source_map = {_sid(row): row for row in hero_rows}
    hero_ids = {str(v) for v in hero.get("resource_ids") or [] if v}
    used_layouts: set[str] = set()
    cards: list[dict] = []
    plan_fact_ids = set(str(v) for v in plan.get("fact_ids") or [])

    for index, item in enumerate(plan.get("cards") or []):
        role = str(item.get("role") or "evidence")
        facts = _card_facts(graph, item)
        if not facts:
            continue
        evidence = _evidence_text(facts)
        headline, body = _fallback_copy(role, facts, plan, hero)

        model_card = model_by_role.get(role) or {}
        mh = _clean(model_card.get("headline"), 90)
        mb = _clean(model_card.get("body"), 300)
        if mh and mb and _japanese_ratio(mh + mb) >= 0.45 and _claim_ok(mh, mb, evidence):
            headline, body = mh, mb

        claim_ok = _claim_ok(headline, body, evidence)
        if not claim_ok:
            headline, body = _fallback_copy(role, facts, plan, hero)
            claim_ok = _claim_ok(headline, body, evidence)

        fact_source_ids = list(dict.fromkeys(str(f.get("source_id") or "") for f in facts if f.get("source_id")))
        evidence_ref = fact_source_ids[0] if fact_source_ids else next(iter(hero_ids), "")
        layout = _layout(seed, index, used_layouts)
        scene_type = str(item.get("scene_type") or "documentary_editorial")
        scene_ok = story_graph_engine.scene_matches_evidence(scene_type, role, facts)
        evidence_complete = all(bool(f.get("complete", True)) and story_article_cleaner.sentence_complete(str(f.get("sentence") or "")) for f in facts)
        prompt = _scene_prompt(scene_type, role, plan, hero, evidence, layout)

        cards.append({
            "set": "STORY",
            "slide": len(cards) + 1,
            "card_id": f"story-{hero.get('id')}-{len(cards)+1}",
            "card_type": "story_editorial",
            "story_id": hero.get("id"),
            "story_role": role,
            "story_archetype": plan.get("archetype_tag"),
            "eyebrow": role.upper(),
            "headline": headline,
            "subheadline": body,
            "key_message": body,
            "metrics": [],
            "evidence_refs": fact_source_ids,
            "evidence_excerpt": evidence,
            "evidence_score": round(max(float(f.get("score") or 0) for f in facts), 2),
            "source": _source_display(source_map.get(evidence_ref)),
            "footer": "",
            "visual_direction": {
                "deck_family": "story_graph",
                "format_variant": layout,
                "layout_variant": layout,
                "scene_type": scene_type,
                "story_role": role,
                "story_archetype": plan.get("archetype_tag"),
                "character_required": False,
                "character_visibility": 0.0,
                "character_shot": "none",
                "character_pose": "none",
                "story_scene_prompt": prompt,
                "brand_mark_policy": "text-only キヨサキ; no K monogram/icon",
                "image_prompts": {"4:5": prompt + " 4:5 vertical, 1080x1350.", "9:16": prompt + " 9:16 vertical, 1080x1920."},
            },
            "qa": {
                "renderable": True,
                "mode": "story",
                "fact_bound": True,
                "claim_evidence_consistent": claim_ok,
                "story_plan_fact_ids_valid": all(str(fid) in plan_fact_ids for fid in item.get("fact_ids") or []),
                "event_ref_score": min((cluster_scores.get(ref, 0.0) for ref in fact_source_ids), default=0.0),
                "evidence_sentence_complete": evidence_complete,
                "scene_evidence_consistent": scene_ok,
            },
        })

    if len(cards) < total_card_count - 1:
        return StoryGenerationResult({}, error="Evidence was too thin to build the requested Story card count without filler.")

    cards = cards[: total_card_count - 1]
    content_cards = cards
    refs_ok = all(set(c.get("evidence_refs") or []).issubset(hero_ids) for c in content_cards)
    graph_sources_ok = set(graph.get("source_ids") or []).issubset(hero_ids)
    claims_ok = all(bool((c.get("qa") or {}).get("claim_evidence_consistent")) for c in content_cards)
    plan_ids_ok = all(bool((c.get("qa") or {}).get("story_plan_fact_ids_valid")) for c in content_cards)
    evidence_complete_ok = all(bool((c.get("qa") or {}).get("evidence_sentence_complete")) for c in content_cards)
    scene_evidence_ok = all(bool((c.get("qa") or {}).get("scene_evidence_consistent")) for c in content_cards)
    japanese_ok = all(_japanese_ratio(f"{c.get('headline','')} {c.get('key_message','')}") >= 0.35 for c in content_cards)
    cleaner_ok = not any(story_article_cleaner.has_boilerplate(str(row.get("material") or "")) for row in hero_rows)
    social_embed_free = cleaner_ok and not any(re.search(r"https?://(?:t\.co|twitter\.com|x\.com|pic\.twitter\.com)/", str(row.get("material") or ""), flags=re.I) for row in hero_rows)

    if not japanese_ok:
        return StoryGenerationResult(
            {},
            error="Japanese Story generation blocked: final card copy did not meet the ja-JP language gate. No publishable package was created.",
            model_warning=model_warning,
        )

    cards.append(_outro(total_card_count, str(plan.get("archetype_tag") or "story_event"), brand))
    unique_layouts = len({(c.get("visual_direction") or {}).get("layout_variant") for c in content_cards})
    unique_scenes = len({(c.get("visual_direction") or {}).get("scene_type") for c in content_cards})
    visual_diag = story_renderer.scene_diagnostics(content_cards)
    visual_ok = (
        unique_scenes >= min(4, len(content_cards))
        and int(visual_diag.get("render_signature_count") or 0) >= min(4, len(content_cards))
        and not visual_diag.get("near_duplicate_scene_pairs")
    )

    failures: list[str] = []
    if not refs_ok or not graph_sources_ok:
        failures.append("hero_evidence_isolation")
    if not claims_ok:
        failures.append("claim_evidence_mismatch")
    if not plan_ids_ok:
        failures.append("story_plan_fact_mismatch")
    if not cleaner_ok or not social_embed_free:
        failures.append("article_boilerplate_contamination")
    if not evidence_complete_ok:
        failures.append("incomplete_evidence")
    if not scene_evidence_ok:
        failures.append("scene_evidence_mismatch")
    if unique_layouts < min(4, len(content_cards)):
        failures.append("layout_repetition")
    if not visual_ok:
        failures.append("visual_scene_repetition")

    publishable = not failures
    for card in cards:
        card.setdefault("qa", {})["story_publishable"] = publishable

    story_qa = {
        "hero_evidence_isolated": refs_ok and graph_sources_ok,
        "hero_cluster_same_event": cluster_ok,
        "claim_evidence_consistent": claims_ok,
        "story_plan_fact_binding": plan_ids_ok,
        "article_cleaner_pass": cleaner_ok,
        "social_embed_free": social_embed_free,
        "evidence_sentence_complete": evidence_complete_ok,
        "scene_evidence_consistent": scene_evidence_ok,
        "japanese_copy_pass": japanese_ok,
        "unique_layouts": unique_layouts,
        "unique_scene_types": unique_scenes,
        "render_signature_count": visual_diag.get("render_signature_count"),
        "max_scene_similarity": visual_diag.get("max_scene_similarity"),
        "near_duplicate_scene_pairs": visual_diag.get("near_duplicate_scene_pairs"),
        "publishable": publishable,
        "blocking_reasons": failures,
    }

    context = dict(source_context)
    context["hero_story"] = hero
    context["hero_resource_ids"] = sorted(hero_ids)
    context["cluster_event_scores"] = cluster_scores
    context["fact_graph"] = graph
    context["story_plan"] = plan
    context["evidence_facts"] = _fact_pack(graph)

    note_lines = [f"# {plan.get('headline_ja')}", "", _clean(plan.get("thesis"), 400), ""]
    for card in content_cards:
        note_lines.extend([f"## {card['slide']}. {card['headline']}", card.get("key_message") or "", ""])

    package = {
        "mode": "story",
        "story_context": context,
        "cards": {"STORY": cards},
        "note_markdown": "\n".join(note_lines).strip(),
        "content_quality": {
            "mode": "story",
            "pipeline": STORY_CONTENT_PIPELINE_VERSION,
            "source_engine": source_engine.STORY_ENGINE_VERSION,
            "graph_engine": story_graph_engine.STORY_GRAPH_ENGINE_VERSION,
            "renderer": story_renderer.STORY_RENDERER_VERSION,
            "generation_seed": seed,
            "hero_story_title": plan.get("headline_ja"),
            "story_archetype": plan.get("archetype_tag"),
            "story_score": hero.get("story_score"),
            "hero_story_score": hero.get("hero_story_score"),
            "hero_selection_reason": hero_selection_reason,
            "model_provider": config.get("provider") or PROVIDER_LOCAL,
            "model_used": bool(model_by_role),
            "story_qa": story_qa,
            "policy": "locale-aware hero -> typed Fact Graph -> dynamic Story Plan -> evidence-bound ja-JP copy -> semantic scene/evidence QA",
        },
    }
    return StoryGenerationResult(package=package, model_warning=model_warning)
