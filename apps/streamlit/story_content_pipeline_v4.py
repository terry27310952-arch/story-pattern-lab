from __future__ import annotations

import hashlib
import re
import time

import story_content_pipeline_v3 as legacy
import story_engine_v4 as story_engine
import story_renderer_v4 as story_renderer


STORY_CONTENT_PIPELINE_VERSION = "story-content-v9.0"
DISPLAY_BRAND_LABEL = legacy.DISPLAY_BRAND_LABEL
PROVIDER_LOCAL = legacy.PROVIDER_LOCAL
PROVIDER_OLLAMA = legacy.PROVIDER_OLLAMA
PROVIDER_OPENAI_COMPATIBLE = legacy.PROVIDER_OPENAI_COMPATIBLE
StoryGenerationResult = legacy.StoryGenerationResult


def _clean(value: object, limit: int = 800) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _sid(row: dict) -> str:
    return str(row.get("id") or row.get("source_id") or row.get("url") or "")


def _hero_resources(resources: list[dict], hero: dict) -> list[dict]:
    allowed = {str(v) for v in hero.get("resource_ids") or [] if v}
    return [dict(row) for row in resources or [] if _sid(row) in allowed]


def _best_fact(pack: dict, preferred: dict | None, role: str) -> dict | None:
    if preferred and preferred.get("source_id"):
        return preferred
    facts = list(pack.get("facts") or [])
    role_preferences = {
        "hook": ["deal_value", "event", "after_state", "historical_value", "fund_flow"],
        "old_business": ["before_state", "event"],
        "turning_point": ["capacity", "after_state", "event"],
        "new_business": ["after_state", "deal_value", "event"],
        "deal_scale": ["deal_value", "capacity", "duration", "numeric_fact"],
        "why_now": ["after_state", "capacity", "fund_flow", "event"],
        "market_implication": ["capacity", "deal_value", "fund_flow", "event"],
        "watch": ["date", "capacity", "duration", "policy_date", "numeric_fact"],
        "then": ["historical_value", "date", "numeric_fact"],
        "what_happened": ["historical_value", "event"],
        "now": ["historical_value", "numeric_fact", "event"],
        "similarity": ["historical_value", "numeric_fact"],
        "difference": ["event", "historical_value"],
        "flow_source": ["fund_flow", "event"],
        "flow_size": ["fund_flow", "numeric_fact"],
        "where_it_goes": ["fund_flow", "event"],
        "price_gap": ["fund_flow", "numeric_fact", "event"],
    }
    preferred_types = role_preferences.get(role, [])
    for kind in preferred_types:
        for fact in facts:
            if fact.get("fact_type") == kind and fact.get("source_id"):
                return fact
    for fact in facts:
        if fact.get("source_id") and float(fact.get("confidence") or 0) >= 0.88:
            return fact
    return facts[0] if facts else None


def _specific_anchor(text: str, hero: dict, pack: dict) -> bool:
    if re.search(r"\d", text or ""):
        return True
    for entity in hero.get("entities") or []:
        if entity and entity.casefold() in (text or "").casefold():
            return True
    values = [str(v) for v in pack.get("values") or [] if v]
    return any(value in (text or "") for value in values)


def _ensure_specific_copy(headline: str, body: str, hero: dict, fact: dict | None, pack: dict) -> tuple[str, str]:
    combined = f"{headline} {body}"
    if _specific_anchor(combined, hero, pack):
        return headline, body
    subject = next((e for e in hero.get("entities") or [] if e), "")
    if subject:
        body = f"{body} {subject}の今回の動きを基準に確認する。"
    elif fact and fact.get("value"):
        body = f"{body} 確認できる数値は{fact['value']}。"
    return headline, body


def _model_specific(text: str, hero: dict, pack: dict) -> bool:
    return _specific_anchor(text, hero, pack) and legacy._model_numeric_safe(text, pack)


def _cluster_ref_coherence(hero: dict, hero_rows: list[dict]) -> tuple[bool, dict[str, float]]:
    hero_resource = dict(hero.get("hero_resource") or {})
    if not hero_resource and hero_rows:
        hero_resource = hero_rows[0]
    scores: dict[str, float] = {}
    ok = True
    for row in hero_rows:
        sid = _sid(row)
        if sid == _sid(hero_resource):
            score = 1.0
        else:
            score = story_engine.event_similarity(hero_resource, row)
        scores[sid] = score
        if score < 0.47:
            ok = False
    return ok, scores


def _source_specific_card(card: dict, hero: dict, pack: dict) -> bool:
    evidence = _clean(card.get("evidence_excerpt"), 500)
    text = f"{card.get('headline','')} {card.get('key_message','')}"
    return bool(evidence and (card.get("qa") or {}).get("fact_bound") and _specific_anchor(text, hero, pack))


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

    ranked = story_engine.annotate_resources([dict(r) for r in resources or []])
    if not ranked:
        return StoryGenerationResult({}, error="No story resources are available.")

    context = story_engine.story_context(ranked)
    hero = dict(context.get("hero_story") or {})
    hero_rows = _hero_resources(ranked, hero)
    if not hero_rows:
        return StoryGenerationResult({}, error="Hero Story has no isolated source resources.")

    cluster_ok, cluster_scores = _cluster_ref_coherence(hero, hero_rows)
    if not cluster_ok:
        return StoryGenerationResult({}, error="Hero Story cluster contains resources from different events.")

    pack = legacy.extract_fact_pack(hero, hero_rows)
    hero_ids = {str(v) for v in hero.get("resource_ids") or [] if v}
    if not set(pack.get("source_ids") or []).issubset(hero_ids):
        return StoryGenerationResult({}, error="Hero evidence isolation failed before generation.")

    total_card_count = max(5, min(9, int(total_card_count or 7)))
    roles = story_engine.story_arc(str(hero.get("archetype") or "hidden_giant"), total_card_count - 1)
    seed = generation_seed or hashlib.sha1(f"{hero.get('id')}|{time.time_ns()}".encode()).hexdigest()[:16]
    model_raw, model_warning = legacy._call_model(config, hero, roles, pack)
    model_by_role: dict[str, dict] = {}
    if isinstance(model_raw, dict):
        for item in model_raw.get("cards") or []:
            if isinstance(item, dict) and item.get("role") in roles:
                model_by_role[str(item["role"])] = item

    source_map = {_sid(r): r for r in hero_rows}
    cards: list[dict] = []
    used_layouts: dict[str, int] = {}
    previous_layout = ""

    for index, role in enumerate(roles):
        headline, body, preferred_fact = legacy._jp_specific_copy(str(hero.get("archetype")), role, hero, pack)
        fact = _best_fact(pack, preferred_fact, role)
        headline, body = _ensure_specific_copy(headline, body, hero, fact, pack)

        model_card = model_by_role.get(role) or {}
        mh = _clean(model_card.get("headline"), 90)
        mb = _clean(model_card.get("body"), 220)
        if mh and mb and not re.search(r"[가-힣]", mh + mb) and _model_specific(mh + " " + mb, hero, pack):
            headline, body = mh, mb

        evidence_ref = str((fact or {}).get("source_id") or "")
        if not evidence_ref or evidence_ref not in hero_ids:
            evidence_ref = next(iter(hero_ids))
            if fact:
                fact = dict(fact)
                fact["source_id"] = evidence_ref
        evidence_excerpt = _clean((fact or {}).get("source_sentence") or (fact or {}).get("text"), 360)

        layout = story_engine.layout_for_story(str(hero.get("archetype")), index, f"{seed}:{role}")
        candidates = list(story_engine.ARCHETYPE_LAYOUTS.get(str(hero.get("archetype"))) or [])
        if layout == previous_layout or used_layouts.get(layout, 0) >= 1:
            for alt in candidates:
                if alt != previous_layout and used_layouts.get(alt, 0) == 0:
                    layout = alt
                    break
        previous_layout = layout
        used_layouts[layout] = used_layouts.get(layout, 0) + 1

        scene_type = legacy._scene_type(str(hero.get("archetype")), role)
        prompt = legacy._scene_prompt(str(hero.get("archetype")), role, hero, layout, scene_type, evidence_excerpt)
        cards.append({
            "set": "STORY",
            "slide": index + 1,
            "card_id": f"story-{hero.get('id')}-{index+1}",
            "card_type": "story_editorial",
            "story_id": hero.get("id"),
            "story_role": role,
            "story_archetype": hero.get("archetype"),
            "eyebrow": str(hero.get("archetype") or "STORY").replace("_", " ").upper(),
            "headline": headline,
            "subheadline": body,
            "key_message": body,
            "metrics": [],
            "evidence_refs": [evidence_ref],
            "evidence_excerpt": evidence_excerpt,
            "evidence_score": round(float((fact or {}).get("confidence") or 0.0), 2),
            "source": legacy._source_display(source_map.get(evidence_ref)),
            "footer": "",
            "visual_direction": {
                "deck_family": f"story_{hero.get('archetype')}",
                "format_variant": layout,
                "layout_variant": layout,
                "scene_type": scene_type,
                "story_role": role,
                "story_archetype": hero.get("archetype"),
                "character_required": False,
                "character_visibility": 0.0,
                "character_shot": "none",
                "character_pose": "none",
                "visual_focus": ", ".join(hero.get("visual_motifs") or []),
                "story_scene_prompt": prompt,
                "brand_mark_policy": "text-only キヨサキ; no K monogram/icon",
                "image_prompts": {
                    "4:5": prompt + " 4:5 vertical, 1080x1350.",
                    "9:16": prompt + " 9:16 vertical, 1080x1920.",
                },
            },
            "qa": {
                "renderable": True,
                "mode": "story",
                "fact_bound": bool(fact and evidence_excerpt),
                "event_ref_score": cluster_scores.get(evidence_ref, 1.0),
            },
        })

    cards.append(legacy._outro(total_card_count, str(hero.get("archetype")), brand))
    content_cards = cards[:-1]

    generic_count = sum(1 for card in content_cards if not _source_specific_card(card, hero, pack))
    unique_layouts = len({(c.get("visual_direction") or {}).get("layout_variant") for c in content_cards})
    unique_scene_types = len({(c.get("visual_direction") or {}).get("scene_type") for c in content_cards})
    refs_ok = all(set(c.get("evidence_refs") or []).issubset(hero_ids) for c in content_cards)
    evidence_bound = all((c.get("qa") or {}).get("fact_bound") for c in content_cards)
    leaks = sum(1 for c in cards if re.search(r"[가-힣]", " ".join(str(c.get(k) or "") for k in ["headline", "subheadline", "key_message"])))
    entity_details = list(hero.get("entity_details") or [])
    entity_pass = bool(entity_details) and all(
        float(e.get("confidence") or 0) >= 0.72
        and str(e.get("name") or "").casefold() not in {"crypto", "crypto.", "editor", "updated", "that", "what", "million", "back"}
        for e in entity_details
    )
    cluster_coherence = float(hero.get("cluster_coherence") or (1.0 if len(hero_rows) == 1 else 0.0))
    cluster_pass = cluster_ok and cluster_coherence >= 0.47

    visual_diag = story_renderer.scene_diagnostics(content_cards)
    render_signature_count = int(visual_diag.get("render_signature_count") or 0)
    near_duplicates = list(visual_diag.get("near_duplicate_scene_pairs") or [])
    max_scene_similarity = float(visual_diag.get("max_scene_similarity") or 0.0)
    visual_pass = (
        unique_scene_types >= min(4, len(content_cards))
        and render_signature_count >= min(4, len(content_cards))
        and not near_duplicates
    )

    failures = []
    if not refs_ok:
        failures.append("evidence_ref_outside_hero_cluster")
    if not cluster_pass:
        failures.append("hero_cluster_not_same_event")
    if not evidence_bound:
        failures.append("unbound_story_card_evidence")
    if generic_count:
        failures.append("generic_story_copy")
    if leaks:
        failures.append("foreign_language_leak")
    if unique_layouts < min(4, len(content_cards)):
        failures.append("layout_repetition")
    if not visual_pass:
        failures.append("visual_scene_repetition")
    if not entity_pass:
        failures.append("entity_quality")

    publishable = not failures
    story_qa = {
        "hero_evidence_isolated": refs_ok and set(pack.get("source_ids") or []).issubset(hero_ids),
        "hero_cluster_same_event": cluster_pass,
        "cluster_coherence": round(cluster_coherence, 4),
        "cluster_event_scores": cluster_scores,
        "specific_fact_cards": f"{len(content_cards)-generic_count}/{len(content_cards)}",
        "fact_bound_cards": sum(1 for c in content_cards if (c.get("qa") or {}).get("fact_bound")),
        "unique_layouts": unique_layouts,
        "unique_scene_types": unique_scene_types,
        "render_signature_count": render_signature_count,
        "max_scene_similarity": round(max_scene_similarity, 4),
        "near_duplicate_scene_pairs": near_duplicates,
        "generic_card_count": generic_count,
        "foreign_language_leaks": leaks,
        "entity_confidence_pass": entity_pass,
        "publishable": publishable,
        "blocking_reasons": failures,
    }

    for card in cards:
        card.setdefault("qa", {})["story_publishable"] = publishable

    context = dict(context)
    context["hero_story"] = hero
    context["evidence_facts"] = pack
    context["hero_resource_ids"] = sorted(hero_ids)
    context["cluster_event_scores"] = cluster_scores

    note_lines = [f"# {hero.get('headline_ja')}", "", hero.get("why_now_ja") or "", ""]
    for c in content_cards:
        note_lines.extend([f"## {c['slide']}. {c['headline']}", c.get("key_message") or "", ""])

    package = {
        "mode": "story",
        "story_context": context,
        "cards": {"STORY": cards},
        "note_markdown": "\n".join(note_lines).strip(),
        "content_quality": {
            "mode": "story",
            "pipeline": STORY_CONTENT_PIPELINE_VERSION,
            "engine": story_engine.STORY_ENGINE_VERSION,
            "renderer": story_renderer.STORY_RENDERER_VERSION,
            "generation_seed": seed,
            "hero_story_title": hero.get("headline_ja"),
            "story_archetype": hero.get("archetype"),
            "story_score": hero.get("story_score"),
            "hero_story_score": hero.get("hero_story_score"),
            "model_provider": config.get("provider") or PROVIDER_LOCAL,
            "model_used": bool(model_raw),
            "story_qa": story_qa,
            "policy": "same-event cluster -> hero-only typed facts -> fact-bound cards -> scene-specific renderer -> pixel-level QA",
        },
    }
    return StoryGenerationResult(package=package, model_warning=model_warning)
