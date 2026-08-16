from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

import story_llm_runtime


STORY_HOOK_ENGINE_VERSION = "story-hook-v1.1"
PROVIDER_LOCAL = "local"
PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"

_BANNED = (
    "まず", "確認する", "確認できる", "今日の主役", "次に見る", "ポイント", "事実関係",
    "見ていく", "注目する", "解説する",
)


def _clean(value: object, limit: int = 180) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _jp_ratio(text: str) -> float:
    value = str(text or "")
    letters = re.findall(r"[A-Za-zぁ-んァ-ヶ一-龥]", value)
    if not letters:
        return 0.0
    jp = re.findall(r"[ぁ-んァ-ヶ一-龥]", value)
    return len(jp) / len(letters)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z0-9])(?:[$¥￥]\s*)?\d[\d,.]*(?:\.\d+)?(?:\s*(?:%|MW|GW|億円|兆円|万円|円|億ドル|兆ドル|万ドル|ドル|USD|JPY|年|年間|か月|ヶ月))?", str(text or ""), flags=re.I))


def _numeric_safe(headline: str, subline: str, evidence: str) -> bool:
    evidence_digits = re.sub(r"[^0-9]", "", evidence)
    for token in _numbers(f"{headline} {subline}"):
        digits = re.sub(r"[^0-9]", "", token)
        if digits and digits not in evidence_digits:
            return False
    return True


def _style_score(headline: str, subline: str) -> float:
    headline = _clean(headline, 100)
    subline = _clean(subline, 100)
    combined = f"{headline} {subline}".strip()
    if not headline or _jp_ratio(combined) < 0.42:
        return 0.0
    score = 50.0
    total = len(headline) + len(subline)
    if 12 <= len(headline) <= 34:
        score += 18
    elif len(headline) <= 46:
        score += 9
    else:
        score -= 18
    if subline:
        score += 8 if len(subline) <= 38 else -8
    if total <= 66:
        score += 8
    if any(term in combined for term in _BANNED):
        score -= 32
    if combined.endswith(("。", "？", "！")):
        score += 2
    if "、" in headline or "。" in headline:
        score += 3
    if re.search(r"[0-9$¥￥]|億|兆|MW|GW", combined):
        score += 5
    if re.search(r"変わ|逆|崩|消え|動|入|止|奪|握|転|追いつ|始ま", combined):
        score += 7
    return max(0.0, min(100.0, score))


def hook_style_pass(headline: str, subline: str) -> bool:
    combined = f"{headline} {subline}".strip()
    return bool(
        headline
        and len(headline) <= 48
        and len(subline) <= 44
        and len(combined) <= 82
        and _jp_ratio(combined) >= 0.40
        and not any(term in combined for term in _BANNED)
    )


def _json_from_text(text: str) -> dict | None:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 90) -> dict:
    req = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _call_hook_model(config: dict, prompt_payload: dict) -> tuple[dict | None, str | None]:
    provider = str(config.get("provider") or PROVIDER_LOCAL)
    if provider == PROVIDER_LOCAL:
        return None, None

    system = (
        "あなたは一流の日本語カルーセル編集者です。第1枚のフックだけを作ってください。"
        "記事タイトルの要約ではなく、事件の最も強い転換・矛盾・規模・意外性を一つだけ選び、指が止まる一行または二行にします。"
        "説明口調は禁止。『まず』『確認する』『今日の主役』『次に見る』『ポイント』は禁止。"
        "提供されたEVIDENCE以外の数字、固有名詞、出来事、因果関係を絶対に追加しないでください。"
        "煽りだけの断定や投資助言は禁止。5案をJSONのみで返してください。"
    )
    user = json.dumps(
        {
            **prompt_payload,
            "constraints": {
                "language": "ja-JP",
                "headline": "12〜34文字推奨、最大48文字",
                "subline": "任意。最大44文字。headlineと合わせて1〜2行",
                "count": 5,
            },
            "schema": {
                "candidates": [
                    {"headline": "日本語", "subline": "日本語または空文字", "angle": "短い理由"}
                ]
            },
        },
        ensure_ascii=False,
    )
    temperature = min(0.95, max(0.68, float(config.get("temperature") or 0.35) + 0.25))

    try:
        if provider == PROVIDER_OLLAMA:
            base = str(config.get("base_url") or story_llm_runtime.DEFAULT_OLLAMA_BASE_URL).rstrip("/")
            model = str(config.get("model") or (story_llm_runtime.DEFAULT_OLLAMA_MODEL if story_llm_runtime.is_cloud_ollama(base) else story_llm_runtime.DEFAULT_LOCAL_OLLAMA_MODEL))
            payload = {
                "model": model,
                "stream": False,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "options": {"temperature": temperature},
            }
            # Ollama Cloud direct API currently does not support structured outputs.
            # The prompt still demands JSON and the parser validates the response.
            if not story_llm_runtime.is_cloud_ollama(base):
                payload["format"] = "json"
            raw = _post_json(
                story_llm_runtime.ollama_api_url(base, "chat"),
                payload,
                story_llm_runtime.ollama_headers(str(config.get("api_key") or "")),
            )
            return _json_from_text(((raw.get("message") or {}).get("content") or "")), None
        if provider == PROVIDER_OPENAI_COMPATIBLE:
            base = str(config.get("base_url") or "").rstrip("/")
            model = str(config.get("model") or "")
            if not base or not model:
                return None, "Hook model configuration is incomplete."
            endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
            key = str(config.get("api_key") or "")
            raw = _post_json(
                endpoint,
                {
                    "model": model,
                    "temperature": temperature,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
                {"Authorization": f"Bearer {key}"} if key else {},
            )
            choices = raw.get("choices") or []
            return _json_from_text((((choices[0] if choices else {}).get("message") or {}).get("content") or "")), None
    except Exception as error:
        return None, f"hook model failed; evidence-bound fallback used: {error}"
    return None, f"Unsupported hook provider: {provider}"


def _fallback(headline_seed: str, evidence: str, subject: str = "") -> tuple[str, str]:
    seed = _clean(headline_seed, 80)
    seed = re.sub(r"(?:ニュース|速報|最新|発表|報道)\s*$", "", seed)
    seed = seed.strip(" 。!?！？")
    if 8 <= len(seed) <= 44 and _jp_ratio(seed) >= 0.35 and not any(term in seed for term in _BANNED):
        return seed, ""

    sentence = _clean(evidence.split("。", 1)[0], 70).strip(" 。!?！？")
    if 8 <= len(sentence) <= 44 and _jp_ratio(sentence) >= 0.35:
        return sentence, ""

    entity = _clean(subject, 20)
    return (f"{entity}で、前提が変わった。" if entity else "前提が、静かに変わった。"), ""


def generate_hook(
    config: dict,
    hero: dict,
    plan: dict,
    facts: list[dict],
    fallback_headline: str,
    fallback_subline: str = "",
) -> dict:
    evidence_chunks: list[str] = []
    for fact in facts:
        sentence = _clean(fact.get("sentence") or fact.get("source_sentence"), 520)
        if sentence and sentence not in evidence_chunks:
            evidence_chunks.append(sentence)
    evidence = " ".join(evidence_chunks)
    entities = [str(v) for v in hero.get("entities") or [] if v][:5]
    values: list[str] = []
    for fact in facts:
        for value in fact.get("values") or []:
            if str(value) not in values:
                values.append(str(value))

    raw, warning = _call_hook_model(
        config,
        {
            "EVENT_TITLE": _clean(hero.get("headline_seed") or hero.get("headline_ja") or fallback_headline, 160),
            "STORY_THESIS": _clean(plan.get("thesis"), 300),
            "ENTITIES": entities,
            "VALUES": values[:10],
            "EVIDENCE": evidence_chunks[:10],
        },
    )

    candidates: list[dict] = []
    if isinstance(raw, dict):
        for item in raw.get("candidates") or []:
            if not isinstance(item, dict):
                continue
            headline = _clean(item.get("headline"), 80)
            subline = _clean(item.get("subline"), 70)
            if not hook_style_pass(headline, subline):
                continue
            if not _numeric_safe(headline, subline, evidence):
                continue
            candidates.append(
                {
                    "headline": headline,
                    "subline": subline,
                    "angle": _clean(item.get("angle"), 80),
                    "score": round(_style_score(headline, subline), 2),
                }
            )

    candidates.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    if candidates:
        best = candidates[0]
        return {
            "headline": best["headline"],
            "subline": best["subline"],
            "source": "llm",
            "score": best["score"],
            "candidate_count": len(candidates),
            "candidates": candidates,
            "warning": warning,
            "style_pass": True,
        }

    fh, fs = _fallback(fallback_headline, evidence or fallback_subline, entities[0] if entities else "")
    return {
        "headline": fh,
        "subline": fs,
        "source": "deterministic",
        "score": round(_style_score(fh, fs), 2),
        "candidate_count": 0,
        "candidates": [],
        "warning": warning,
        "style_pass": hook_style_pass(fh, fs),
    }
