"""B-05 bounded recognition and safety behaviour."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import sqlalchemy as sa
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

os.environ["INTERNAL_AUTH_SECRET"] = "b05-local-test-secret"
os.environ["JWT_SECRET"] = "b05-local-test-jwt"

from backend.db.models import DrugImage, DrugImageEmbedding, DrugProduct, DrugProductIngredient, Ingredient
from backend.services.drug_image_recognition import (
    AMBIGUOUS_MATCH,
    HIGH_EVIDENCE_MATCH,
    INSUFFICIENT_EVIDENCE,
    OCR_SOURCE,
    QUALITY_REJECT,
    DrugImageRecognizer,
    OcrObservation,
    ProductMetadata,
    TextSignal,
    _rerank,
    extract_structured_signals,
    inspect_image_quality,
    normalize_for_match,
)
from backend.services.drug_image_retrieval import EMBEDDING_DIMENSION, PREPROCESSING_VERSION, DrugImageSearchResult


class FakeEmbedder:
    embedding_model = "test/image"
    embedding_version = "test-v1"
    embedding_dimension = EMBEDDING_DIMENSION
    preprocessing_version = PREPROCESSING_VERSION

    def embed_image(self, image: Image.Image) -> tuple[float, ...]:
        return self.unit(image.convert("RGB").getpixel((0, 0))[0])

    @staticmethod
    def unit(index: int) -> tuple[float, ...]:
        return tuple(1.0 if offset == index else 0.0 for offset in range(EMBEDDING_DIMENSION))


class StaticOcr:
    def __init__(self, text: str, status: str = "OCR_OK") -> None:
        self.text = text
        self.status = status
        self.calls = 0

    def extract(self, image: Image.Image) -> OcrObservation:  # noqa: ARG002 - protocol coverage
        self.calls += 1
        return OcrObservation(self.text, self.status)


class FailingOcr:
    def extract(self, image: Image.Image) -> OcrObservation:  # noqa: ARG002 - protocol coverage
        raise OSError("OCR executable unavailable")


def session_with_schema() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    for table in (DrugProduct, DrugImage, DrugImageEmbedding, Ingredient, DrugProductIngredient):
        table.__table__.create(engine)
    return Session(engine)


def add_reference(
    session: Session,
    *,
    product_id: str,
    image_id: str,
    vector_index: int,
    display_name: str,
    strength: str | None = None,
    checksum: str | None = None,
    ingredient: str | None = None,
) -> None:
    session.add(
        DrugProduct(
            id=product_id,
            legacy_drug_id=f"legacy-{product_id}",
            display_name=display_name,
            strength_text=strength,
            status="ACTIVE",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    if ingredient:
        ingredient_id = f"ingredient-{product_id}"
        session.add(
            Ingredient(id=ingredient_id, name=ingredient, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        )
        session.add(DrugProductIngredient(drug_product_id=product_id, ingredient_id=ingredient_id))
    session.add(
        DrugImage(
            id=image_id,
            drug_product_id=product_id,
            storage_key=f"drug-images/v1/{product_id}/front/{image_id}.webp",
            source_url=f"https://example.test/{image_id}",
            source_snapshot_id=f"snapshot-{image_id}",
            checksum_sha256=(checksum or image_id).ljust(64, "a")[:64],
            normalized_checksum_sha256=(checksum or image_id).ljust(64, "b")[:64],
            mime_type="image/webp",
            width=100,
            height=100,
            file_size=100,
            view_type="front",
            is_primary=True,
            validation_status="VALIDATED",
            collection_version="v1",
            source_retrieved_at=datetime.now(UTC),
        )
    )
    session.add(
        DrugImageEmbedding(
            drug_image_id=image_id,
            embedding_model=FakeEmbedder.embedding_model,
            embedding_version=FakeEmbedder.embedding_version,
            embedding_dimension=EMBEDDING_DIMENSION,
            embedding=list(FakeEmbedder.unit(vector_index)),
            preprocessing_version=PREPROCESSING_VERSION,
        )
    )
    session.commit()


def query_image(index: int) -> Image.Image:
    image = Image.new("RGB", (120, 100), (index, 30, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 5, 110, 90), outline=(255, 255, 255), width=3)
    draw.line((0, 99, 119, 0), fill=(0, 0, 0), width=3)
    return image


def test_quality_gate_reports_deterministic_retake_and_reject_reasons() -> None:
    tiny = Image.new("RGB", (20, 20), "black")
    blank = Image.new("RGB", (120, 100), "white")
    try:
        assert inspect_image_quality(tiny).status == QUALITY_REJECT
        quality = inspect_image_quality(blank)
        assert quality.status != "PASS"
        assert {"IMAGE_TOO_BRIGHT", "IMAGE_TOO_BLURRY"}.issubset(quality.reason_codes)
    finally:
        tiny.close()
        blank.close()


def test_normalization_preserves_strength_units_and_extracts_only_visible_signals() -> None:
    signals = extract_structured_signals("PÁRACÉTAMOL\n500mg\nNSX: Demo Pharma\nVD-1234-56")
    assert normalize_for_match("PÁRACÉTAMOL 500mg") == "paracetamol 500mg"
    assert ("strength_candidate", "500 mg", OCR_SOURCE) in {(item.field, item.value, item.source) for item in signals}
    assert any(item.field == "manufacturer_candidate" for item in signals)
    assert any(item.field == "registration_number_candidate" for item in signals)
    assert all(item.source == OCR_SOURCE for item in signals)


def test_high_evidence_requires_top_visual_text_corroboration_and_confirmation() -> None:
    session = session_with_schema()
    add_reference(
        session,
        product_id="paracetamol",
        image_id="image-paracetamol",
        vector_index=8,
        display_name="Paracetamol 500mg",
        strength="500 mg",
        ingredient="Paracetamol",
    )
    add_reference(
        session,
        product_id="other",
        image_id="image-other",
        vector_index=9,
        display_name="Other 250mg",
        strength="250 mg",
    )
    ocr = StaticOcr("PARACETAMOL 500 mg")
    image = query_image(8)
    try:
        result = DrugImageRecognizer(FakeEmbedder(), ocr=ocr).recognize(session, image)
    finally:
        image.close()
    assert result.outcome == HIGH_EVIDENCE_MATCH
    assert result.confirmation_required is True
    assert result.candidates[0].drug_product_id == "paracetamol"
    assert result.candidates[0].visual_rank == 1
    assert "xác nhận" in result.confirmation_prompt().casefold()
    assert ocr.calls == 1


def test_visual_text_conflict_never_becomes_high_evidence() -> None:
    session = session_with_schema()
    add_reference(
        session,
        product_id="paracetamol",
        image_id="image-p",
        vector_index=8,
        display_name="Paracetamol 500mg",
        strength="500 mg",
    )
    add_reference(
        session,
        product_id="amoxicillin",
        image_id="image-a",
        vector_index=9,
        display_name="Amoxicillin 500mg",
        strength="500 mg",
    )
    image = query_image(8)
    try:
        result = DrugImageRecognizer(FakeEmbedder(), ocr=StaticOcr("Amoxicillin 500 mg")).recognize(session, image)
    finally:
        image.close()
    assert result.outcome != HIGH_EVIDENCE_MATCH
    assert any("NAME_CONFLICT" in item.conflicts for item in result.candidates)


def test_conflict_free_candidate_outranks_hard_conflict_regardless_of_visual_score() -> None:
    visual = (
        DrugImageSearchResult(1, "image-a", "product-a", 0.99, "test/image", "test-v1"),
        DrugImageSearchResult(2, "image-b", "product-b", -0.90, "test/image", "test-v1"),
    )
    metadata = {
        "product-a": ProductMetadata("product-a", "Paracetamol 500mg", "500 mg", None, ()),
        "product-b": ProductMetadata("product-b", "Amoxicillin 500mg", "500 mg", None, ()),
    }
    signals = (
        TextSignal("product_name_candidate", "Amoxicillin", "amoxicillin"),
        TextSignal("strength_candidate", "500 mg", "500 mg"),
    )

    candidates = _rerank(visual, metadata, signals)

    assert candidates[0].drug_product_id == "product-b"
    assert candidates[0].conflicts == ()
    assert candidates[1].conflicts == ("NAME_CONFLICT",)


def test_duplicate_content_without_text_remains_ambiguous_not_forced_top_one() -> None:
    session = session_with_schema()
    checksum = "duplicate-checksum"
    add_reference(
        session, product_id="product-a", image_id="image-a", vector_index=8, display_name="Product A", checksum=checksum
    )
    add_reference(
        session, product_id="product-b", image_id="image-b", vector_index=8, display_name="Product B", checksum=checksum
    )
    image = query_image(8)
    try:
        result = DrugImageRecognizer(FakeEmbedder(), ocr=StaticOcr("")).recognize(session, image)
    finally:
        image.close()
    assert result.outcome == AMBIGUOUS_MATCH
    assert "DUPLICATE_REFERENCE_CONTENT_REQUIRES_CONFIRMATION" in result.evidence_summary
    assert result.confirmation_required is True


def test_unknown_text_and_bad_quality_fail_safely_without_medical_facts_or_persistence() -> None:
    session = session_with_schema()
    add_reference(
        session,
        product_id="known",
        image_id="image-known",
        vector_index=8,
        display_name="Known 500mg",
        strength="500 mg",
    )
    image = query_image(8)
    try:
        result = DrugImageRecognizer(FakeEmbedder(), ocr=StaticOcr("Breakfast cereal 10 ml")).recognize(session, image)
    finally:
        image.close()
    assert result.outcome == INSUFFICIENT_EVIDENCE
    assert {
        "VISIBLE_TEXT_DOES_NOT_CORROBORATE_CATALOG_CANDIDATES",
        "TOP_CANDIDATE_HAS_HARD_CONFLICT",
    } & set(result.evidence_summary)
    assert not hasattr(result, "medical_facts")
    assert session.query(DrugImageEmbedding).count() == 1

    blank = Image.new("RGB", (120, 100), "white")
    try:
        retake = DrugImageRecognizer(FakeEmbedder(), ocr=StaticOcr("Known 500mg")).recognize(session, blank)
    finally:
        blank.close()
    assert retake.outcome == INSUFFICIENT_EVIDENCE
    assert retake.quality_gate.status != "PASS"
    assert "QUALITY_GATE_RETAKE_RECOMMENDED" in retake.evidence_summary


def test_recognition_result_is_deterministic_and_contains_version_without_generating_calls() -> None:
    session = session_with_schema()
    add_reference(
        session,
        product_id="known",
        image_id="image-known",
        vector_index=8,
        display_name="Known 500mg",
        strength="500 mg",
    )
    recognizer = DrugImageRecognizer(FakeEmbedder(), ocr=StaticOcr(""))
    first_image = query_image(8)
    second_image = query_image(8)
    try:
        first = recognizer.recognize(session, first_image)
        second = recognizer.recognize(session, second_image)
    finally:
        first_image.close()
        second_image.close()
    assert first == second
    assert first.recognition_version == "drug-recognition-v1"
    assert first.outcome == AMBIGUOUS_MATCH


def test_ocr_runtime_failure_degrades_to_candidate_confirmation_not_a_crash() -> None:
    session = session_with_schema()
    add_reference(
        session,
        product_id="known",
        image_id="image-known",
        vector_index=8,
        display_name="Known 500mg",
        strength="500 mg",
    )
    image = query_image(8)
    try:
        result = DrugImageRecognizer(FakeEmbedder(), ocr=FailingOcr()).recognize(session, image)
    finally:
        image.close()
    assert result.outcome == AMBIGUOUS_MATCH
    assert "OCR_STATUS:OCR_FAILED" in result.evidence_summary
