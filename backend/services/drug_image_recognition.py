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

# Fix_drug_OCR_3.md: catalog identity/pack/descriptive parsing. Common
# Vietnamese pharma packaging-count words (full and already-transliterated
# forms) plus the bare abbreviation "v" (viên) and "liều" (dose) -- audited
# against the real 3556-row catalog (section 2 of the report): with these,
# only 21 products (0.6%) have neither a strength nor a recognizable pack
# pattern at all.
_PACK_UNIT_WORDS = (
    "hộp", "hop", "ống", "ong", "viên", "vien", "chai", "lọ", "lo",
    "vỉ", "vi", "gói", "goi", "tuýp", "tuyp", "liều", "lieu",
)
_PACK_UNIT_ALT = "|".join(_PACK_UNIT_WORDS)
# PR #165 review: the first alternative originally had TWO independent
# `\s*` quantifiers straddling an optional (possibly-empty) unit-word
# group -- `\d+\s*(?:UNIT|v)?\s*[xX]`. Once that group matches empty, the
# two `\s*`s become adjacent and can trade off consuming the SAME run of
# whitespace in any split, and when the eventual `[xX]` never matches
# (e.g. a digit followed by a very long whitespace run and no "x"), the
# engine explores every split before giving up -- confirmed empirically
# (not just theoretically) as real O(n^2) backtracking: ~61s for a
# 100,000-char adversarial string, scaling test showed time/n^2 constant
# across n=500..8000. Not reachable by attacker input TODAY (this pattern
# only ever runs against short, trusted catalog `display_name` values,
# never raw OCR text -- confirmed by grep), but a real latent bug is
# still a real bug. Fixed by folding the leading whitespace INTO the
# optional group so there is only ever one independent `\s*` per gap
# (`(?:\s*(?:UNIT|v))?` is tried as a single atomic optional unit, not
# two separately-backtrackable quantifiers).
_PACK_PATTERN = re.compile(
    r"\b\d+(?:\s*(?:" + _PACK_UNIT_ALT + r"|v))?\s*[xX]\s*\d+(?:\s*(?:ml|mg|g|" + _PACK_UNIT_ALT + r"|v))?\b"
    r"|\b(?:" + _PACK_UNIT_ALT + r")\s+\d+\s*(?:ml|mg|g|" + _PACK_UNIT_ALT + r")?\b"
    r"|\b\d+\s*(?:" + _PACK_UNIT_ALT + r"|v)\b",
    re.IGNORECASE,
)
# A delimiter surrounded by whitespace on BOTH sides marks a real
# separator between product identity/pack and free-form descriptive/
# marketing text (e.g. "LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ").
# A delimiter with NO surrounding space is far more often part of a
# compound brand token itself ("Agi-neurin", "Agilosart-h") or a
# combo-strength notation ("500/125") -- confirmed against the real
# catalog (report section 2) -- and must never be split on.
_DESCRIPTIVE_SPLIT_PATTERN = re.compile(r"\s[-,:]\s")
_TRAILING_PAREN_PATTERN = re.compile(r"\s*\([^()]*\)\s*$")
# "P/H", "P.H", "P.H." -> "PH" before generic normalization, so a
# meaningful 2-letter brand qualifier survives as one token instead of
# being split into two 1-character fragments and dropped -- section 10.
_ABBREVIATION_JOIN_PATTERN = re.compile(r"\b([A-Za-zĐđ])[/.]([A-Za-zĐđ])\.?(?!\w)")
# Brand qualifiers this short are still meaningful identity evidence
# (section 4's preserve-list) even though they fall under the general
# 3-character minimum _meaningful_tokens otherwise applies.
_PRESERVE_SHORT_TOKENS = frozenset({"ph", "xr", "cr", "sr"})
_PRESERVE_SUFFIX_ONLY_TOKENS = _PRESERVE_SHORT_TOKENS | {"plus", "forte", "extra"}


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
    # Fix_drug_OCR_3.md section 8 (generalizes Fix_drug_OCR_2.md Part A):
    # True when this candidate's parsed catalog identity_text (any token
    # count -- e.g. "Snapcef" alone, or the multi-token "B Complex C
    # Vidipha") is one the catalog itself shows >=1 OTHER real product
    # sharing, with no observed OCR strength narrowing it back down to one.
    # A matched identity is not independently reliable evidence when the
    # catalog cannot tell which of 2+ real products it actually names --
    # see _decide()'s corroboration/uniqueness gate.
    identity_non_unique: bool = False
    # Fix_drug_OCR_3.md section 14 observability only (not decision-
    # affecting beyond what identity_non_unique above already gates):
    # true when the catalog shows exactly one real product for this
    # parsed identity regardless of strength. False plus
    # identity_non_unique=False means uniqueness was only established by
    # narrowing on an OCR-observed strength.
    identity_globally_unique: bool = True
    # PR #165 review response (real production finding, not the original
    # task scope): true when this candidate's OCR match is the new
    # partial-match tier (matched all but exactly one identity token, on
    # an identity with >=3 tokens) AND the matched SUBSET collides with
    # some OTHER real product's full identity -- meaning the missing
    # token might be genuinely distinguishing rather than OCR noise (see
    # _matched_subset_collides_with_other_identity). Blocks the partial
    # tier from reaching HIGH_EVIDENCE_MATCH regardless of corroboration.
    partial_subset_ambiguous: bool = False


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
    # PR #165 review response: True only when the match came from the
    # partial-match tier (matched all but exactly one identity token, on
    # a 3+-token identity) -- see _name_match's partial tier and
    # decision_reason_codes (PARTIAL_TOKEN_NAME_MATCH + confirmed, or
    # PARTIAL_TOKEN_NEEDS_CORROBORATION / PARTIAL_MATCH_SUBSET_AMBIGUOUS
    # if degraded).
    ocr_partial_token_name_match: bool
    ocr_strength_match: bool
    ocr_conflict: bool
    # Fix_drug_OCR_3.md section 14: bounded, catalog-derived parsing/
    # uniqueness signals -- never the raw identity_text/OCR string itself
    # (task's own explicit instruction), only a token count and booleans.
    # identity_strength_unique generalizes Fix_drug_OCR_2.md's original
    # single-token-only `ocr_single_token_non_unique` field (renamed and
    # inverted: this is the "unique enough" value _decide() actually
    # gates on, for both single- and multi-token identities now) --
    # False here is the direct replacement signal.
    parsed_identity_token_count: int
    pack_detected: bool
    description_suffix_detected: bool
    identity_unique: bool
    identity_strength_unique: bool
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
        or "product_name_match_single_token" in evidence_fields
        or "product_name_match_partial" in evidence_fields,
        ocr_single_token_name_match="product_name_match_single_token" in evidence_fields,
        ocr_partial_token_name_match="product_name_match_partial" in evidence_fields,
        ocr_strength_match="strength_match" in evidence_fields,
        ocr_conflict=bool(decision_top and decision_top.conflicts),
        parsed_identity_token_count=(
            len(_identity_segment_tokens(decision_top.product_display_name)) if decision_top else 0
        ),
        pack_detected=bool(
            decision_top and parse_catalog_identity(decision_top.product_display_name).pack_text is not None
        ),
        description_suffix_detected=bool(
            decision_top and parse_catalog_identity(decision_top.product_display_name).descriptive_text is not None
        ),
        identity_unique=bool(decision_top and decision_top.identity_globally_unique),
        identity_strength_unique=bool(decision_top and not decision_top.identity_non_unique),
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
    """Diacritic-aware comparison form; it is not displayed or persisted.

    Fix_drug_OCR_3.md section 10: short brand qualifiers written as
    "P/H"/"P.H." must normalize the same as the plain form "PH" -- applied
    here (not only inside the catalog-side _meaningful_tokens) so BOTH the
    catalog identity tokens and the raw OCR-observed text this function
    also normalizes (extract_structured_signals) end up comparable. Real
    bug found while testing this exact case: the join previously ran on
    the catalog side only, so an OCR line ending in "P/H" (the common
    real-world shape -- the abbreviation is rarely followed by more
    letters) never got joined into "ph" at all and the identity token
    silently dropped out of the observed set."""

    normalized = normalize_visible_text(value)
    normalized = _ABBREVIATION_JOIN_PATTERN.sub(r"\1\2", normalized)
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
    any_name_match = any(score >= 1.0 for score, _tokens, _matched in name_matches.values())
    prepared: list[RecognitionCandidate] = []
    for item in visual:
        product = metadata.get(item.drug_product_id)
        if product is None:
            continue
        text_evidence: list[TextSignal] = []
        conflicts: list[str] = []
        name_match, identity_token_count, matched_tokens = name_matches.get(
            item.drug_product_id, (0.0, 0, frozenset())
        )
        # Fix_drug_OCR_2.md Part A: a single-token identity match (~52.5% of
        # the catalog) is a materially weaker signal than a multi-token
        # one -- surfaced as its own text_evidence field so _decide() can
        # require additional corroboration before it may contribute to
        # HIGH_EVIDENCE_MATCH, instead of treating it the same as a robust
        # multi-token brand match.
        # Fix_drug_OCR_3.md section 8: catalog uniqueness is now checked for
        # BOTH shapes -- the leftmost-cut parser (section 3) can make a
        # multi-token identity non-unique too (e.g. three real "B Complex C
        # Vidipha" pack-size SKUs), so a robust-looking multi-token match is
        # not automatically exempt from this gate the way it was before.
        identity_non_unique = False
        identity_globally_unique = True
        partial_subset_ambiguous = False
        if name_match >= 0.5:
            identity_tokens = _identity_segment_tokens(product.display_name)
            identity_globally_unique, identity_strength_unique = _identity_uniqueness_detail(
                session, identity_tokens, observed_strengths
            )
            identity_non_unique = not identity_strength_unique
        if name_match >= 1.0:
            if identity_token_count == 1:
                text_evidence.append(
                    TextSignal(
                        "product_name_match_single_token",
                        product.display_name,
                        normalize_for_match(product.display_name),
                    )
                )
            else:
                text_evidence.append(
                    TextSignal("product_name_match", product.display_name, normalize_for_match(product.display_name))
                )
        elif name_match >= 0.5:
            # PR #165 review response (real production finding): a real
            # LONG Huyet PH photo reached visual Top-1 correctly but OCR
            # only read 2 of its 3 identity tokens. Real catalog audit
            # found 5.5% of 3+-token products (39/704) where the matched
            # subset itself collides with another product's full identity
            # -- e.g. "Clazic SR United" dropping "SR" -- so this tier is
            # additionally gated by _matched_subset_collides_with_other_identity,
            # never just the corroboration/uniqueness gate alone.
            text_evidence.append(
                TextSignal(
                    "product_name_match_partial", product.display_name, normalize_for_match(product.display_name)
                )
            )
            partial_subset_ambiguous = _matched_subset_collides_with_other_identity(
                session, identity_tokens, matched_tokens
            )
        elif any_name_match:
            conflicts.append("NAME_CONFLICT")
        # Fix_drug_OCR_3.md section 5/14: optional, tracked-only pack
        # corroboration -- never gates the decision (see _pack_match).
        pack_text = parse_catalog_identity(product.display_name).pack_text
        if pack_text and _pack_match(pack_text, observed_text):
            text_evidence.append(TextSignal("pack_text_match", pack_text, normalize_for_match(pack_text)))
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
                identity_non_unique=identity_non_unique,
                identity_globally_unique=identity_globally_unique,
                partial_subset_ambiguous=partial_subset_ambiguous,
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


@dataclass(frozen=True)
class CatalogIdentity:
    """Recognition/corroboration-only view of a catalog `display_name`
    (Fix_drug_OCR_3.md section 3) -- never persisted, never rewrites
    `DrugProduct.display_name` (section 16)."""

    identity_text: str
    strength_text: str | None
    pack_text: str | None
    descriptive_text: str | None


def parse_catalog_identity(display_name: str) -> CatalogIdentity:
    """Deterministic, catalog-wide split -- never a per-product special
    case (section 4/21: no `if name == "LONG Huyết PH"`, no "first N
    words"). Leftmost-cut strategy: identity_text is everything BEFORE
    whichever structural marker (strength / pack / a real descriptive
    delimiter / a trailing parenthetical) appears FIRST in the string.

    This directly generalizes the prior "everything before the first
    strength match" rule (Fix_drug_OCR_2.md): for a product WITH a
    strength pattern, strength is still virtually always the leftmost
    marker, so identity_text is unchanged from before -- verified on the
    real catalog, see the report's regression section. It is
    deliberately NOT a "remove each piece and keep the rest" strategy:
    that alternative was tried and rejected because it let trailing
    manufacturer text ("HẢI Dương", "Agimexpharm", "Organon", ...),
    which sits AFTER the strength/pack in most names, leak into
    identity_text -- a real regression this task must not introduce.
    """

    strength_match = _STRENGTH_PATTERN.search(display_name)
    pack_match = _PACK_PATTERN.search(display_name)
    delim_match = _DESCRIPTIVE_SPLIT_PATTERN.search(display_name)
    paren_match = _TRAILING_PAREN_PATTERN.search(display_name)

    cut_candidates: list[int] = []
    if strength_match:
        cut_candidates.append(strength_match.start())
    if pack_match:
        cut_candidates.append(pack_match.start())

    delim_is_real_suffix = False
    if delim_match:
        after = display_name[delim_match.end() :]
        after_tokens = set(normalize_for_match(after).split())
        preserve_only = bool(after_tokens) and after_tokens.issubset(_PRESERVE_SUFFIX_ONLY_TOKENS)
        if after.strip() and not preserve_only and len(_meaningful_tokens(after)) >= 2:
            delim_is_real_suffix = True
            cut_candidates.append(delim_match.start())

    paren_is_real_suffix = False
    if paren_match and len(_meaningful_tokens(paren_match.group(0))) >= 1:
        paren_is_real_suffix = True
        cut_candidates.append(paren_match.start())

    identity_text = display_name[: min(cut_candidates)] if cut_candidates else display_name
    identity_text = " ".join(identity_text.split())

    descriptive_text = None
    if delim_is_real_suffix:
        descriptive_text = display_name[delim_match.end() :].strip()
    elif paren_is_real_suffix:
        descriptive_text = paren_match.group(0).strip(" ()")

    return CatalogIdentity(
        identity_text=identity_text or display_name,
        strength_text=strength_match.group(0).strip() if strength_match else None,
        pack_text=pack_match.group(0).strip() if pack_match else None,
        descriptive_text=descriptive_text,
    )


def _identity_segment_tokens(display_name: str) -> tuple[str, ...]:
    """The parsed-identity tokens _name_match compares OCR text against.
    Shared with the catalog-uniqueness index (section 8) so both use the
    exact same extraction.

    PR #165 review: parse_catalog_identity()'s leftmost-cut can fall back
    to the WHOLE display_name as identity_text when the earliest
    structural marker starts at position 0 (cut_at == 0) or when no
    marker is found at all -- not currently hit by any real catalog row
    (checked directly against all 3556), but real for a hypothetical
    product like "2x12 Some Brand". _meaningful_tokens already re-strips
    a stray _STRENGTH_PATTERN match from that fallback text as a side
    effect of its own strength-stripping; pack had no equivalent
    protection, so a pack token (e.g. "2x12") could leak into identity
    comparison in that fallback case. Stripped here, scoped to identity-
    token extraction only, so it does not affect _pack_match's own
    direct _meaningful_tokens(pack_text) call on a real pack_text string
    (which would otherwise always reduce to zero tokens)."""

    identity = parse_catalog_identity(display_name)
    return _meaningful_tokens(_PACK_PATTERN.sub(" ", identity.identity_text))


def _name_match(display_name: str, observed_text: str) -> tuple[float, int, frozenset[str]]:
    """Return (score, identity_token_count, matched_tokens). Score is 1.0
    for a full match, 0.5 for the partial-match tier described below, 0.0
    otherwise; the token count lets the caller (_rerank) tell a robust
    multi-token match apart from a single-token one, which ~52.5% of the
    catalog reduces to (Fix_drug_OCR_2.md section 1) and which alone is
    not independently reliable identity evidence -- see _decide().

    Partial-match tier (post-PR-#165 production finding): a real photo of
    "LONG Huyet PH" (identity = 3 tokens) reached visual Top-1 correctly
    but OCR only read 2 of the 3 tokens in production, missing the
    75%-of-len>=2 bar by one token -- a real, observed false negative,
    not a hypothetical one. Scoped narrowly: only identities with >=3
    tokens, missing EXACTLY one. A 2-token identity dropping to 1 match is
    deliberately EXCLUDED here -- that shape is indistinguishable from the
    single-token case, which this project already treats as high-risk for
    a documented reason (a real catalog audit found this exact shape,
    e.g. "Pruzena" vs "Pruzena Forte": dropping "Forte" is not OCR noise,
    it is a different real product). The caller (_rerank) additionally
    requires the matched SUBSET to not itself collide with another real
    product's full identity before this tier counts as usable evidence
    (see _matched_subset_collides_with_other_identity) -- a real audit
    found 5.5% of 3+-token products (39/704) have exactly this risk
    (e.g. "Clazic SR United" dropping "SR" collides with a real
    "...United" identity), so the check is necessary, not theoretical."""

    candidate = _identity_segment_tokens(display_name)
    if not observed_text or not candidate:
        return 0.0, len(candidate), frozenset()
    # Description/marketing text must NOT be required for corroboration
    # (section 6) -- compare only against the parsed identity_text, not
    # the raw display_name approximation this used before.
    # OCR remains corroboration only: _decide still requires visual Top-1
    # and rejects strength/name conflicts before HIGH_EVIDENCE_MATCH.
    observed = set(observed_text.split())
    matched_tokens = frozenset(token for token in candidate if token in observed)
    matched = len(matched_tokens)
    if matched == len(candidate):
        return 1.0, len(candidate), matched_tokens
    if len(candidate) >= 2 and matched / len(candidate) >= 0.75:
        return 1.0, len(candidate), matched_tokens
    if len(candidate) >= 3 and matched == len(candidate) - 1:
        return 0.5, len(candidate), matched_tokens
    return 0.0, len(candidate), matched_tokens


def _meaningful_tokens(value: str) -> tuple[str, ...]:
    # Abbreviation-join (P/H -> ph) now happens inside normalize_for_match
    # itself so the catalog side here and the OCR-observed side
    # (extract_structured_signals) always agree -- see its docstring.
    without_strength = _STRENGTH_PATTERN.sub(" ", normalize_for_match(value))
    return tuple(
        token
        for token in without_strength.split()
        if token not in _DOSAGE_WORDS and (len(token) >= 3 or token in _PRESERVE_SHORT_TOKENS)
    )


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


# Fix_drug_OCR_3.md section 8 (generalizes Fix_drug_OCR_2.md Part A
# section 5's single-token-only version): catalog-derived uniqueness, not
# a hand-maintained keyword blacklist. Two indexes built together in one
# scan of `drug_product` (~3556 rows, sub-second): how many DISTINCT
# products share an exact identity_tokens set at all, and how many share
# that same set AND one specific strength -- the leftmost-cut parser
# (section 3) intentionally makes MORE products share an identity than
# the old raw-prefix comparison did (pack-size variants of the same real
# brand, e.g. three "B Complex C Vidipha" pack SKUs, now correctly
# collapse to one identity) so this check had to stop being single-token
# -only to keep covering the same real risk for multi-token identities
# too. Cached process-wide for the process lifetime -- the same
# "pay once, not per request" convention already used for the OpenCLIP
# embedder, the OCR runtime probe, and (Fix_drug_OCR_2.md's own PR
# review response) this exact index's predecessor, all warmed together
# at startup (backend/main.py). A catalog change only takes effect after
# a process restart, same as those two.
_IdentityKey = tuple[str, ...]
_IDENTITY_COUNT_INDEX: dict[_IdentityKey, int] | None = None
_IDENTITY_STRENGTH_COUNT_INDEX: dict[tuple[_IdentityKey, str], int] | None = None


def _identity_uniqueness_index(
    session: Session,
) -> tuple[dict[_IdentityKey, int], dict[tuple[_IdentityKey, str], int]]:
    global _IDENTITY_COUNT_INDEX, _IDENTITY_STRENGTH_COUNT_INDEX
    if _IDENTITY_COUNT_INDEX is not None and _IDENTITY_STRENGTH_COUNT_INDEX is not None:
        return _IDENTITY_COUNT_INDEX, _IDENTITY_STRENGTH_COUNT_INDEX
    count_index: dict[_IdentityKey, int] = {}
    strength_count_index: dict[tuple[_IdentityKey, str], int] = {}
    for product in session.scalars(select(DrugProduct)).all():
        tokens = _identity_segment_tokens(product.display_name)
        if not tokens:
            continue
        key = tuple(sorted(tokens))
        count_index[key] = count_index.get(key, 0) + 1
        source = " ".join(part for part in (product.strength_text, product.display_name) if part)
        for signal in extract_structured_signals(source):
            if signal.field != "strength_candidate":
                continue
            strength_key = (key, signal.normalized_value)
            strength_count_index[strength_key] = strength_count_index.get(strength_key, 0) + 1
    _IDENTITY_COUNT_INDEX = count_index
    _IDENTITY_STRENGTH_COUNT_INDEX = strength_count_index
    return count_index, strength_count_index


def _identity_uniqueness_detail(
    session: Session, identity_tokens: Sequence[str], strengths: set[str]
) -> tuple[bool, bool]:
    """Return (identity_unique, identity_strength_unique) for observability
    (Fix_drug_OCR_3.md section 14) and as the shared basis for
    _is_identity_non_unique below.

    identity_unique: the catalog shows exactly one real product for this
    parsed identity, regardless of strength.
    identity_strength_unique: true whenever identity_unique is already
    true, OR at least one OCR-observed strength narrows the identity back
    down to exactly one real product. This is the operationally relevant
    value -- _is_identity_non_unique is simply its negation."""

    key = tuple(sorted(identity_tokens))
    count_index, strength_count_index = _identity_uniqueness_index(session)
    total = count_index.get(key, 0)
    identity_unique = total <= 1
    if identity_unique:
        return True, True
    identity_strength_unique = any(strength_count_index.get((key, strength), 0) <= 1 for strength in strengths)
    return False, identity_strength_unique


def _is_identity_non_unique(session: Session, identity_tokens: Sequence[str], strengths: set[str]) -> bool:
    """True when the catalog itself shows >=1 OTHER real product sharing
    this exact parsed identity, AND no observed OCR strength narrows it
    back down to exactly one real product -- the shape this task's own
    audit found for 30 identity groups (e.g. three "B Complex C Vidipha"
    pack-size SKUs sharing one identity with no strength data at all,
    or two "Acyclovir 200mg" pack-size SKUs, unchanged from
    Fix_drug_OCR_2.md's own single-token finding). In that case OCR
    reading the brand text -- even a full, robust multi-token match --
    cannot tell the recognizer WHICH of the real candidates it actually
    names, so identity alone must not count as independently reliable
    evidence on its own (section 8: "identity match alone must NOT create
    HIGH_EVIDENCE")."""

    _, identity_strength_unique = _identity_uniqueness_detail(session, identity_tokens, strengths)
    return not identity_strength_unique


def _pack_match(pack_text: str | None, observed_text: str) -> bool:
    """Fix_drug_OCR_3.md section 5/14: pack_text corroboration is
    optional and tracked-only (PACK_TEXT_MATCH) -- it must never gate a
    decision (section 5: "Pack mismatch must not automatically become a
    hard safety conflict"). Reuses the same OCR-classified
    product_name_candidate text _name_match/_ingredient_match already
    compare against (extract_structured_signals' own line classifier
    keeps alpha-bearing pack lines like "20 ong x 10ml" in that bucket, so
    a second raw-text source is not needed)."""

    if not pack_text or not observed_text:
        return False
    tokens = _meaningful_tokens(pack_text)
    if not tokens:
        return False
    observed = set(observed_text.split())
    return all(token in observed for token in tokens)


def _matched_subset_collides_with_other_identity(
    session: Session, full_identity_tokens: Sequence[str], matched_tokens: frozenset[str]
) -> bool:
    """True when the OCR-matched SUBSET of a partial-match identity is
    itself the complete identity of some real catalog product -- meaning
    the token OCR missed might be genuinely distinguishing (e.g. "Forte",
    "SR"), not just noise. A real catalog audit found this for 5.5% of
    3+-token products (39/704), e.g. "Clazic SR United" -- dropping "SR"
    collides with a real "...United"-only identity elsewhere in the
    catalog. Reuses _identity_uniqueness_index's own count_index (already
    keyed by sorted identity-token tuples) rather than a second scan."""

    subset_key = tuple(sorted(matched_tokens))
    if subset_key == tuple(sorted(full_identity_tokens)):
        return False  # not actually partial (full match) -- nothing to check
    count_index, _strength_index = _identity_uniqueness_index(session)
    return count_index.get(subset_key, 0) > 0


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
        signal.field
        in {
            "product_name_match",
            "product_name_match_single_token",
            "product_name_match_partial",
            "strength_match",
            "ingredient_match",
        }
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
    # PR #165 review response (real production finding): a real LONG Huyet
    # PH photo hit visual Top-1 correctly but OCR read only 2 of its 3
    # identity tokens -- see _name_match's partial-match tier. Treated at
    # least as strictly as single-token: always needs corroboration, plus
    # its own extra gate (partial_subset_ambiguous) single-token never
    # needed, because a missing token can be genuinely distinguishing
    # (real audit: 5.5% of 3+-token products) rather than OCR noise.
    partial_text = any(signal.field == "product_name_match_partial" for signal in top.text_evidence)
    strength_matched = any(signal.field == "strength_match" for signal in top.text_evidence)
    ingredient_matched = any(signal.field == "ingredient_match" for signal in top.text_evidence)
    pack_matched = any(signal.field == "pack_text_match" for signal in top.text_evidence)
    identity_matched = strong_text or single_token_text or partial_text
    corroborated = strength_matched or ingredient_matched
    # Fix_drug_OCR_3.md section 8: a matched catalog identity_text -- single-
    # or multi-token -- is only independently reliable when the catalog
    # shows it names exactly one real product (after applying any
    # OCR-observed strength to narrow it). A single-token or partial match
    # additionally always requires a second corroborating signal even when
    # unique (Fix_drug_OCR_2.md's original, stricter rule for the
    # structurally weaker single-token shape, extended to partial); a
    # unique multi-token FULL match remains sufficient alone, unchanged
    # from before this task. Because strong_text implies
    # (strong_text or corroborated) unconditionally, the only way a
    # multi-token FULL match can fail this is top.identity_non_unique --
    # see the degrade branch below.
    identity_eligible = (
        identity_matched
        and not top.identity_non_unique
        and not top.partial_subset_ambiguous
        and (strong_text or corroborated)
    )
    has_any_catalog_match = any(candidate.text_evidence for candidate in candidates)
    # Fix_drug_OCR_3.md section 6/14: a real descriptive suffix
    # (e.g. "TAN BAM TIM GIAM PHU NE") was parsed out of this candidate's
    # catalog name and deliberately excluded from identity comparison --
    # tracked so a reviewer can see description was ignored, not silently
    # dropped.
    description_ignored = parse_catalog_identity(top.product_display_name).descriptive_text is not None
    # No cosine threshold is used.  High evidence remains bounded to the visual
    # Top-1 plus independent text corroboration; reranking a lower visual result
    # cannot silently turn a visual/text disagreement into a high-confidence claim.
    if identity_eligible and top.visual_rank == 1 and not duplicate_ambiguous:
        if single_token_text:
            reasons = ["SINGLE_TOKEN_NAME_MATCH"]
        elif partial_text:
            reasons = ["PARTIAL_TOKEN_NAME_MATCH"]
        else:
            reasons = ["OCR_NAME_MATCH"]
        reasons.append("CATALOG_IDENTITY_MATCH")
        if strength_matched:
            reasons.append("OCR_STRENGTH_MATCH")
        if (single_token_text or partial_text) and ingredient_matched:
            reasons.append("INGREDIENT_MATCH")
        if pack_matched:
            reasons.append("PACK_TEXT_MATCH")
        if description_ignored:
            reasons.append("DESCRIPTION_IGNORED_FOR_IDENTITY")
        reasons.append("HIGH_EVIDENCE_CONFIRMED")
        return HIGH_EVIDENCE_MATCH, tuple(reasons)
    if signals and not has_any_catalog_match:
        return INSUFFICIENT_EVIDENCE, ("INSUFFICIENT_VISUAL_EVIDENCE",)
    if duplicate_ambiguous:
        return AMBIGUOUS_MATCH, ("DUPLICATE_CONTENT_AMBIGUITY",)
    if identity_matched and not identity_eligible:
        # Real identity text evidence exists (the parsed identity matched)
        # but it is deliberately not enough alone -- degrade to
        # AMBIGUOUS_MATCH rather than inventing confidence (task's own
        # explicit section 8 rule), never silently indistinguishable from a
        # plain no-signal case.
        if single_token_text:
            reasons = ["SINGLE_TOKEN_NEEDS_CORROBORATION"]
        elif partial_text:
            reasons = ["PARTIAL_TOKEN_NEEDS_CORROBORATION"]
        else:
            reasons = ["CATALOG_IDENTITY_MATCH"]
        if top.identity_non_unique:
            reasons.append("CATALOG_IDENTITY_NON_UNIQUE")
        if top.partial_subset_ambiguous:
            reasons.append("PARTIAL_MATCH_SUBSET_AMBIGUOUS")
        if pack_matched:
            reasons.append("PACK_TEXT_MATCH")
        if description_ignored:
            reasons.append("DESCRIPTION_IGNORED_FOR_IDENTITY")
        return AMBIGUOUS_MATCH, tuple(reasons)
    if not _identity_segment_tokens(top.product_display_name):
        # Fix_drug_OCR_3.md section 14: the catalog parser itself could not
        # establish any identity tokens for this specific candidate (a
        # catalog-data shape issue, not an OCR failure) -- see the report's
        # "remaining catalog-data issues" section, never silently folded
        # into the generic AMBIGUOUS_VISUAL_ONLY case.
        return AMBIGUOUS_MATCH, ("AMBIGUOUS_VISUAL_ONLY", "IDENTITY_PARSE_AMBIGUOUS")
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
