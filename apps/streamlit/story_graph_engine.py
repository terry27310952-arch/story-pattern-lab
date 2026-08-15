from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

import story_article_cleaner


STORY_GRAPH_ENGINE_VERSION = "story-graph-v10.0"

_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_NUMBER_PATTERNS = [
    ("money", re.compile(r"(?:約\s*)?(?:\$\s*)?\d[\d,.]*(?:\.\d+)?\s*(?:兆|億|万)?\s*(?:円|ドル|USD|JPY|billion|million|trillion|bn|mn)", re.I)),
    ("capacity", re.compile(r"\d[\d,.]*(?:\.\d+)?\s*(?:MW|GW|メガワット|ギガワット)", re.I)),
    ("percent", re.compile(r"\d+(?:\.\d+)?\s*%")),
    ("duration", re.compile(r"(?<!\d)\d{1,3}\s*(?:年間|年|years?|months?|か月|ヶ月)(?!\d)", re.I)),
]

_RELATION_RULES = [
    ("before_state", ["これまで", "従来", "以前", "主力", "formerly", "previously", "historically", "used to"]),
    ("change", ["転換", "移行", "多角化", "参入", "拡大", "転用", "再編", "変える", "変わる", "shift", "transition", "pivot", "diversif", "expand", "move into", "convert"]),
    ("deal", ["契約", "提携", "買収", "出資", "取得", "締結", "lease", "deal", "contract", "agreement", "acquire", "investment", "partnership"]),
    ("flow", ["流入", "流出", "資金", "買い越", "売り越", "inflow", "outflow", "allocation", "fund flow"]),
    ("policy", ["規制", "法案", "法律", "承認", "施行", "当局", "金融庁", "規則", "regulation", "regulator", "approval", "law", "rule", "policy"]),
    ("risk", ["破綻", "流出", "攻撃", "ハッキング", "盗難", "清算", "危機", "損失", "hack", "breach", "collapse", "liquidation", "risk", "fraud"]),
    ("cause", ["ため", "背景", "受け", "により", "理由", "because", "due to", "driven by", "amid", "as demand"]),
    ("contrast", ["一方", "しかし", "だが", "ただし", "にもかかわらず", "while", "but", "however", "despite", "whereas"]),
    ("impact", ["影響", "意味", "評価", "示す", "可能性", "見方", "impact", "implication", "valuation", "could", "may", "signals"]),
    ("future", ["予定", "計画", "見込み", "までに", "今後", "開始する", "稼働", "will", "plan", "expected", "scheduled", "target", "launch"]),
    ("history", ["過去", "歴史", "当時", "以来", "1929", "2000", "historical", "history", "previous cycle", "dot-com"]),
]

_VISUAL_KEYWORDS = [
    ("industrial_infrastructure", ["工場", "発電", "電力", "データセンター", "採掘", "マイニング", "server", "data center", "mining", "power", "infrastructure"]),
    ("policy_document", ["規制", "当局", "法案", "法律", "承認", "policy", "regulation", "regulator", "law", "approval"]),
    ("capital_flow", ["流入", "流出", "資金", "ETF", "inflow", "outflow", "fund", "allocation"]),
    ("archive_context", ["1929", "2000", "過去", "歴史", "historical", "archive", "dot-com"]),
    ("security_forensics", ["ハッキング", "盗難", "攻撃", "FBI", "hack", "fraud", "breach", "theft"]),
]

_ROLE_ORDER = {
    "hook": 0,
    "context": 10,
    "actor": 15,
    "before": 20,
    "change": 30,
    "deal": 35,
    "scale": 40,
    "cause": 50,
    "contrast": 55,
    "evidence": 60,
    "impact": 70,
    "timeline": 80,
    "watch": 90,
}


@dataclass
class FactNode:
    id: str
    source_id: str
    sentence: str
    subject: str
    relation: str
    values: list[str]
    years: list[str]
    score: float
    index: int

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


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？!?\.])\s+|\n+", str(text or ""))
    out: list[str] = []
    for item in raw:
        sentence = _clean(item, 900)
        if len(sentence) >= 12 and sentence not in out and not story_article_cleaner.has_boilerplate(sentence):
            out.append(sentence)
    return out


def _values(sentence: str) -> tuple[list[str], list[str]]:
    values: list[str] = []
    years = list(dict.fromkeys(_YEAR_RE.findall(sentence)))
    for _, pattern in _NUMBER_PATTERNS:
        for match in pattern.finditer(sentence):
            value = _clean(match.group(0), 80)
            if value and value not in values:
                values.append(value)
    for year in years:
        if year not in values:
            values.append(year)
    return values[:8], years[:6]


def _relation(sentence: str) -> str:
    lower = sentence.casefold()
    hits: list[tuple[int, str]] = []
    for relation, terms in _RELATION_RULES:
        count = sum(1 for term in terms if term.casefold() in lower)
        if count:
            hits.append((count, relation))
    if not hits:
        return "evidence" if re.search(r"\d", sentence) else "context"
    # Prefer structural transitions over generic impact/future words when tied.
    priority = {"change": 10, "deal": 9, "policy": 9, "risk": 9, "flow": 8, "before_state": 8, "contrast": 7, "cause": 6, "future": 5, "history": 5, "impact": 4}
    hits.sort(key=lambda item: (item[0], priority.get(item[1], 0)), reverse=True)
    return hits[0][1]


def _subject(sentence: str, entities: list[str]) -> str:
    folded = sentence.casefold()
    for entity in sorted([e for e in entities if e], key=len, reverse=True):
        if entity.casefold() in folded:
            return entity
    return entities[0] if entities else ""


def _fact_score(sentence: str, relation: str, values: list[str], subject: str) -> float:
    score = 0.25
    score += min(0.25, len(sentence) / 900)
    score += min(0.22, len(values) * 0.07)
    if subject:
        score += 0.12
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
            values, years = _values(sentence)
            relation = _relation(sentence)
            subject = _subject(sentence, entities)
            payload = f"{source_id}|{sentence_index}|{sentence}"
            node = FactNode(
                id="fact_" + hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:12],
                source_id=source_id,
                sentence=sentence,
                subject=subject,
                relation=relation,
                values=values,
                years=years,
                score=_fact_score(sentence, relation, values, subject),
                index=sentence_index,
            )
            nodes.append(node)
            sentence_index += 1

    # Deduplicate near-identical source sentences without knowing the publisher/topic.
    unique: list[FactNode] = []
    seen: set[str] = set()
    for node in sorted(nodes, key=lambda n: (n.index, -n.score)):
        key = re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龥]+", "", node.sentence.casefold())[:220]
        if not key or key in seen:
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
        "facts": [node.to_dict() for node in unique[:120]],
        "relations": by_relation,
    }


def _facts(graph: dict) -> list[dict]:
    return [dict(item) for item in graph.get("facts") or []]


def _best(graph: dict, relations: list[str], require_values: bool = False, exclude: set[str] | None = None) -> dict | None:
    exclude = exclude or set()
    candidates = [f for f in _facts(graph) if f.get("relation") in relations and f.get("id") not in exclude]
    if require_values:
        candidates = [f for f in candidates if f.get("values")]
    if not candidates:
        return None
    candidates.sort(key=lambda f: (float(f.get("score") or 0), len(f.get("values") or []), -int(f.get("index") or 0)), reverse=True)
    return candidates[0]


def _tag_story(graph: dict) -> str:
    relations = {str(f.get("relation")) for f in _facts(graph)}
    if "policy" in relations:
        return "policy_change"
    if "risk" in relations:
        return "crisis_or_risk"
    if "flow" in relations:
        return "money_flow"
    if "history" in relations:
        return "historical_parallel"
    if "before_state" in relations and ("change" in relations or "deal" in relations):
        return "business_transformation"
    if "contrast" in relations:
        return "contradiction"
    if "change" in relations or "deal" in relations:
        return "power_shift"
    return "story_event"


def _scene_for(role: str, facts: list[dict]) -> str:
    text = " ".join(str(f.get("sentence") or "") for f in facts).casefold()
    if role in {"timeline", "watch"}:
        return "timeline_milestones"
    if role == "scale":
        return "numeric_evidence"
    if role == "contrast":
        return "split_comparison"
    for scene, terms in _VISUAL_KEYWORDS:
        if any(term.casefold() in text for term in terms):
            return scene
    if role in {"actor", "context", "before"}:
        return "entity_environment"
    if role in {"change", "deal"}:
        return "transition_scene"
    if role in {"cause", "impact"}:
        return "system_relationship"
    return "documentary_editorial"


def _role_candidates(graph: dict) -> list[tuple[str, dict]]:
    selected: list[tuple[str, dict]] = []
    mapping = [
        ("before", ["before_state"]),
        ("change", ["change"]),
        ("deal", ["deal"]),
        ("scale", ["deal", "evidence", "flow", "policy", "future"]),
        ("cause", ["cause"]),
        ("contrast", ["contrast"]),
        ("impact", ["impact"]),
        ("timeline", ["future"]),
        ("evidence", ["evidence", "history"]),
        ("context", ["context"]),
    ]
    used: set[str] = set()
    for role, relations in mapping:
        fact = _best(graph, relations, require_values=(role == "scale"), exclude=used)
        if not fact and role == "scale":
            fact = _best(graph, ["deal", "flow", "future", "evidence", "context"], require_values=True, exclude=used)
        if fact:
            selected.append((role, fact))
            used.add(str(fact.get("id")))
    return selected


def build_story_plan(hero: dict, graph: dict, content_card_count: int) -> dict:
    content_card_count = max(4, min(8, int(content_card_count or 6)))
    facts = _facts(graph)
    if not facts:
        return {"version": STORY_GRAPH_ENGINE_VERSION, "error": "No structured facts available.", "cards": []}

    used: set[str] = set()
    hook = _best(graph, ["change", "deal", "policy", "risk", "flow", "contrast", "future", "history", "evidence", "context"], exclude=used) or facts[0]
    used.add(str(hook.get("id")))

    role_facts = _role_candidates(graph)
    # Keep only roles with distinct evidence and order them by narrative progression.
    middle: list[tuple[str, dict]] = []
    for role, fact in sorted(role_facts, key=lambda item: _ROLE_ORDER.get(item[0], 50)):
        if str(fact.get("id")) in used:
            continue
        middle.append((role, fact))
        used.add(str(fact.get("id")))

    final = _best(graph, ["future"], exclude=set())
    final_role = "watch" if final else "impact"
    if final is None:
        final = _best(graph, ["impact", "contrast", "evidence", "context"], exclude=set()) or hook

    # Reserve first hook and last watch/impact. Fill the center with actual available facts.
    slots = max(0, content_card_count - 2)
    chosen_middle = middle[:slots]
    cards: list[CardPlanItem] = [
        CardPlanItem("hook", [str(hook.get("id"))], _scene_for("hook", [hook]), "strongest event/evidence hook")
    ]
    for role, fact in chosen_middle:
        cards.append(CardPlanItem(role, [str(fact.get("id"))], _scene_for(role, [fact]), f"available {fact.get('relation')} evidence"))
    cards.append(CardPlanItem(final_role, [str(final.get("id"))], _scene_for(final_role, [final]), "future milestone or strongest implication"))

    # If the source is thin, add remaining high-score facts rather than inventing slots.
    if len(cards) < content_card_count:
        leftovers = [f for f in sorted(facts, key=lambda x: float(x.get("score") or 0), reverse=True) if str(f.get("id")) not in {fid for c in cards for fid in c.fact_ids}]
        insert_at = max(1, len(cards) - 1)
        for fact in leftovers:
            if len(cards) >= content_card_count:
                break
            cards.insert(insert_at, CardPlanItem("evidence", [str(fact.get("id"))], _scene_for("evidence", [fact]), "additional high-confidence evidence"))
            insert_at += 1

    fact_map = {str(f.get("id")): f for f in facts}
    subject = next((str(e) for e in graph.get("entities") or [] if e), "")
    thesis_fact = hook
    thesis = _clean(thesis_fact.get("sentence"), 220)
    headline_seed = _clean((hero.get("hero_resource") or {}).get("title") or hero.get("headline_seed") or thesis, 160)
    if re.search(r"[ぁ-んァ-ヶ一-龥]", headline_seed):
        headline_ja = headline_seed
    else:
        headline_ja = _clean(hero.get("headline_ja") or thesis, 160)

    return {
        "version": STORY_GRAPH_ENGINE_VERSION,
        "archetype_tag": _tag_story(graph),
        "subject": subject,
        "headline_ja": headline_ja,
        "thesis": thesis,
        "cards": [item.to_dict() for item in cards[:content_card_count]],
        "fact_ids": list(fact_map.keys()),
        "planning_policy": "facts first -> relation graph -> dynamic card roles -> archetype tag last",
    }


def facts_for_card(graph: dict, item: dict) -> list[dict]:
    wanted = set(str(v) for v in item.get("fact_ids") or [])
    return [f for f in _facts(graph) if str(f.get("id")) in wanted]
