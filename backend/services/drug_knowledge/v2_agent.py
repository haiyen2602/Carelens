"""Agent-facing Data/Search/RAG V2 facade.

This module is intentionally file-backed and read-only for Phase 7. It lets the
Agent consume Canonical V2 in parallel with the existing V1 DB-backed RAG path
without changing public drug IDs, prescriptions, or production embeddings.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.services.severity import SEVERITY_RANK

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data pharmacy"
FINAL_CANONICAL_DIR = DATA_DIR / "v2" / "final_canonical"
FINAL_CANONICAL_ARTIFACTS = (
    "manifest.json",
    "drug_product.jsonl",
    "drug_id_map.jsonl",
    "drug_product_ingredient.jsonl",
    "drug_knowledge.jsonl",
)
VECTOR_DIM = 512
TOP_K = 5
SAFE_DEFAULT_SEVERITY = next(label for label, rank in SEVERITY_RANK.items() if rank == 2)

BackendMode = Literal["v1", "v2", "shadow"]

KNOWLEDGE_TYPE_TO_FIELD_GROUP = {
    "INDICATION": "cong_dung",
    "ADVERSE_EFFECT": "tac_dung_phu",
    "CONTRAINDICATION": "tac_dung_phu",
    "PRECAUTION": "tac_dung_phu",
    "INTERACTION": "tac_dung_phu",
    "PREGNANCY_LACTATION": "tac_dung_phu",
    "DRIVING_WARNING": "tac_dung_phu",
    "ADMINISTRATION": "cach_dung",
    "GENERAL_DOSAGE": "cach_dung",
    "STORAGE": "bao_quan",
}

TOPIC_KEYWORDS = [
    ("CONTRAINDICATION", ["chong chi dinh", "khong duoc dung", "ai khong dung"]),
    ("ADVERSE_EFFECT", ["tac dung phu", "phan ung bat loi", "adr", "buon non", "chong mat"]),
    ("INTERACTION", ["tuong tac", "dung chung", "uong chung"]),
    ("PREGNANCY_LACTATION", ["mang thai", "co thai", "cho con bu", "thai ky"]),
    ("DRIVING_WARNING", ["lai xe", "van hanh may", "tau xe"]),
    ("ADMINISTRATION", ["cach dung", "dung nhu the nao", "su dung nhu the nao"]),
    ("GENERAL_DOSAGE", ["lieu dung", "uong bao nhieu", "ngay may lan"]),
    ("STORAGE", ["bao quan", "cat giu", "de o dau"]),
    ("INDICATION", ["cong dung", "chi dinh", "tri gi", "dung de lam gi"]),
    ("PRECAUTION", ["than trong", "luu y", "canh bao"]),
]

STOPWORDS = {
    "thuoc",
    "toi",
    "cho",
    "hoi",
    "biet",
    "ve",
    "co",
    "gi",
    "khong",
    "la",
    "va",
    "hay",
    "thi",
    "duoc",
    "dung",
    "uong",
    "nhu",
    "the",
    "nao",
    "bao",
    "nhieu",
    "can",
    "neu",
    "bi",
}


@dataclass(frozen=True)
class AgentKnowledgeLookup:
    results: list[Any]
    trace: dict[str, Any]


@dataclass(frozen=True)
class DrugInfoResult:
    """V2-compatible source row consumed by Agent response nodes."""

    drug_id: str
    ten_thuoc: str
    field_group: str
    noi_dung: str
    danh_muc: str
    muc_nghiem_trong: str
    source: str
    vector_score: float | None
    lexical_score: float | None
    rrf_score: float
    rank: int


@dataclass(frozen=True)
class DrugCatalogItem:
    """Public-slug catalog projection for API and prescription validation."""

    drug_id: str
    ten_thuoc: str
    dang_thuoc: str
    duong_dung: str
    ham_luong: str | None
    tong_so_luong: str | None
    muc_nghiem_trong: str | None

    @property
    def id(self) -> str:
        """Compatibility alias for internal callers that historically read Drug.id."""

        return self.drug_id

    def to_dict(self) -> dict[str, str | None]:
        return {
            "drug_id": self.drug_id,
            "ten_thuoc": self.ten_thuoc,
            "dang_thuoc": self.dang_thuoc,
            "duong_dung": self.duong_dung,
            "ham_luong": self.ham_luong,
            "tong_so_luong": self.tong_so_luong,
            "muc_nghiem_trong": self.muc_nghiem_trong,
        }


@dataclass(frozen=True)
class DrugIdentityCandidate:
    drug_id: str
    ten_thuoc: str
    score: float


@dataclass(frozen=True)
class SideEffectMatchResult:
    drug_id: str
    ten_thuoc: str
    noi_dung: str
    score: float


@dataclass(frozen=True)
class SeveritySource:
    drug_id: str
    text: str
    fallback_severity: str
    status: str
    source_types: tuple[str, ...]


@dataclass(frozen=True)
class V2Chunk:
    id: str
    legacy_drug_id: str
    drug_product_id: str
    ten_thuoc: str
    danh_muc: str
    knowledge_type: str
    text: str
    source: str
    provenance: dict[str, Any]


def normalize_text(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().casefold()
    return re.sub(r"\s+", " ", value)


def tokenize(value: str) -> list[str]:
    return [token for token in normalize_text(value).split() if token and token not in STOPWORDS]


def detect_knowledge_type(utterance: str) -> str | None:
    normalized = normalize_text(utterance)
    for knowledge_type, phrases in TOPIC_KEYWORDS:
        if any(phrase in normalized for phrase in phrases):
            return knowledge_type
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _v2_dir() -> Path:
    configured = get_settings().drug_knowledge_v2_dir
    if configured:
        return Path(configured).resolve()

    missing = [
        filename
        for filename in FINAL_CANONICAL_ARTIFACTS
        if not (FINAL_CANONICAL_DIR / filename).is_file()
    ]
    if missing:
        raise RuntimeError(
            "Final Canonical V2 artifacts are incomplete: "
            + ", ".join(missing)
            + ". Set DRUG_KNOWLEDGE_V2_DIR only for an explicit validated override."
        )
    return FINAL_CANONICAL_DIR


def _bucket(token: str) -> int:
    return int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % VECTOR_DIM


def _sparse_vector(tokens: list[str], idf: dict[str, float]) -> dict[int, float]:
    counts = Counter(tokens)
    vector: dict[int, float] = defaultdict(float)
    for token, count in counts.items():
        vector[_bucket(token)] += (1.0 + math.log(count)) * idf.get(token, 1.0)
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if not norm:
        return {}
    return {idx: value / norm for idx, value in vector.items()}


def _cosine(left: dict[int, float], right: dict[int, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(idx, 0.0) for idx, value in left.items())


class V2AgentKnowledgeService:
    def __init__(self) -> None:
        v2_dir = _v2_dir()
        products = _read_jsonl(v2_dir / "drug_product.jsonl")
        mappings = _read_jsonl(v2_dir / "drug_id_map.jsonl")
        ingredient_rows = _read_jsonl(v2_dir / "drug_product_ingredient.jsonl")
        knowledge_rows = _read_jsonl(v2_dir / "drug_knowledge.jsonl")

        product_id_by_legacy = {row["legacy_drug_id"]: row["drug_product_id"] for row in mappings}
        product_by_id = {row["id"]: row for row in products}
        self.product_id_by_legacy = product_id_by_legacy
        self.legacy_by_product_id = {row["drug_product_id"]: row["legacy_drug_id"] for row in mappings}
        self.products_by_legacy = {row["legacy_drug_id"]: row for row in products}
        strengths_by_product: dict[str, list[str]] = defaultdict(list)
        for row in ingredient_rows:
            strength = str(row.get("raw_strength") or "").strip()
            if strength:
                strengths_by_product[str(row["drug_product_id"])].append(strength)
        self.strengths_by_product = {
            product_id: "; ".join(dict.fromkeys(strengths))
            for product_id, strengths in strengths_by_product.items()
        }
        self.name_index = {
            normalize_text(str(row.get("display_name", ""))): row["legacy_drug_id"]
            for row in products
            if row.get("display_name")
        }
        self.catalog_items = [self._to_catalog_item(row) for row in products]

        self.chunks: list[V2Chunk] = []
        self.by_product_type: dict[tuple[str, str], list[V2Chunk]] = defaultdict(list)
        for row in knowledge_rows:
            product = product_by_id.get(row["drug_product_id"], {})
            chunk = V2Chunk(
                id=row["id"],
                legacy_drug_id=row["legacy_drug_id"],
                drug_product_id=row["drug_product_id"],
                ten_thuoc=str(product.get("display_name") or row["legacy_drug_id"]),
                danh_muc=str(product.get("category") or ""),
                knowledge_type=row["knowledge_type"],
                text=row.get("content_raw") or row.get("content_normalized") or "",
                source=f"{row['knowledge_type']} - {row['legacy_drug_id']}",
                provenance={
                    "source_snapshot_id": row.get("source_snapshot_id"),
                    "provenance_status": row.get("provenance_status"),
                    "source_field": row.get("source_field"),
                    "source_section": row.get("source_section"),
                    "review_status": row.get("review_status"),
                },
            )
            self.chunks.append(chunk)
            self.by_product_type[(chunk.drug_product_id, chunk.knowledge_type)].append(chunk)

        doc_tokens = [tokenize(chunk.text) for chunk in self.chunks]
        df = Counter(token for tokens in doc_tokens for token in set(tokens))
        doc_count = max(1, len(self.chunks))
        self.idf = {token: math.log((doc_count + 1) / (freq + 1)) + 1.0 for token, freq in df.items()}
        self.vectors = [_sparse_vector(tokens, self.idf) for tokens in doc_tokens]
        self.indexes_by_product: dict[str, list[int]] = defaultdict(list)
        self.indexes_by_product_type: dict[tuple[str, str], list[int]] = defaultdict(list)
        for index, chunk in enumerate(self.chunks):
            self.indexes_by_product[chunk.drug_product_id].append(index)
            self.indexes_by_product_type[(chunk.drug_product_id, chunk.knowledge_type)].append(index)

    def resolve_legacy_id(self, legacy_drug_id: str) -> str | None:
        return self.product_id_by_legacy.get(legacy_drug_id)

    def get_catalog_item(self, legacy_drug_id: str) -> DrugCatalogItem | None:
        product = self.products_by_legacy.get(legacy_drug_id)
        return self._to_catalog_item(product) if product else None

    def search_catalog(self, query: str, limit: int = 20) -> list[DrugCatalogItem]:
        query = (query or "").strip()
        if not query:
            return []
        ranked = [
            (self._name_score(query, item.ten_thuoc), item)
            for item in self.catalog_items
        ]
        ranked = [item for item in ranked if item[0] >= 0.20]
        ranked.sort(key=lambda item: (-item[0], normalize_text(item[1].ten_thuoc), item[1].drug_id))
        return [item for _, item in ranked[: max(1, min(limit, 50))]]

    def search_identity_candidates(self, query: str, limit: int = 5) -> list[DrugIdentityCandidate]:
        ranked = [
            DrugIdentityCandidate(item.drug_id, item.ten_thuoc, self._name_score(query, item.ten_thuoc))
            for item in self.catalog_items
        ]
        ranked = [item for item in ranked if item.score >= 0.20]
        ranked.sort(key=lambda item: (-item.score, normalize_text(item.ten_thuoc), item.drug_id))
        return ranked[: max(1, limit)]

    def get_knowledge(self, drug_product_id: str, knowledge_type: str) -> list[V2Chunk]:
        return self.by_product_type.get((drug_product_id, knowledge_type), [])

    def search_active_adverse_effects(
        self, utterance: str, legacy_drug_ids: list[str]
    ) -> list[SideEffectMatchResult]:
        qvec = _sparse_vector(tokenize(utterance), self.idf)
        matches: list[SideEffectMatchResult] = []
        for legacy_drug_id in dict.fromkeys(legacy_drug_ids):
            product_id = self.resolve_legacy_id(legacy_drug_id)
            if not product_id:
                continue
            for index in self.indexes_by_product_type.get((product_id, "ADVERSE_EFFECT"), []):
                score = _cosine(qvec, self.vectors[index])
                if score > 0:
                    chunk = self.chunks[index]
                    matches.append(SideEffectMatchResult(chunk.legacy_drug_id, chunk.ten_thuoc, chunk.text, score))
        matches.sort(key=lambda item: (-item.score, item.drug_id, item.noi_dung))
        return matches[:TOP_K]

    def severity_source(self, legacy_drug_id: str) -> SeveritySource:
        product_id = self.resolve_legacy_id(legacy_drug_id)
        if not product_id:
            return SeveritySource(legacy_drug_id, "", SAFE_DEFAULT_SEVERITY, "REVIEW_REQUIRED", ())
        source_types = ("INDICATION", "ADVERSE_EFFECT")
        chunks = [
            chunk
            for knowledge_type in source_types
            for chunk in self.get_knowledge(product_id, knowledge_type)
        ]
        return SeveritySource(
            legacy_drug_id,
            "\n\n".join(chunk.text for chunk in chunks),
            SAFE_DEFAULT_SEVERITY,
            "REVIEW_REQUIRED",
            source_types if chunks else (),
        )

    def retrieve(self, legacy_drug_id: str, utterance: str) -> AgentKnowledgeLookup:
        started = time.monotonic()
        drug_product_id = self.resolve_legacy_id(legacy_drug_id)
        topic = detect_knowledge_type(utterance)
        if drug_product_id is None:
            return AgentKnowledgeLookup(
                [],
                {
                    "step": "drug_knowledge_v2",
                    "mode": "v2",
                    "path": "fail_closed",
                    "resolution_status": "NOT_FOUND",
                    "legacy_drug_id": legacy_drug_id,
                    "knowledge_type": topic,
                    "duration_ms": (time.monotonic() - started) * 1000,
                },
            )

        path = "rag_v2"
        chunks: list[V2Chunk] = []
        if topic:
            chunks = self.get_knowledge(drug_product_id, topic)
            path = "structured_lookup"

        if not chunks:
            chunks = [item["chunk"] for item in self._search(utterance, drug_product_id, topic)]
            path = "rag_v2"

        results = [self._to_drug_info(chunk, rank=i + 1) for i, chunk in enumerate(chunks[:TOP_K])]
        return AgentKnowledgeLookup(
            results,
            {
                "step": "drug_knowledge_v2",
                "mode": "v2",
                "path": path,
                "legacy_drug_id": legacy_drug_id,
                "drug_product_id": drug_product_id,
                "knowledge_type": topic,
                "result_count": len(results),
                "duration_ms": (time.monotonic() - started) * 1000,
            },
        )

    def _search(self, utterance: str, drug_product_id: str, knowledge_type: str | None) -> list[dict[str, Any]]:
        qvec = _sparse_vector(tokenize(utterance), self.idf)
        if knowledge_type:
            candidate_indexes = self.indexes_by_product_type.get((drug_product_id, knowledge_type), [])
        else:
            candidate_indexes = self.indexes_by_product.get(drug_product_id, [])
        scored = []
        for index in candidate_indexes:
            score = _cosine(qvec, self.vectors[index])
            if score > 0:
                scored.append((score, self.chunks[index]))
        scored.sort(key=lambda item: (-item[0], item[1].knowledge_type, item[1].id))
        return [{"score": score, "chunk": chunk} for score, chunk in scored[:TOP_K]]

    def _to_drug_info(self, chunk: V2Chunk, rank: int) -> DrugInfoResult:
        field_group = KNOWLEDGE_TYPE_TO_FIELD_GROUP.get(chunk.knowledge_type, "tac_dung_phu")
        return DrugInfoResult(
            drug_id=chunk.legacy_drug_id,
            ten_thuoc=chunk.ten_thuoc,
            field_group=field_group,
            noi_dung=chunk.text,
            danh_muc=chunk.danh_muc,
            muc_nghiem_trong="",
            source=f"{chunk.knowledge_type} - {chunk.ten_thuoc}",
            vector_score=None,
            lexical_score=None,
            rrf_score=0.0,
            rank=rank,
        )

    def _to_catalog_item(self, product: dict[str, Any]) -> DrugCatalogItem:
        legacy_metadata = product.get("legacy_metadata") or {}
        return DrugCatalogItem(
            drug_id=str(product["legacy_drug_id"]),
            ten_thuoc=str(product.get("display_name") or product["legacy_drug_id"]),
            dang_thuoc=str(product.get("dosage_form") or ""),
            duong_dung=str(product.get("route") or ""),
            ham_luong=self.strengths_by_product.get(str(product["id"])) or None,
            tong_so_luong=str(product.get("package_text") or "") or None,
            muc_nghiem_trong=legacy_metadata.get("legacy_missed_dose_risk"),
        )

    @staticmethod
    def _name_score(query: str, display_name: str) -> float:
        normalized_query = normalize_text(query)
        normalized_name = normalize_text(display_name)
        if not normalized_query or not normalized_name:
            return 0.0
        if normalized_name in normalized_query:
            return 1.0

        name_tokens = normalized_name.split()
        query_tokens = [token for token in normalized_query.split() if token not in STOPWORDS]
        if not name_tokens or not query_tokens:
            return 0.0

        # Primary signal: significant (>=4 char) words of the product name
        # that the user actually typed, word-for-word. This must dominate
        # the score - two unrelated products must never be able to tie with
        # (or beat) a real word match on raw character similarity alone.
        # Regression: "daflavon" vs "Azaroin 15g" used to score the exact
        # same 0.4210... as "daflavon" vs "Daflavon 450mg Pymepharco 4x15"
        # via plain SequenceMatcher.ratio(), and the tie-break sorts
        # alphabetically - silently picking the wrong drug (TASK-001).
        # >=4 chars (not >=3) because Vietnamese is monosyllabic - short
        # generic syllables (route/form words like "tai" in "nho tai" = ear
        # drops, "vien", "kem"...) collide constantly with unrelated words
        # inside longer sentences ("... khong TON TAI ..." = "does not
        # exist") and must not count as a name match on their own.
        # Score blends how much of the NAME was matched (precision) with
        # how much of the QUERY was matched (recall) so one coincidental
        # short-token hit buried in an otherwise unrelated, longer query
        # cannot cross the identity-candidate threshold by itself.
        significant_name_tokens = [token for token in name_tokens if len(token) >= 4]
        matched_tokens = {token for token in significant_name_tokens if token in query_tokens}
        token_score = 0.0
        if matched_tokens:
            precision = len(matched_tokens) / max(1, len(significant_name_tokens))
            recall = len(matched_tokens) / max(1, len(query_tokens))
            f_score = 2 * precision * recall / max(1e-9, precision + recall)
            token_score = 0.55 + 0.35 * f_score

        # Secondary signal: character-level fuzzy match, kept only as light
        # typo tolerance and scaled well under the token-match band so it
        # can never coincidentally tie with (or outrank) a genuine word
        # match on an unrelated product name. Built only from query tokens
        # of >=4 chars for the same reason as above - short 2-3 char
        # fragments are too common across unrelated names in a ~3500-item
        # catalog to carry any real fuzzy signal.
        fuzzy_query_tokens = [token for token in query_tokens if len(token) >= 4]
        char_ratio = 0.0
        if fuzzy_query_tokens:
            window_size = min(len(name_tokens), len(fuzzy_query_tokens))
            for size in range(1, window_size + 1):
                for start in range(len(fuzzy_query_tokens) - size + 1):
                    window = " ".join(fuzzy_query_tokens[start : start + size])
                    char_ratio = max(char_ratio, SequenceMatcher(None, window, normalized_name).ratio())
        char_score = char_ratio * 0.4

        return max(token_score, char_score)


@lru_cache(maxsize=1)
def get_v2_agent_knowledge_service() -> V2AgentKnowledgeService:
    return V2AgentKnowledgeService()


def warm_v2_agent_knowledge_service() -> dict[str, Any]:
    started = time.monotonic()
    service = get_v2_agent_knowledge_service()
    return {
        "chunks": len(service.chunks),
        "products": len(service.product_id_by_legacy),
        "duration_ms": (time.monotonic() - started) * 1000,
    }


def search_active_adverse_effects(
    db: Session,
    utterance: str,
    legacy_drug_ids: list[str],
    embed_query: Any,
    mode: BackendMode | None = None,
) -> list[SideEffectMatchResult]:
    """Read adverse-effect knowledge from V2 by default; V1 remains rollback-only."""

    selected_mode: BackendMode = mode or get_settings().drug_knowledge_backend
    if selected_mode == "v2":
        return get_v2_agent_knowledge_service().search_active_adverse_effects(utterance, legacy_drug_ids)

    from backend.services.retrieval import search_active_side_effect_chunks

    v1_results = search_active_side_effect_chunks(db, embed_query(utterance), legacy_drug_ids)
    if selected_mode == "shadow":
        get_v2_agent_knowledge_service().search_active_adverse_effects(utterance, legacy_drug_ids)
    return [SideEffectMatchResult(row.drug_id, row.ten_thuoc, row.noi_dung, row.score) for row in v1_results]


def get_severity_source(db: Session, legacy_drug_id: str, mode: BackendMode | None = None) -> SeveritySource:
    """Return V2 severity context without promoting legacy risk metadata to a medical fact."""

    selected_mode: BackendMode = mode or get_settings().drug_knowledge_backend
    if selected_mode == "v2":
        return get_v2_agent_knowledge_service().severity_source(legacy_drug_id)

    from backend.services.retrieval import get_chunks_by_drug_id

    chunks = get_chunks_by_drug_id(db, legacy_drug_id)
    relevant = [chunk for chunk in chunks if chunk.field_group in {"cong_dung", "tac_dung_phu"}]
    fallback = relevant[0].muc_nghiem_trong if relevant else SAFE_DEFAULT_SEVERITY
    source = SeveritySource(
        legacy_drug_id,
        "\n\n".join(chunk.noi_dung for chunk in relevant),
        fallback,
        "LEGACY_COMPATIBILITY" if relevant else "REVIEW_REQUIRED",
        ("cong_dung", "tac_dung_phu") if relevant else (),
    )
    if selected_mode == "shadow":
        get_v2_agent_knowledge_service().severity_source(legacy_drug_id)
    return source


def get_confirmed_drug_knowledge(
    db: Session,
    legacy_drug_id: str,
    utterance: str,
    mode: BackendMode | None = None,
) -> AgentKnowledgeLookup:
    selected_mode: BackendMode = mode or get_settings().drug_knowledge_backend
    started = time.monotonic()
    if selected_mode == "v1":
        from backend.services.retrieval import get_chunks_by_drug_id

        results = get_chunks_by_drug_id(db, legacy_drug_id)
        return AgentKnowledgeLookup(
            results,
            {
                "step": "drug_knowledge_backend",
                "mode": "v1",
                "path": "v1_get_chunks_by_drug_id",
                "legacy_drug_id": legacy_drug_id,
                "result_count": len(results),
                "duration_ms": (time.monotonic() - started) * 1000,
            },
        )

    service = get_v2_agent_knowledge_service()
    if selected_mode == "v2":
        lookup = service.retrieve(legacy_drug_id, utterance)
        return AgentKnowledgeLookup(
            lookup.results,
            {**lookup.trace, "step": "drug_knowledge_backend"},
        )

    from backend.services.retrieval import get_chunks_by_drug_id

    v1_results = get_chunks_by_drug_id(db, legacy_drug_id)
    v2_lookup = service.retrieve(legacy_drug_id, utterance)
    v1_fields = sorted({result.field_group for result in v1_results})
    v2_fields = sorted({result.field_group for result in v2_lookup.results})
    return AgentKnowledgeLookup(
        v1_results,
        {
            "step": "drug_knowledge_backend",
            "mode": "shadow",
            "response_backend": "v1",
            "legacy_drug_id": legacy_drug_id,
            "v1_result_count": len(v1_results),
            "v2_result_count": len(v2_lookup.results),
            "v1_fields": v1_fields,
            "v2_fields": v2_fields,
            "field_match": v1_fields == v2_fields,
            "v2_path": v2_lookup.trace.get("path"),
            "v2_knowledge_type": v2_lookup.trace.get("knowledge_type"),
            "duration_ms": (time.monotonic() - started) * 1000,
        },
    )
