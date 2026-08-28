"""Bounded, deterministic multi-signal drug-image candidate recognition for B-05.

This service deliberately returns *candidates*, never an identified medicine.  It
does not persist query images, OCR output, query embeddings, or patient data and
it is intentionally independent from FastAPI, Agent V2, and the Drug Tool.
"""

from __future__ import annotations

import re
import shutil
import statistics
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

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
OCR_AVAILABLE = "OCR_AVAILABLE"
OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
OCR_FAILED = "OCR_FAILED"
OCR_NOT_RUN = "OCR_NOT_RUN"
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


def _load_pytesseract() -> Any:
    """Import the optional adapter only when an image actually needs OCR."""

    import pytesseract

    return pytesseract


class OptionalTesseractOcrExtractor:
    """Local/offline Tesseract adapter, intentionally optional at runtime.

    Tesseract with the ``vie`` and ``eng`` language packs is the selected
    practical candidate.  The base service remains usable when it is not
    installed; in that case text is an absent/weak signal rather than truth.
    """

    def __init__(self, *, languages: str = "vie+eng", timeout_seconds: float = 5.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("OCR timeout must be positive")
        self._languages = languages
        self._required_languages = frozenset(part for part in languages.split("+") if part)
        self._timeout_seconds = timeout_seconds
        self._runtime: Any | None = None
        self._runtime_status: str | None = None

    def _resolve_runtime(self) -> tuple[Any | None, str]:
        if self._runtime_status is not None:
            return self._runtime, self._runtime_status
        try:
            runtime = _load_pytesseract()
        except ImportError:
            self._runtime_status = OCR_UNAVAILABLE
            return None, self._runtime_status

        command = str(getattr(runtime.pytesseract, "tesseract_cmd", "tesseract"))
        if shutil.which(command) is None:
            self._runtime_status = OCR_UNAVAILABLE
            return None, self._runtime_status
        try:
            installed_languages = frozenset(runtime.get_languages(config=""))
        except runtime.TesseractNotFoundError:
            self._runtime_status = OCR_UNAVAILABLE
            return None, self._runtime_status
        except (OSError, RuntimeError, runtime.TesseractError):
            self._runtime_status = OCR_FAILED
            return None, self._runtime_status
        if not self._required_languages.issubset(installed_languages):
            self._runtime_status = OCR_UNAVAILABLE
            return None, self._runtime_status

        self._runtime = runtime
        self._runtime_status = OCR_AVAILABLE
        return self._runtime, self._runtime_status

    def extract(self, image: Image.Image) -> OcrObservation:
        runtime, runtime_status = self._resolve_runtime()
        if runtime is None:
            return OcrObservation(text="", status=runtime_status)
        try:
            text = runtime.image_to_string(
                image,
                lang=self._languages,
                timeout=self._timeout_seconds,
            )
        except runtime.TesseractNotFoundError:
            self._runtime = None
            self._runtime_status = OCR_UNAVAILABLE
            return OcrObservation(text="", status=OCR_UNAVAILABLE)
        except (OSError, RuntimeError, runtime.TesseractError):
            return OcrObservation(text="", status=OCR_FAILED)
        return OcrObservation(text=text, status=OCR_AVAILABLE)


class NoopOcrExtractor:
    """Explicit no-text adapter for tests and environments without OCR."""

    def extract(self, image: Image.Image) -> OcrObservation:  # noqa: ARG002 - protocol boundary
        return OcrObservation(text="", status=OCR_UNAVAILABLE)


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
    # Fix_drug_OCR_2.md Part A: True only when this candidate's OCR name
    # match came from a single-token identity segment (~52.5% of the
    # catalog -- e.g. "Snapcef" alone before "16mg") AND the catalog
    # itself shows >=1 OTHER product sharing that exact (token, strength)
    # pair. A single generic brand token is not independently reliable
    # identity evidence when the catalog cannot tell which of 2+ real
    # products it actually names -- see _decide()'s SINGLE_TOKEN_* gate.
    single_token_non_unique: bool = False


@dataclass(frozen=True)
class RecognitionResult:
    outcome: str
    candidates: tuple[RecognitionCandidate, ...]
    evidence_summary: tuple[str, ...]
    quality_gate: ImageQuality
    model_version: str
    recognition_version: str = RECOGNITION_VERSION
    confirmation_required: bool = True
    ocr_status: str = OCR_NOT_RUN
    ocr_signal_count: int = 0
    decision_reason_codes: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class RecognitionObservability:
    """Safe structured evidence for logs/traces; raw OCR and vectors stay absent."""

    quality_status: str
    quality_reasons: tuple[str, ...]
    ocr_status: str
    ocr_signal_count: int
    internal_top1_drug_product_id: str | None
    internal_top1_visual_score: float | None
    internal_top2_visual_score: float | None
    top1_top2_margin: float | None
    ocr_name_match: bool
    # Fix_drug_OCR_2.md Part A: True only when the name match came from a
    # single-token identity segment (~52.5% of the catalog) -- a weaker
    # signal that alone never reaches HIGH_EVIDENCE_MATCH; see decision_reason_codes
    # for whether it was actually corroborated (SINGLE_TOKEN_NAME_MATCH +
    # HIGH_EVIDENCE_CONFIRMED) or degraded (SINGLE_TOKEN_NEEDS_CORROBORATION).
    ocr_single_token_name_match: bool
    ocr_single_token_non_unique: bool
    ocr_strength_match: bool
    ocr_conflict: bool
    decision_reason_codes: tuple[str, ...]
    recognizer_outcome: str


def recognition_observability(result: RecognitionResult) -> RecognitionObservability:
    """Project a recognition result into bounded, non-patient-readable telemetry."""

    visual_order = sorted(result.candidates, key=lambda candidate: candidate.visual_rank)
    top1 = visual_order[0] if visual_order else None
    top2 = visual_order[1] if len(visual_order) > 1 else None
    decision_top = result.candidates[0] if result.candidates else None
    evidence_fields = {signal.field for signal in decision_top.text_evidence} if decision_top else set()
    top1_score = top1.visual_score if top1 else None
    top2_score = top2.visual_score if top2 else None
    return RecognitionObservability(
        quality_status=result.quality_gate.status,
        quality_reasons=result.quality_gate.reason_codes,
        ocr_status=result.ocr_status,
        ocr_signal_count=result.ocr_signal_count,
        internal_top1_drug_product_id=top1.drug_product_id if top1 else None,
        internal_top1_visual_score=top1_score,
        internal_top2_visual_score=top2_score,
        top1_top2_margin=(top1_score - top2_score) if top1_score is not None and top2_score is not None else None,
        ocr_name_match="product_name_match" in evidence_fields
        or "product_name_match_single_token" in evidence_fields,
        ocr_single_token_name_match="product_name_match_single_token" in evidence_fields,
        ocr_single_token_non_unique=bool(decision_top and decision_top.single_token_non_unique),
        ocr_strength_match="strength_match" in evidence_fields,
        ocr_conflict=bool(decision_top and decision_top.conflicts),
        decision_reason_codes=result.decision_reason_codes,
        recognizer_outcome=result.outcome,
    )


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
            reasons = ("QUALITY_FAILED", *quality.reason_codes)
            return RecognitionResult(
                outcome=INSUFFICIENT_EVIDENCE,
                candidates=(),
                evidence_summary=reasons,
                quality_gate=quality,
                model_version=self._embedder.embedding_version,
                ocr_status=OCR_NOT_RUN,
                decision_reason_codes=reasons,
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
        candidates = _rerank(session, visual, metadata, signals)
        duplicate_ambiguous = _has_unresolved_duplicate_ambiguity(session, candidates)
        outcome, reasons = _decide(candidates, signals, duplicate_ambiguous, quality.status)
        availability_reasons = (
            (observation.status,) if observation.status in {OCR_UNAVAILABLE, OCR_FAILED} else ()
        )
        decision_reasons = tuple(dict.fromkeys((*availability_reasons, *reasons)))
        return RecognitionResult(
            outcome=outcome,
            candidates=tuple(candidates),
            evidence_summary=(f"OCR_STATUS:{observation.status}", *reasons),
            quality_gate=quality,
            model_version=self._embedder.embedding_version,
            ocr_status=observation.status,
            ocr_signal_count=len(signals),
            decision_reason_codes=decision_reasons,
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
    session: Session,
    visual: Sequence[DrugImageSearchResult],
    metadata: dict[str, ProductMetadata],
    signals: Sequence[TextSignal],
) -> list[RecognitionCandidate]:
    """Apply documented baseline heuristics; every contribution remains visible."""

    observed_text = " ".join(signal.normalized_value for signal in signals if signal.field == "product_name_candidate")
    observed_strengths = {signal.normalized_value for signal in signals if signal.field == "strength_candidate"}
    name_matches = {
        item.drug_product_id: _name_match(metadata[item.drug_product_id].display_name, observed_text)
        for item in visual
        if item.drug_product_id in metadata
    }
    any_name_match = any(score >= 1.0 for score, _tokens in name_matches.values())
    prepared: list[RecognitionCandidate] = []
    for item in visual:
        product = metadata.get(item.drug_product_id)
        if product is None:
            continue
        text_evidence: list[TextSignal] = []
        conflicts: list[str] = []
        name_match, identity_token_count = name_matches.get(item.drug_product_id, (0.0, 0))
        # Fix_drug_OCR_2.md Part A: a single-token identity match (~52.5% of
        # the catalog) is a materially weaker signal than a multi-token
        # one -- surfaced as its own text_evidence field so _decide() can
        # require additional corroboration before it may contribute to
        # HIGH_EVIDENCE_MATCH, instead of treating it the same as a robust
        # multi-token brand match.
        single_token_non_unique = False
        if name_match >= 1.0:
            if identity_token_count == 1:
                text_evidence.append(
                    TextSignal(
                        "product_name_match_single_token",
                        product.display_name,
                        normalize_for_match(product.display_name),
                    )
                )
                identity_tokens = _identity_segment_tokens(product.display_name)
                single_token_non_unique = _is_single_token_non_unique(
                    session, identity_tokens[0], observed_strengths
                )
            else:
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
                single_token_non_unique=single_token_non_unique,
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


def _identity_segment_tokens(display_name: str) -> tuple[str, ...]:
    """The pre-strength brand/name tokens _name_match compares OCR text
    against. Shared with the catalog-uniqueness audit (Fix_drug_OCR_2.md
    Part A section 1/5) so both use the exact same extraction."""

    strength = _STRENGTH_PATTERN.search(display_name)
    identity_segment = display_name[: strength.start()] if strength else display_name
    return _meaningful_tokens(identity_segment)


def _name_match(display_name: str, observed_text: str) -> tuple[float, int]:
    """Return (score, identity_token_count). Score is 1.0 for a match, 0.0
    otherwise; the token count lets the caller (_rerank) tell a robust
    multi-token match apart from a single-token one, which ~52.5% of the
    catalog reduces to (Fix_drug_OCR_2.md section 1) and which alone is
    not independently reliable identity evidence -- see _decide()."""

    candidate = _identity_segment_tokens(display_name)
    if not observed_text or not candidate:
        return 0.0, len(candidate)
    # Catalog display names append manufacturer and pack-size text after the
    # branded name. The package front may legitimately show only that branded
    # name, so compare the OCR text with the pre-strength identity segment.
    # OCR remains corroboration only: _decide still requires visual Top-1 and
    # rejects strength/name conflicts before HIGH_EVIDENCE_MATCH.
    observed = set(observed_text.split())
    matched = sum(token in observed for token in candidate)
    if matched == len(candidate):
        return 1.0, len(candidate)
    if len(candidate) >= 2 and matched / len(candidate) >= 0.75:
        return 1.0, len(candidate)
    return 0.0, len(candidate)


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


# Fix_drug_OCR_2.md Part A section 5 (catalog-derived uniqueness, not a
# hand-maintained keyword blacklist). Maps (single identity token,
# normalized strength) -> how many DISTINCT real catalog products share
# that exact pair. Computed once by scanning the whole `drug_product`
# table (~3556 rows, sub-second) and cached process-wide for the process
# lifetime -- the same "pay once, not per request" convention already
# used for the OpenCLIP embedder and the OCR runtime probe in this
# module. A catalog change only takes effect after a process restart,
# same as those two.
_SINGLE_TOKEN_STRENGTH_INDEX: dict[tuple[str, str], int] | None = None


def _single_token_strength_index(session: Session) -> dict[tuple[str, str], int]:
    global _SINGLE_TOKEN_STRENGTH_INDEX
    if _SINGLE_TOKEN_STRENGTH_INDEX is not None:
        return _SINGLE_TOKEN_STRENGTH_INDEX
    index: dict[tuple[str, str], int] = {}
    for product in session.scalars(select(DrugProduct)).all():
        tokens = _identity_segment_tokens(product.display_name)
        if len(tokens) != 1:
            continue
        source = " ".join(part for part in (product.strength_text, product.display_name) if part)
        for signal in extract_structured_signals(source):
            if signal.field != "strength_candidate":
                continue
            key = (tokens[0], signal.normalized_value)
            index[key] = index.get(key, 0) + 1
    _SINGLE_TOKEN_STRENGTH_INDEX = index
    return index


def _is_single_token_non_unique(session: Session, token: str, strengths: set[str]) -> bool:
    """True when the catalog itself shows >=1 OTHER real product sharing
    this exact (single identity token, strength) pair -- the shape this
    task's own catalog audit found for 165 tokens (e.g. two different
    "Acyclovir 200mg" pack-size SKUs). In that case OCR reading the brand
    word plus a matching strength cannot tell the recognizer WHICH of the
    real candidates it actually names, so it must not count as
    independently reliable identity evidence on its own."""

    if not strengths:
        return False
    index = _single_token_strength_index(session)
    return any(index.get((token, strength), 0) > 1 for strength in strengths)


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
        signal.field in {"product_name_match", "product_name_match_single_token", "strength_match", "ingredient_match"}
        for signal in top.text_evidence
    )


def _decide(
    candidates: Sequence[RecognitionCandidate],
    signals: Sequence[TextSignal],
    duplicate_ambiguous: bool,
    quality_status: str,
) -> tuple[str, tuple[str, ...]]:
    if quality_status != QUALITY_PASS:
        return INSUFFICIENT_EVIDENCE, ("QUALITY_FAILED",)
    if not candidates:
        return INSUFFICIENT_EVIDENCE, ("INSUFFICIENT_VISUAL_EVIDENCE",)
    top = candidates[0]
    if top.conflicts:
        return INSUFFICIENT_EVIDENCE, ("OCR_HARD_CONFLICT", *top.conflicts)
    strong_text = any(signal.field == "product_name_match" for signal in top.text_evidence)
    # Fix_drug_OCR_2.md Part A: a single-token identity match (~52.5% of the
    # catalog reduces to exactly one meaningful token before its strength,
    # e.g. "Snapcef") is NOT independently reliable identity evidence on its
    # own -- it must be joined by at least one other real, already-computed
    # corroborating signal (strength_match or ingredient_match; no new
    # fuzzy/display-name fallback was added) AND the catalog must not show
    # >=1 OTHER real product sharing that exact (token, strength) pair.
    single_token_text = any(signal.field == "product_name_match_single_token" for signal in top.text_evidence)
    strength_matched = any(signal.field == "strength_match" for signal in top.text_evidence)
    ingredient_matched = any(signal.field == "ingredient_match" for signal in top.text_evidence)
    single_token_corroborated = single_token_text and (strength_matched or ingredient_matched) and not top.single_token_non_unique
    has_any_catalog_match = any(candidate.text_evidence for candidate in candidates)
    # No cosine threshold is used.  High evidence remains bounded to the visual
    # Top-1 plus independent text corroboration; reranking a lower visual result
    # cannot silently turn a visual/text disagreement into a high-confidence claim.
    if (strong_text or single_token_corroborated) and top.visual_rank == 1 and not duplicate_ambiguous:
        reasons = ["SINGLE_TOKEN_NAME_MATCH"] if single_token_text else ["OCR_NAME_MATCH"]
        if strength_matched:
            reasons.append("OCR_STRENGTH_MATCH")
        if single_token_text and ingredient_matched:
            reasons.append("INGREDIENT_MATCH")
        reasons.append("HIGH_EVIDENCE_CONFIRMED")
        return HIGH_EVIDENCE_MATCH, tuple(reasons)
    if signals and not has_any_catalog_match:
        return INSUFFICIENT_EVIDENCE, ("INSUFFICIENT_VISUAL_EVIDENCE",)
    if duplicate_ambiguous:
        return AMBIGUOUS_MATCH, ("DUPLICATE_CONTENT_AMBIGUITY",)
    if single_token_text and not single_token_corroborated:
        # Real text evidence exists (the brand token matched) but it is
        # deliberately not enough alone -- degrade to AMBIGUOUS_MATCH
        # rather than inventing confidence (task's own explicit rule),
        # never silently indistinguishable from a plain no-signal case.
        reasons = ["SINGLE_TOKEN_NEEDS_CORROBORATION"]
        if top.single_token_non_unique:
            reasons.append("NON_UNIQUE_SINGLE_TOKEN")
        return AMBIGUOUS_MATCH, tuple(reasons)
    return AMBIGUOUS_MATCH, ("AMBIGUOUS_VISUAL_ONLY",)


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
