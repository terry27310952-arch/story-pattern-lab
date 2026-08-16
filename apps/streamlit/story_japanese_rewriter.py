from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

import story_llm_runtime


STORY_JAPANESE_REWRITER_VERSION = "story-ja-rewriter-v1.0"
PROVIDER_LOCAL = "local"
PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"


def _clean(value: object, limit: int = 900) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def japanese_ratio(text: str) -> float:
    value = str(text or "")
    letters = re.findall(r"[A-Za-zぁ-んァ-ヶ一-龥]", value)
    if not letters:
        return 0.0
    jp = re.findall(r"[ぁ-んァ-ヶ一-龥]", value)
    return len(jp) / len(letters)


def _numeric_tokens(text: str) -> set[str]:
    return set(
        re.findall(
            r"(?<![A-Za-z0-9])(?:[$¥￥]\s*)?\d[\d,.]*(?:\.\d+)?(?:\s*(?:%|MW|GW|億円|兆円|万円|円|億ドル|兆ドル|万ドル|ドル|USD|JPY|年|年間|か月|ヶ月|years?|months?))?",
            str(text or ""),
            flags=re.I,
        )
    )


def numeric_safe(headline: str, body: str, evidence: str) -> bool:
    evidence_digits = re.sub(r"[^0-9]", "", str(evidence or ""))
    for token in _numeric_tokens(f"{headline} {body}"):
        digits = re.sub(r"[^0-9]", "", token)
        if digits and digits not in evidence_digits:
            return False
    return True


def parse_json_object(text: str) -> dict | None:
    """Recover one JSON object even when the model adds prose or code fences."""
    value = str(text or "").strip()
    if not value:
        return None
    value = re.sub(r"```(?:json)?", "", value, flags=re.I).replace("```", "").strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", value):
        try:
            parsed, _ = decoder.raw_decode(value[match.start() :])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
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


def _ollama_payload(config: dict, system: str, user: str, temperature: float) -> tuple[str, dict, dict[str, str]]:
    base = str(config.get("base_url") or story_llm_runtime.DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = str(
        config.get("model")
        or (
            story_llm_runtime.DEFAULT_OLLAMA_MODEL
            if story_llm_runtime.is_cloud_ollama(base)
            else story_llm_runtime.DEFAULT_LOCAL_OLLAMA_MODEL
        )
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": float(temperature)},
    }
    if model.casefold().startswith("gpt-oss"):
        payload["think"] = "low"
    if not story_llm_runtime.is_cloud_ollama(base):
        payload["format"] = "json"
    return (
        story_llm_runtime.ollama_api_url(base, "chat"),
        payload,
        story_llm_runtime.ollama_headers(str(config.get("api_key") or "")),
    )


def _call_model(config: dict, system: str, user: str, temperature: float = 0.2) -> tuple[str, str | None]:
    provider = str(config.get("provider") or PROVIDER_LOCAL)
    if provider == PROVIDER_LOCAL:
        return "", "Japanese rewriter requires an LLM provider."
    try:
        if provider == PROVIDER_OLLAMA:
            url, payload, headers = _ollama_payload(config, system, user, temperature)
            raw = _post_json(url, payload, headers)
            message = raw.get("message") or {}
            return str(message.get("content") or ""), None
        if provider == PROVIDER_OPENAI_COMPATIBLE:
            base = str(config.get("base_url") or "").rstrip("/")
            model = str(config.get("model") or "")
            if not base or not model:
                return "", "OpenAI-compatible Japanese rewriter configuration is incomplete."
            endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
            key = str(config.get("api_key") or "")
            raw = _post_json(
                endpoint,
                {
                    "model": model,
                    "temperature": float(temperature),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                {"Authorization": f"Bearer {key}"} if key else {},
            )
            choices = raw.get("choices") or []
            content = (((choices[0] if choices else {}).get("message") or {}).get("content") or "")
            return str(content), None
    except Exception as error:
        return "", f"Japanese rewrite model failed: {error}"
    return "", f"Unsupported Japanese rewrite provider: {provider}"


def _extract_card(parsed: dict | None) -> tuple[str, str]:
    if not isinstance(parsed, dict):
        return "", ""
    if isinstance(parsed.get("card"), dict):
        parsed = parsed["card"]
    headline = _clean(parsed.get("headline"), 90)
    body = _clean(parsed.get("body") or parsed.get("subline") or parsed.get("key_message"), 300)
    return headline, body


def _valid_copy(headline: str, body: str, evidence: str, hook: bool) -> bool:
    combined = f"{headline} {body}".strip()
    if not headline:
        return False
    if japanese_ratio(combined) < 0.42:
        return False
    if not hook and not body:
        return False
    if hook and len(headline) > 48:
        return False
    if not numeric_safe(headline, body, evidence):
        return False
    return True


def rewrite_card(
    config: dict,
    role: str,
    evidence: str,
    subject: str = "",
    original_headline: str = "",
    original_body: str = "",
    hook: bool = False,
) -> dict:
    """Translate/rewrite one evidence-bound card into publishable ja-JP, with retry."""
    if str(config.get("provider") or PROVIDER_LOCAL) == PROVIDER_LOCAL:
        return {
            "accepted": False,
            "headline": "",
            "body": "",
            "attempts": 0,
            "warning": "Japanese rewrite skipped because provider is deterministic local mode.",
            "raw_preview": "",
        }

    system = (
        "あなたは日本の金融メディアの編集者です。入力されたEVIDENCEだけを根拠に、カード本文を自然な日本語へ書き直してください。"
        "翻訳調ではなく、日本人が読む短い編集文にしてください。数字、日付、固有名詞、因果関係を追加・推測・変更してはいけません。"
        "英語の原文を本文に残さないでください。固有名詞とティッカーは原綴りのままで構いません。"
        "出力は必ずJSONオブジェクト1個だけにし、headlineとbody以外の説明文を付けないでください。"
    )
    if hook:
        system += (
            "これは1枚目のフックです。記事タイトルの要約ではなく、EVIDENCE内の最も強い変化・矛盾・規模・意外性を一つだけ使い、"
            "headlineは最大48文字、bodyは任意で最大44文字にしてください。"
        )

    base_payload = {
        "role": role,
        "subject": _clean(subject, 100),
        "evidence": _clean(evidence, 1400),
        "current_headline": _clean(original_headline, 100),
        "current_body": _clean(original_body, 340),
        "rules": {
            "locale": "ja-JP",
            "evidence_only": True,
            "preserve_numbers": True,
            "no_new_claims": True,
            "no_english_sentence_fallback": True,
        },
        "schema": {"headline": "自然な日本語", "body": "自然な日本語。hookなら空文字可"},
    }

    warnings: list[str] = []
    last_raw = ""
    for attempt in range(1, 3):
        payload = dict(base_payload)
        payload["attempt"] = attempt
        if attempt == 2:
            payload["repair_instruction"] = (
                "前回は形式または日本語品質の検証に失敗しました。説明文を一切付けず、JSONオブジェクト1個だけを返してください。"
                "EVIDENCEの意味を短く正確に日本語化してください。"
            )
        raw, warning = _call_model(config, system, json.dumps(payload, ensure_ascii=False), temperature=0.18 if not hook else 0.55)
        last_raw = raw
        if warning:
            warnings.append(warning)
        parsed = parse_json_object(raw)
        headline, body = _extract_card(parsed)
        if _valid_copy(headline, body, evidence, hook):
            return {
                "accepted": True,
                "headline": headline,
                "body": body,
                "attempts": attempt,
                "warning": " / ".join(dict.fromkeys(warnings)),
                "raw_preview": _clean(raw, 240),
            }

    return {
        "accepted": False,
        "headline": "",
        "body": "",
        "attempts": 2,
        "warning": " / ".join(dict.fromkeys(warnings)) or "Japanese rewrite output failed validation after 2 attempts.",
        "raw_preview": _clean(last_raw, 240),
    }
