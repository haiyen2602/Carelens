"""Bounded, deterministic multi-signal drug-image candidate recognition for B-05.

This service deliberately returns *candidates*, never an identified medicine.  It
does not persist query images, OCR output, query embeddings, or patient data and
it is intentionally independent from FastAPI, Agent V2, and the Drug Tool.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageChops, ImageOps, ImageStat
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DrugImage, DrugProduct, DrugProductIngredient, Ingredient
from backend.services.drug_image_retrieval import DrugImageSearchResult, ImageEmbedder, search_similar_drug_images

RECOGNITION_VERSION = "drug-recognition-v1"
TOP_K = 10
QUALITY_PASS = "PASS"
QUALITY_RETAKE = "RETAKE_RECOMMENDED"
QUALITY_REJECT = "REJECT"
HIGH_EVIDENCE_MATCH = "HIGH_EVIDENCE_MATCH"
AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
OCR_SOURCE = "OCR"
RERANKING_POLICY = "deterministic-baseline-heuristic-v1"

_STRENGTH_PATTERN = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(mcg|µg|ug|mg|ml|g|%)(?!\w)", re.IGNORECASE)
_REGISTRATION_PATTERN = re.compile(
    r"\b(?:sdk|reg(?:istration)?|vd|vn)\s*[-:#.]?\s*([a-z0-9][a-z0-9-]{3,})\b", re.IGNORECASE
)
_MANUFACTURER_PATTERN = re.compile(r"\b(?:manufacturer|nhà\s*sản\s*xuất|nsx)\s*[:\-]\s*([^\n]{2,80})", re.IGNORECASE)
_DOSAGE_WORDS = frozenset({"tablet", "capsule", "vien", "nang", "nen", "hop", "chai", "goi", "ong", "solution"})


@dataclass(frozen=True)
class ImageQuality:
    status: str
    reason_codes: tuple[str, ...]
    width: int | None
    height: int | None


@dataclass(frozen=True)
class TextSignal:
    """A bounded, structured observation from visible text; raw OCR is omitted."""

    field: str
    value: str
    normalized_value: str
    source: str = OCR_SOURCE
    quality: str = "OBSERVED"


@dataclass(frozen=True)
class OcrObservation:
    text: str
    status: str


class OcrExtractor(Protocol):
    def extract(self, image: Image.Image) -> OcrObservation: ...


class OptionalTesseractOcrExtractor:
    """Local/offline Tesseract adapter, intentionally optional at runtime.

    Tesseract with the ``vie`` and ``eng`` language packs is the selected
    practical candidate.  The base service remains usable when it is not
    installed; in that case text is an absent/weak signal rather than truth.
    """

    def __init__(self, *, languages: str = "vie+eng") -> None:
        self._languages = languages

    def extract(self, image: Image.Image) -> OcrObservation:
        try:
            import pytesseract
        except ImportError:
            return OcrObservation(text="", status="OCR_UNAVAILABLE")
        try:
            text = pytesseract.image_to_string(image, lang=self._languages)
        except (OSError, RuntimeError, pytesseract.TesseractError, pytesseract.TesseractNotFoundError):
            return OcrObservation(text="", status="OCR_UNAVAILABLE")
        return OcrObservation(text=text, status="OCR_OK")


class NoopOcrExtractor:
    """Explicit no-text adapter for tests and environments without OCR."""

    def extract(self, image: Image.Image) -> OcrObservation:  # noqa: ARG002 - protocol boundary
        return OcrObservation(text="", status="OCR_NOT_CONFIGURED")


@dataclass(frozen=True)
class ProductMetadata:
    drug_product_id: str
    display_name: str
    strength_text: str | None
    dosage_form: str | None
    ingredient_names: tuple[str, ...]


@dataclass(frozen=True)
class RecognitionCandidate:
    rank: int
    visual_rank: int
    drug_product_id: str
    drug_image_id: str
    product_display_name: str
    visual_score: float
    fused_score: float
    text_evidence: tuple[TextSignal, ...]
    conflicts: tuple[str, ...]


@dataclass(frozen=True)
class RecognitionResult:
    outcome: str
    candidates: tuple[RecognitionCandidate, ...]
    evidence_summary: tuple[str, ...]
    quality_gate: ImageQuality
    model_version: str
    recognition_version: str = RECOGNITION_VERSION
    confirmation_required: bool = True

    def confirmation_prompt(self) -> str:
        """Return user-safe candidate wording, never a medicine assertion."""

        if self.outcome == HIGH_EVIDENCE_MATCH and self.candidates:
            return (
                "Ảnh có vẻ phù hợp nhất với: "
                f"{self.candidates[0].product_display_name}. "
                "Bạn xác nhận đây có phải thuốc của bạn không?"
            )
        if self.outcome == AMBIGUOUS_MATCH and self.candidates:
            options = "\n".join(f"- {item.product_display_name}" for item in self.candidates[:3])
            return f"Ảnh có thể là một trong các thuốc sau:\n{options}\nHãy chọn thuốc đúng."
        return "Tôi chưa xác định đủ chắc chắn. Hãy chụp lại rõ mặt trước của hộp thuốc hoặc nhập tên thuốc."


def normalize_visible_text(value: str) -> str:
    """Normalize for comparison while retaining meaningful strength/unit tokens."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[\t\r\f\v]+", " ", normalized)
    normalized = re.sub(r"[ ]{2,}", " ", normalized)
    return normalized.strip()


def normalize_for_match(value: str) -> str:
    """Diacritic-aware comparison form; it is not displayed or persisted."""

    normalized = normalize_visible_text(value)
    decomposed = unicodedata.normalize("NFD", normalized)
    without_diacritics = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^\w%]+", " ", without_diacritics).strip()


def extract_structured_signals(visible_text: str) -> tuple[TextSignal, ...]:
    """Extract only text that appeared in OCR; no catalog-derived values enter here."""

    signals: list[TextSignal] = []
    normalized = normalize_visible_text(visible_text)
    seen: set[tuple[str, str]] = set()

    def add(field: str, value: str) -> None:
        compact = " ".join(value.split())
        comparison = normalize_for_match(compact)
        key = (field, comparison)
        if compact and comparison and key not in seen:
            seen.add(key)
            signals.append(TextSignal(field=field, value=compact, normalized_value=comparison))

    for match in _STRENGTH_PATTERN.finditer(normalized):
        amount = match.group(1).replace(",", ".")
        unit = {"µg": "mcg", "ug": "mcg"}.get(match.group(2).casefold(), match.group(2).casefold())
        add("strength_candidate", f"{amount} {unit}")
    for match in _REGISTRATION_PATTERN.finditer(normalized):
        add("registration_number_candidate", match.group(1))
    for match in _MANUFACTURER_PATTERN.finditer(visible_text):
        add("manufacturer_candidate", match.group(1))
    for line in visible_text.splitlines():
        comparison = normalize_for_match(line)
        tokens = [token for token in comparison.split() if any(char.isalpha() for char in token)]
        if tokens and sum(len(token) for token in tokens) >= 4:
            add("product_name_candidate", line)
    return tuple(signals)


def inspect_image_quality(image: Image.Image, *, minimum_dimension: int = 64) -> ImageQuality:
    """Run small, deterministic checks.  This is not a drug-confidence score."""

    normalized: Image.Image | None = None
    try:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        normalized.load()
    except (OSError, ValueError):
        if normalized is not None:
            normalized.close()
        return ImageQuality(QUALITY_REJECT, ("IMAGE_UNREADABLE",), None, None)
    assert normalized is not None
    try:
        width, height = normalized.size
        reasons: list[str] = []
        if width < minimum_dimension or height < minimum_dimension:
            reasons.append("IMAGE_TOO_SMALL")
        ratio = max(width, height) / min(width, height) if min(width, height) else float("inf")
        if ratio > 5:
            reasons.append("IMAGE_EXTREME_ASPECT_RATIO")
        grayscale = normalized.convert("L")
        try:
            mean = ImageStat.Stat(grayscale).mean[0]
            if mean < 12:
                reasons.append("IMAGE_TOO_DARK")
            elif mean > 245:
                reasons.append("IMAGE_TOO_BRIGHT")
            if _mean_absolute_gradient(grayscale) < 2.0:
                reasons.append("IMAGE_TOO_BLURRY")
        finally:
            grayscale.close()
        if "IMAGE_TOO_SMALL" in reasons or "IMAGE_EXTREME_ASPECT_RATIO" in reasons:
            status = QUALITY_REJECT
        elif reasons:
            status = QUALITY_RETAKE
        else:
            status = QUALITY_PASS
        return ImageQuality(status, tuple(reasons), width, height)
    finally:
        normalized.close()


def _mean_absolute_gradient(image: Image.Image) -> float:
    """Return a native Pillow edge-energy proxy without a Python pixel loop."""

    width, height = image.size
    if width < 2 or height < 2:
        return 0.0
    horizontal = ImageChops.difference(image, ImageChops.offset(image, -1, 0))
    vertical = ImageChops.difference(image, ImageChops.offset(image, 0, -1))
    try:
        return (ImageStat.Stat(horizontal).mean[0] + ImageStat.Stat(vertical).mean[0]) / 2
    finally:
        horizontal.close()
        vertical.close()


class DrugImageRecognizer:
    """Use B-04 Top-K retrieval then explainably rerank only those candidates."""

    def __init__(self, embedder: ImageEmbedder, *, ocr: OcrExtractor | None = None, top_k: int = TOP_K) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self._embedder = embedder
        self._ocr = ocr or NoopOcrExtractor()
        self._top_k = top_k

    def recognize(self, session: Session, image: Image.Image) -> RecognitionResult:
        quality = inspect_image_quality(image)
        if quality.status == QUALITY_REJECT:
            return RecognitionResult(
                outcome=INSUFFICIENT_EVIDENCE,
                candidates=(),
                evidence_summary=("QUALITY_GATE_BLOCKED_RETRIEVAL", *quality.reason_codes),
                quality_gate=quality,
                model_version=self._embedder.embedding_version,
            )
        try:
            observation = self._ocr.extract(image)
        except (OSError, RuntimeError, ValueError):
            observation = OcrObservation(text="", status="OCR_FAILED")
        signals = extract_structured_signals(observation.text)
        query_embedding = self._embedder.embed_image(image)
        visual = search_similar_drug_images(
            session,
            query_embedding,
            embedding_model=self._embedder.embedding_model,
            embedding_version=self._embedder.embedding_version,
            top_k=self._top_k,
        )
        metadata = _load_product_metadata(session, (item.drug_product_id for item in visual))
        candidates = _rerank(visual, metadata, signals)
        duplicate_ambiguous = _has_unresolved_duplicate_ambiguity(session, candidates)
        outcome, reasons = _decide(candidates, signals, duplicate_ambiguous, quality.status)
        return RecognitionResult(
            outcome=outcome,
            candidates=tuple(candidates),
            evidence_summary=(f"OCR_STATUS:{observation.status}", *reasons),
            quality_gate=quality,
            model_version=self._embedder.embedding_version,
        )


def _load_product_metadata(session: Session, product_ids: Iterable[str]) -> dict[str, ProductMetadata]:
    unique_ids = tuple(dict.fromkeys(product_ids))
    if not unique_ids:
        return {}
    products = session.scalars(select(DrugProduct).where(DrugProduct.id.in_(unique_ids))).all()
    ingredients_by_product: dict[str, list[str]] = {product.id: [] for product in products}
    ingredient_rows = session.execute(
        select(DrugProductIngredient.drug_product_id, Ingredient.name)
        .join(Ingredient, Ingredient.id == DrugProductIngredient.ingredient_id)
        .where(DrugProductIngredient.drug_product_id.in_(unique_ids))
    ).all()
    for product_id, ingredient_name in ingredient_rows:
        ingredients_by_product.setdefault(product_id, []).append(ingredient_name)
    return {
        product.id: ProductMetadata(
            drug_product_id=product.id,
            display_name=product.display_name,
            strength_text=product.strength_text,
            dosage_form=product.dosage_form,
            ingredient_names=tuple(sorted(ingredients_by_product.get(product.id, []))),
        )
        for product in products
    }


def _rerank(
    visual: Sequence[DrugImageSearchResult], metadata: dict[str, ProductMetadata], signals: Sequence[TextSignal]
) -> list[RecognitionCandidate]:
    """Apply documented baseline heuristics; every contribution remains visible."""

    observed_text = " ".join(signal.normalized_value for signal in signals if signal.field == "product_name_candidate")
    observed_strengths = {signal.normalized_value for signal in signals if signal.field == "strength_candidate"}
    name_matches = {
        item.drug_product_id: _name_match(metadata[item.drug_product_id].display_name, observed_text)
        for item in visual
        if item.drug_product_id in metadata
    }
    any_name_match = any(score >= 1.0 for score in name_matches.values())
    prepared: list[RecognitionCandidate] = []
    for item in visual:
        product = metadata.get(item.drug_product_id)
        if product is None:
            continue
        text_evidence: list[TextSignal] = []
        conflicts: list[str] = []
        name_match = name_matches.get(item.drug_product_id, 0.0)
        if name_match >= 1.0:
            text_evidence.append(
                TextSignal("product_name_match", product.display_name, normalize_for_match(product.display_name))
            )
        elif any_name_match:
            conflicts.append("NAME_CONFLICT")
        product_strengths = _strengths_for_product(product)
        strength_match = bool(observed_strengths & product_strengths)
        if strength_match:
            text_evidence.append(
                TextSignal(
                    "strength_match",
                    sorted(observed_strengths & product_strengths)[0],
                    sorted(observed_strengths & product_strengths)[0],
                )
            )
        elif observed_strengths and product_strengths:
            conflicts.append("STRENGTH_CONFLICT")
        ingredient_match = _ingredient_match(product.ingredient_names, observed_text)
        if ingredient_match:
            text_evidence.append(
                TextSignal("ingredient_match", ingredient_match, normalize_for_match(ingredient_match))
            )
        # Baseline heuristic, intentionally explicit rather than a learned confidence score.
        fused = (
            item.similarity_score
            + (0.20 * name_match)
            + (0.08 if strength_match else 0.0)
            + (0.12 if ingredient_match else 0.0)
        )
        # A hard conflict must not be able to outrank a conflict-free candidate,
        # regardless of cosine range. The score remains explanatory only; the
        # sort key below enforces that safety invariant.
        fused -= float(len(conflicts))
        prepared.append(
            RecognitionCandidate(
                rank=0,
                visual_rank=item.rank,
                drug_product_id=item.drug_product_id,
                drug_image_id=item.drug_image_id,
                product_display_name=product.display_name,
                visual_score=item.similarity_score,
                fused_score=fused,
                text_evidence=tuple(text_evidence),
                conflicts=tuple(conflicts),
            )
        )
    ordered = sorted(
        prepared,
        key=lambda item: (
            bool(item.conflicts),
            -item.fused_score,
            -item.visual_score,
            item.drug_product_id,
            item.drug_image_id,
        ),
    )
    return [RecognitionCandidate(**{**item.__dict__, "rank": index}) for index, item in enumerate(ordered, start=1)]


def _name_match(display_name: str, observed_text: str) -> float:
    if not observed_text:
        return 0.0
    candidate = _meaningful_tokens(display_name)
    observed = set(observed_text.split())
    if not candidate:
        return 0.0
    matched = sum(token in observed for token in candidate)
    if matched == len(candidate):
        return 1.0
    if len(candidate) >= 2 and matched / len(candidate) >= 0.75:
        return 1.0
    return 0.0


def _meaningful_tokens(value: str) -> tuple[str, ...]:
    without_strength = _STRENGTH_PATTERN.sub(" ", normalize_for_match(value))
    return tuple(token for token in without_strength.split() if len(token) >= 3 and token not in _DOSAGE_WORDS)


def _strengths_for_product(product: ProductMetadata) -> set[str]:
    source = " ".join(part for part in (product.strength_text, product.display_name) if part)
    return {
        signal.normalized_value for signal in extract_structured_signals(source) if signal.field == "strength_candidate"
    }


def _ingredient_match(ingredients: Sequence[str], observed_text: str) -> str | None:
    for ingredient in ingredients:
        tokens = _meaningful_tokens(ingredient)
        if tokens and all(token in observed_text.split() for token in tokens):
            return ingredient
    return None


def _has_unresolved_duplicate_ambiguity(session: Session, candidates: Sequence[RecognitionCandidate]) -> bool:
    if not candidates:
        return False
    image = session.get(DrugImage, candidates[0].drug_image_id)
    if image is None:
        return False
    product_ids = session.scalars(
        select(DrugImage.drug_product_id)
        .where(DrugImage.normalized_checksum_sha256 == image.normalized_checksum_sha256)
        .distinct()
    ).all()
    if len(product_ids) <= 1:
        return False
    top = candidates[0]
    return not any(
        signal.field in {"product_name_match", "strength_match", "ingredient_match"} for signal in top.text_evidence
    )


def _decide(
    candidates: Sequence[RecognitionCandidate],
    signals: Sequence[TextSignal],
    duplicate_ambiguous: bool,
    quality_status: str,
) -> tuple[str, tuple[str, ...]]:
    if quality_status != QUALITY_PASS:
        return INSUFFICIENT_EVIDENCE, ("QUALITY_GATE_RETAKE_RECOMMENDED",)
    if not candidates:
        return INSUFFICIENT_EVIDENCE, ("NO_VISUAL_CANDIDATES",)
    top = candidates[0]
    if top.conflicts:
        return INSUFFICIENT_EVIDENCE, ("TOP_CANDIDATE_HAS_HARD_CONFLICT", *top.conflicts)
    strong_text = any(signal.field == "product_name_match" for signal in top.text_evidence)
    has_any_catalog_match = any(candidate.text_evidence for candidate in candidates)
    # No cosine threshold is used.  High evidence remains bounded to the visual
    # Top-1 plus independent text corroboration; reranking a lower visual result
    # cannot silently turn a visual/text disagreement into a high-confidence claim.
    if strong_text and top.visual_rank == 1 and not duplicate_ambiguous:
        return HIGH_EVIDENCE_MATCH, ("TEXT_CORROBORATED_TOP_VISUAL_CANDIDATE", RERANKING_POLICY)
    if signals and not has_any_catalog_match:
        return INSUFFICIENT_EVIDENCE, ("VISIBLE_TEXT_DOES_NOT_CORROBORATE_CATALOG_CANDIDATES",)
    if duplicate_ambiguous:
        return AMBIGUOUS_MATCH, ("DUPLICATE_REFERENCE_CONTENT_REQUIRES_CONFIRMATION",)
    return AMBIGUOUS_MATCH, ("CANDIDATE_REQUIRES_USER_CONFIRMATION",)


def percentile(values: Sequence[float], percentile_value: int) -> float | None:
    """Small reporting helper using linear interpolation, not recognition logic."""

    if not values:
        return None
    if not 0 <= percentile_value <= 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile_value / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None
