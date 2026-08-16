from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

import story_article_cleaner


STORY_GRAPH_ENGINE_VERSION = "story-graph-v10.3"

_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_SCALE_KINDS = {"money", "capacity", "percent", "quantity", "price", "valuation"}

_RELATION_RULES = [
    ("before_state", ["これまで", "従来", "以前", "主力", "formerly", "previously", "used to"]),
    ("change", ["転換", "移行", "多角化", "参入", "拡大", "転用", "再編", "変える", "変わる", "shift", "transition", "pivot", "diversif", "expand", "move into", "convert"]),
    ("deal", ["契約", "提携", "買収", "出資", "資金調達", "融資", "取得", "締結", "lease", "contract", "agreement", "acquire", "acquisition", "funding", "financing", "investment round", "strategic investment", "invested in", "stake purchase"]),
    ("flow", ["流入", "流出", "資金流入", "買い越", "売り越", "inflow", "outflow", "allocation", "fund flow"]),
    ("policy", ["規制", "法案", "法律", "承認", "施行", "当局", "金融庁", "規則", "ルール", "regulation", "regulator", "approval", "law", "rule", "policy"]),
    ("risk", ["破綻", "流出", "攻撃", "ハッキング", "盗難", "清算", "危機", "損失", "hack", "breach", "collapse", "liquidation", "fraud"]),
    ("cause", ["ため", "背景", "受け", "により", "理由", "because", "due to", "driven by", "amid", "as demand"]),
    ("contrast", ["一方", "しかし", "だが", "ただし", "にもかかわらず", "while", "but", "however", "despite", "whereas"]),
    ("impact", ["影響", "意味", "評価", "示す", "可能性", "見方", "impact", "implication", "valuation", "could", "may", "signals"]),
    ("future", ["予定", "計画", "見込み", "までに", "今後", "開始する", "稼働", "施行", "適用", "発効", "will", "plan", "expected", "scheduled", "target", "launch", "effective"]),
    ("history", ["過去", "歴史", "当時", "以来", "historical", "historically", "previous cycle", "dot-com"]),
]

_ROLE_ORDER = {
    "hook": 0, "context": 10, "actor": 15, "before": 20, "change": 30, "deal": 35,
    "scale": 40, "cause": 50, "contrast": 55, "evidence": 60, "impact": 70, "timeline": 80, "watch": 90,
}


@dataclass
class FactNode:
    id: str
    source_id: str
    sentence: str
    subject: str
    relation: str
    values: list[str]
    value_details: list[dict]
    years: list[str]
    score: float
    index: int
    complete: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CardPlanItem:
    role: str
    fact_ids: list[str]
    scene_type: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(value: object, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _sid(row: dict) -> str:
    return str(row.get("id") or row.get("source_id") or row.get("url") or "")


def _term_present(text: str, term: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9 .&+/_-]+", term):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, flags=re.I))
    return term in text


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？!?\.])\s+|\n+", str(text or ""))
    out: list[str] = []
    for item in raw:
        sentence = _clean(item, 900)
        if len(sentence) < 12 or sentence in out or story_article_cleaner.has_boilerplate(sentence):
            continue
        if not story_article_cleaner.sentence_complete(sentence):
            continue
        out.append(sentence)
    return out


def _canonical_number(value: str) -> str:
    return value.strip().rstrip(".,").replace(",", "").replace(" ", "")


def _value_details(sentence: str) -> tuple[list[dict], list[str], list[str]]:
    details: list[dict] = []
    occupied: list[tuple[int, int]] = []

    def add(kind: str, raw: str, canonical: str, span: tuple[int, int]) -> None:
        if any(span[0] < e and span[1] > s for s, e in occupied):
            return
        details.append({"kind": kind, "raw": _clean(raw, 80).rstrip(".,;:"), "canonical": canonical})
        occupied.append(span)

    for match in re.finditer(r"(?<!\w)([$¥￥])\s*(\d[\d,.]*(?:\.\d+)?)", sentence):
        currency = "usd" if match.group(1) == "$" else "jpy"
        num = _canonical_number(match.group(2))
        add("money", match.group(0), f"money:{num}:{currency}", match.span())

    money_suffix = re.compile(
        r"(?:約\s*)?(\d[\d,.]*(?:\.\d+)?)\s*(兆円|億円|万円|円|兆ドル|億ドル|万ドル|ドル|USD|JPY|billion|million|trillion|bn|mn)",
        re.I,
    )
    for match in money_suffix.finditer(sentence):
        unit = match.group(2).casefold()
        currency = "jpy" if unit in {"兆円", "億円", "万円", "円", "jpy"} else "usd"
        num = _canonical_number(match.group(1))
        add("money", match.group(0), f"money:{num}:{unit}:{currency}", match.span())

    for match in re.finditer(r"(\d[\d,.]*(?:\.\d+)?)\s*(MW|GW|メガワット|ギガワット)", sentence, flags=re.I):
        unit = "mw" if match.group(2).casefold() in {"mw", "メガワット"} else "gw"
        add("capacity", match.group(0), f"capacity:{_canonical_number(match.group(1))}:{unit}", match.span())

    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", sentence):
        add("percent", match.group(0), f"percent:{match.group(1)}", match.span())

    for match in re.finditer(r"(?<!\d)(\d{1,3})\s*(年間|年|years?|months?|か月|ヶ月)(?!\d)", sentence, flags=re.I):
        unit = match.group(2).casefold()
        canonical_unit = "years" if unit in {"年", "年間", "year", "years"} else "months"
        add("duration", match.group(0), f"duration:{match.group(1)}:{canonical_unit}", match.span())

    for match in re.finditer(
        r"(?<![\dA-Za-z])(\d[\d,.]*(?:\.\d+)?)\s*(shares?|BTC|ETH|SOL|tokens?|users?|customers?|件|人|台|枚|株)(?![A-Za-z])",
        sentence,
        flags=re.I,
    ):
        add("quantity", match.group(0), f"quantity:{_canonical_number(match.group(1))}:{match.group(2).casefold()}", match.span())

    years = list(dict.fromkeys(_YEAR_RE.findall(sentence)))
    for year in years:
        details.append({"kind": "year", "raw": year, "canonical": f"year:{year}"})

    values = list(dict.fromkeys(str(item["raw"]) for item in details))
    return details[:12], values[:12], years[:8]


def _relations(sentence: str) -> list[str]:
    matched: list[str] = []
    for relation, terms in _RELATION_RULES:
        if any(_term_present(sentence, term) for term in terms):
            matched.append(relation)

    lower = sentence.casefold()
    if "deal" in matched and re.search(r"\binvestment\s+(?:thesis|outlook|case|strategy|view)\b", lower):
        transactional = any(_term_present(sentence, t) for t in ["contract", "agreement", "funding", "financing", "invested in", "investment round", "strategic investment", "stake purchase"])
        if not transactional:
            matched = [r for r in matched if r != "deal"]

    if matched:
        return list(dict.fromkeys(matched))
    return ["evidence" if re.search(r"\d", sentence) else "context"]


def _subject(sentence: str, entities: list[str]) -> str:
    folded = sentence.casefold()
    for entity in sorted([e for e in entities if e], key=len, reverse=True):
        if entity.casefold() in folded:
            return entity
    return entities[0] if entities else ""


def _fact_score(sentence: str, relation: str, details: list[dict], subject: str) -> float:
    non_temporal = sum(1 for d in details if d.get("kind") in _SCALE_KINDS)
    score = 0.24 + min(0.22, len(sentence) / 900) + min(0.24, non_temporal * 0.08 + len(details) * 0.025)
    if subject:
        score += 0.10
    if relation in {"change", "deal", "policy", "risk", "flow", "before_state", "future", "contrast"}:
        score += 0.18
    return round(min(1.0, score), 3)


def extract_fact_graph(hero: dict, resources: list[dict]) -> dict:
    allowed = {str(v) for v in hero.get("resource_ids") or [] if v}
    entities = list(hero.get("entities") or [])
    nodes: list[FactNode] = []
    sentence_index = 0

    for row in resources or []:
        source_id = _sid(row)
        if allowed and source_id not in allowed:
            continue
        material = _clean(row.get("material") or row.get("excerpt"), 18000)
        title = _clean(row.get("title"), 400)
        for sentence in _sentences(f"{title}。 {material}"):
            details, values, years = _value_details(sentence)
            subject = _subject(sentence, entities)
            for relation in _relations(sentence):
                payload = f"{source_id}|{sentence_index}|{relation}|{sentence}"
                nodes.append(FactNode(
                    id="fact_" + hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:12],
                    source_id=source_id,
                    sentence=sentence,
                    subject=subject,
                    relation=relation,
                    values=values,
                    value_details=details,
                    years=years,
                    score=_fact_score(sentence, relation, details, subject),
                    index=sentence_index,
                    complete=True,
                ))
            sentence_index += 1

    unique: list[FactNode] = []
    seen: set[tuple[str, str]] = set()
    for node in sorted(nodes, key=lambda n: (n.index, -n.score)):
        sentence_key = re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龥]+", "", node.sentence.casefold())[:220]
        key = (node.relation, sentence_key)
        if not sentence_key or key in seen:
            continue
        seen.add(key)
        unique.append(node)

    by_relation: dict[str, list[str]] = {}
    for node in unique:
        by_relation.setdefault(node.relation, []).append(node.id)

    return {
        "version": STORY_GRAPH_ENGINE_VERSION,
        "source_ids": sorted({_sid(r) for r in resources if _sid(r) and (not allowed or _sid(r) in allowed)}),
        "entities": entities,
        "facts": [node.to_dict() for node in unique[:180]],
        "relations": by_relation,
    }


def _facts(graph: dict) -> list[dict]:
    return [dict(item) for item in graph.get("facts") or []]


def _has_scale_value(fact: dict) -> bool:
    return any(str(item.get("kind") or "") in _SCALE_KINDS for item in fact.get("value_details") or [])


def _has_year(fact: dict) -> bool:
    return bool(fact.get("years"))


def _best(
    graph: dict,
    relations: list[str],
    require_scale: bool = False,
    require_year: bool = False,
    exclude: set[str] | None = None,
    exclude_sentences: set[int] | None = None,
) -> dict | None:
    exclude = exclude or set()
    exclude_sentences = exclude_sentences or set()
    candidates = [
        f for f in _facts(graph)
        if f.get("relation") in relations
        and f.get("id") not in exclude
        and int(f.get("index") or 0) not in exclude_sentences
        and bool(f.get("complete", True))
    ]
    if require_scale:
        candidates = [f for f in candidates if _has_scale_value(f)]
    if require_year:
        candidates = [f for f in candidates if _has_year(f)]
    if not candidates:
        return None
    candidates.sort(
        key=lambda f: (
            float(f.get("score") or 0),
            sum(1 for d in f.get("value_details") or [] if d.get("kind") in _SCALE_KINDS),
            len(f.get("values") or []),
            -int(f.get("index") or 0),
        ),
        reverse=True,
    )
    return candidates[0]


def _electrical_context(text: str) -> bool:
    terms = ["electric", "electricity", "electrical", "power plant", "power grid", "grid", "substation", "transmission", "MW", "GW", "電力", "発電", "送電", "変電"]
    return any(_term_present(text, t) for t in terms)


def infer_scene_type(role: str, facts: list[dict]) -> str:
    text = " ".join(str(f.get("sentence") or "") for f in facts)
    kinds = {str(d.get("kind") or "") for f in facts for d in f.get("value_details") or []}

    if role in {"timeline", "watch"}:
        return "timeline_milestones"
    if role == "scale" and kinds & _SCALE_KINDS:
        return "numeric_evidence"
    if role == "contrast":
        return "split_comparison"
    if any(_term_present(text, t) for t in ["規制", "当局", "法案", "法律", "承認", "policy", "regulation", "regulator", "law", "approval"]):
        return "policy_document"
    if any(_term_present(text, t) for t in ["流入", "流出", "資金流入", "inflow", "outflow", "allocation", "fund flow"]):
        return "capital_flow"
    if any(_term_present(text, t) for t in ["ハッキング", "盗難", "攻撃", "hack", "fraud", "breach", "theft"]):
        return "security_forensics"
    if any(_term_present(text, t) for t in ["data center", "server", "factory", "mining", "データセンター", "サーバー", "工場", "採掘", "マイニング"]) or _electrical_context(text):
        return "industrial_infrastructure"
    if any(_term_present(text, t) for t in ["store of value", "scarcity", "purchasing power", "価値保存", "希少性", "購買力"]):
        return "asset_store_of_value"
    if kinds & {"money"} or any(_term_present(text, t) for t in ["trades near", "trading at", "価格", "price"]):
        return "market_price_context"
    if role in {"change", "deal"}:
        return "transition_scene"
    if role in {"cause", "impact"}:
        return "system_relationship"
    if role in {"actor", "context", "before"}:
        return "entity_environment"
    return "documentary_editorial"


def _dominant_tag(graph: dict, selected_fact_ids: list[str]) -> str:
    selected = set(selected_fact_ids)
    facts = [f for f in _facts(graph) if str(f.get("id")) in selected] or _facts(graph)
    weights: dict[str, float] = {}
    for fact in facts:
        relation = str(fact.get("relation") or "context")
        weights[relation] = weights.get(relation, 0.0) + float(fact.get("score") or 0.4)

    def w(name: str) -> float:
        return weights.get(name, 0.0)

    if w("policy") >= 0.9 and w("policy") >= max(w("change"), w("deal"), w("history")) * 0.8:
        return "policy_change"
    if w("risk") >= 0.9:
        return "crisis_or_risk"
    if w("flow") >= 0.9:
        return "money_flow"

    history_facts = [f for f in facts if f.get("relation") == "history"]
    explicit_past_years = {y for f in history_facts for y in f.get("years") or [] if int(y) < 2020}
    comparative = any(
        any(_term_present(str(f.get("sentence") or ""), t) for t in ["1929", "2000", "then", "当時", "比較", "以来", "dot-com"])
        for f in history_facts
    )
    if len(history_facts) >= 2 and (explicit_past_years or comparative) and w("history") >= 1.2:
        return "historical_parallel"
    if w("before_state") >= 0.5 and (w("change") + w("deal")) >= 0.9:
        return "business_transformation"
    if w("contrast") >= 1.0 and w("contrast") >= max(w("change"), w("deal")):
        return "contradiction"
    if (w("change") + w("deal")) >= 1.0:
        return "power_shift"
    return "story_event"


def _role_candidates(graph: dict) -> list[tuple[str, dict]]:
    selected: list[tuple[str, dict]] = []
    mapping = [
        ("before", ["before_state"], False, False),
        ("change", ["change"], False, False),
        ("deal", ["deal"], False, False),
        ("scale", ["deal", "evidence", "flow", "policy", "future", "context"], True, False),
        ("cause", ["cause"], False, False),
        ("contrast", ["contrast"], False, False),
        ("impact", ["impact"], False, False),
        ("timeline", ["future"], False, True),
        ("evidence", ["evidence", "history"], False, False),
        ("context", ["context", "policy", "risk", "flow"], False, False),
    ]
    used_ids: set[str] = set()
    used_sentences: set[int] = set()
    for role, relations, require_scale, require_year in mapping:
        fact = _best(graph, relations, require_scale=require_scale, require_year=require_year, exclude=used_ids, exclude_sentences=used_sentences)
        if not fact:
            fact = _best(graph, relations, require_scale=require_scale, require_year=require_year, exclude=used_ids)
        if fact:
            selected.append((role, fact))
            used_ids.add(str(fact.get("id")))
            used_sentences.add(int(fact.get("index") or 0))
    return selected


def build_story_plan(hero: dict, graph: dict, content_card_count: int) -> dict:
    content_card_count = max(4, min(8, int(content_card_count or 6)))
    facts = _facts(graph)
    if not facts:
        return {"version": STORY_GRAPH_ENGINE_VERSION, "error": "No structured facts available.", "cards": []}

    hook = _best(graph, ["change", "deal", "policy", "risk", "flow", "contrast", "future", "evidence", "context", "history"]) or facts[0]
    hook_id = str(hook.get("id"))

    final_fact = _best(graph, ["future"], require_year=True, exclude={hook_id}) or _best(graph, ["future"], exclude={hook_id})
    final_role = "watch" if final_fact else "impact"
    if not final_fact:
        final_fact = _best(graph, ["impact", "cause", "contrast", "evidence", "context"], exclude={hook_id})

    reserved = {hook_id}
    if final_fact:
        reserved.add(str(final_fact.get("id")))

    middle: list[tuple[str, dict]] = []
    for role, fact in sorted(_role_candidates(graph), key=lambda item: _ROLE_ORDER.get(item[0], 50)):
        fid = str(fact.get("id"))
        if fid in reserved:
            continue
        if final_fact and final_role == "watch" and role == "timeline":
            continue
        middle.append((role, fact))
        reserved.add(fid)

    slots: list[tuple[str, dict]] = [("hook", hook)]
    target_middle = max(0, content_card_count - 2)
    slots.extend(middle[:target_middle])

    if final_fact and len(slots) < content_card_count:
        slots.append((final_role, final_fact))

    if len(slots) < content_card_count:
        used = {str(f.get("id")) for _, f in slots}
        for fact in sorted(facts, key=lambda f: float(f.get("score") or 0), reverse=True):
            if str(fact.get("id")) in used:
                continue
            relation = str(fact.get("relation"))
            role = {
                "before_state": "before", "change": "change", "deal": "deal", "cause": "cause",
                "contrast": "contrast", "impact": "impact", "future": "timeline", "history": "evidence",
                "policy": "context", "risk": "context", "flow": "context",
            }.get(relation, "evidence")
            if role == "timeline" and not _has_year(fact):
                role = "evidence"
            insert_at = len(slots) - 1 if final_fact and slots and slots[-1][1] is final_fact else len(slots)
            slots.insert(insert_at, (role, fact))
            used.add(str(fact.get("id")))
            if len(slots) >= content_card_count:
                break

    slots = slots[:content_card_count]
    if final_fact and not any(f is final_fact for _, f in slots):
        slots[-1] = (final_role, final_fact)
    elif final_fact:
        slots = [(r, f) for r, f in slots if f is not final_fact] + [(final_role, final_fact)]

    selected_ids = [str(f.get("id")) for _, f in slots]
    tag = _dominant_tag(graph, selected_ids)
    subject = str(hero.get("entities", [""])[0] if hero.get("entities") else "")
    headline = _clean(hero.get("headline_ja") or (hero.get("hero_resource") or {}).get("title") or hook.get("sentence"), 100)
    thesis = _clean(hook.get("sentence"), 360)

    cards = [
        CardPlanItem(
            role=role,
            fact_ids=[str(fact.get("id"))],
            scene_type=infer_scene_type(role, [fact]),
            reason=f"selected {fact.get('relation')} evidence; scale cards require non-temporal quantities",
        ).to_dict()
        for role, fact in slots
    ]
    return {
        "version": STORY_GRAPH_ENGINE_VERSION,
        "planning_policy": "facts first -> typed values/relations -> dynamic card roles -> weighted archetype tag last",
        "headline_ja": headline,
        "thesis": thesis,
        "subject": subject,
        "archetype_tag": tag,
        "fact_ids": selected_ids,
        "cards": cards,
    }


def scene_matches_evidence(scene_type: str, role: str, facts: list[dict]) -> bool:
    return scene_type == infer_scene_type(role, facts)
