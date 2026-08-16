from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

import story_llm_runtime


STORY_JAPANESE_REWRITER_VERSION = "story-ja-rewriter-v1.3"
PROVIDER_LOCAL = "local"
PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"


def _clean(value: object, limit: int = 900) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _neutral_latin_token(token: str) -> bool:
    value = str(token or "")
    if not value:
        return True
    if any(ch.isdigit() for ch in value):
        return True
    letters = re.sub(r"[^A-Za-z]", "", value)
    if not letters:
        return True
    if letters.isupper() and len(letters) <= 12:
        return True
    if len(letters) >= 2 and letters[0].isupper() and any(ch.isupper() for ch in letters[1:]):
        return True
    if len(letters) >= 3 and letters[0].isupper() and letters[1:].islower():
        return True
    return False


def japanese_ratio(text: str) -> float:
    """Estimate Japanese prose while treating Latin tickers/product/proper names as neutral."""
    value = re.sub(r"https?://\S+", " ", str(text or ""))
    jp_count = len(re.findall(r"[ぁ-んァ-ヶ一-龥]", value))
    english_letters = 0
    for token in re.findall(r"[A-Za-z][A-Za-z0-9.+&/_-]*", value):
        if not _neutral_latin_token(token):
            english_letters += len(re.sub(r"[^A-Za-z]", "", token))
    if jp_count == 0:
        return 0.0
    return jp_count / max(1, jp_count + english_letters)


def _numeric_tokens(text: str) -> set[str]:
    return set(
        re.findall(
            r"(?<![A-Za-z0-9])(?:[$¥￥]\s*)?\d[\d,.]*(?:\.\d+)?(?:\s*(?:%|MW|GW|億円|兆円|万円|円|億ドル|兆ドル|万ドル|ドル|USD|JPY|年|年間|か月|ヶ月|years?|months?|billion|million|trillion|bn|mn))?",
            str(text or ""),
            flags=re.I,
        )
    )


def _digits(token: str) -> str:
    return re.sub(r"[^0-9]", "", str(token or ""))


def numeric_safe(headline: str, body: str, evidence: str) -> bool:
    """Require every output number to correspond to one concrete evidence number.

    The old implementation concatenated every evidence digit and then used substring
    matching. That accidentally accepted unit conversions such as $100,000 -> 10万ドル,
    which the stricter production claim validator later rejected. Here each claim number
    must match one evidence number independently (commas/decimal punctuation may differ).
    """
    claim_tokens = _numeric_tokens(f"{headline} {body}")
    if not claim_tokens:
        return True
    evidence_digits = {_digits(token) for token in _numeric_tokens(evidence) if _digits(token)}
    for token in claim_tokens:
        digits = _digits(token)
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


def _parse_line_protocol(text: str) -> tuple[str, str]:
    value = str(text or "").strip()
    headline = ""
    body = ""
    for line in value.splitlines():
        stripped = line.strip()
        head_match = re.match(r"^(?:\[?HEADLINE\]?|見出し|headline)\s*[:：]\s*(.+)$", stripped, flags=re.I)
        body_match = re.match(r"^(?:\[?BODY\]?|本文|body)\s*[:：]\s*(.*)$", stripped, flags=re.I)
        if head_match:
            headline = _clean(head_match.group(1), 90)
        elif body_match:
            body = _clean(body_match.group(1), 300)
    return headline, body


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


def _valid_copy(headline: str, body: str, evidence: str, hook: bool, avoid_numbers: bool = False) -> bool:
    combined = f"{headline} {body}".strip()
    if not headline:
        return False
    if japanese_ratio(combined) < 0.42:
        return False
    if not hook and not body:
        return False
    if hook and len(headline) > 48:
        return False
    if avoid_numbers and _numeric_tokens(combined):
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
    avoid_numbers: bool = False,
) -> dict:
    """Translate/rewrite one evidence-bound card into publishable ja-JP, with recovery retries."""
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
        "数字を使う場合はEVIDENCE中の数字表記をそのまま使い、換算・単位変換・桁の言い換えをしないでください。"
    )
    if avoid_numbers:
        system += "今回は数字・年・金額・割合を一切使わず、意味だけを日本語で表現してください。"
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
            "preserve_numbers_verbatim": not avoid_numbers,
            "avoid_numbers": avoid_numbers,
            "no_new_claims": True,
            "no_english_sentence_fallback": True,
        },
    }

    warnings: list[str] = []
    last_raw = ""
    for attempt in range(1, 4):
        payload = dict(base_payload)
        payload["attempt"] = attempt
        if attempt < 3:
            payload["schema"] = {"headline": "自然な日本語", "body": "自然な日本語。hookなら空文字可"}
            if attempt == 2:
                payload["repair_instruction"] = (
                    "前回は形式または日本語品質の検証に失敗しました。説明文を一切付けず、JSONオブジェクト1個だけを返してください。"
                    "EVIDENCEの意味を短く正確に日本語化してください。数字を使うならEVIDENCEの表記を一字も換算しないでください。"
                )
            prompt_text = json.dumps(payload, ensure_ascii=False)
        else:
            payload["repair_instruction"] = (
                "JSON形式は使わず、必ず次の2行だけを返してください。\n"
                "HEADLINE: 日本語の見出し\nBODY: 日本語の本文\n"
                "説明、コードフェンス、前置きは禁止です。"
            )
            prompt_text = json.dumps(payload, ensure_ascii=False)

        raw, warning = _call_model(
            config,
            system,
            prompt_text,
            temperature=0.16 if not hook else (0.50 if attempt < 3 else 0.35),
        )
        last_raw = raw
        if warning:
            warnings.append(warning)

        if attempt < 3:
            headline, body = _extract_card(parse_json_object(raw))
        else:
            headline, body = _parse_line_protocol(raw)
        if _valid_copy(headline, body, evidence, hook, avoid_numbers=avoid_numbers):
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
        "attempts": 3,
        "warning": " / ".join(dict.fromkeys(warnings)) or "Japanese rewrite output failed validation after 3 attempts.",
        "raw_preview": _clean(last_raw, 240),
    }