"""Fix_drug_OCR_2.md Part A section 6: OCR single-token name-match
hardening test set. A single-token identity match (~52.5% of the real
catalog, see the report's own audit) must never be sufficient ALONE for
HIGH_EVIDENCE_MATCH -- it needs an additional real corroborating signal
(strength_match or ingredient_match, both already computed elsewhere) and
the catalog itself must not show >=1 other product sharing the exact
(identity, strength) pair. Fix_drug_OCR_3.md section 8 generalized the
catalog-uniqueness check from single-token-only to any parsed identity
token count; the underlying single-token behavior asserted below is
unchanged. The catalog-uniqueness index is a module-level, process-
lifetime cache (see drug_image_recognition._identity_uniqueness_index)
-- every test here resets it first so it is always computed fresh against
THAT test's own in-memory catalog, never leaked in from another test.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import sqlalchemy as sa
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

os.environ["INTERNAL_AUTH_SECRET"] = "b05-local-test-secret"
os.environ["JWT_SECRET"] = "b05-local-test-jwt"

from backend.db.models import DrugImage, DrugImageEmbedding, DrugProduct, DrugProductIngredient, Ingredient
from backend.services import drug_image_recognition as recognition_module
from backend.services.drug_image_recognition import (
    AMBIGUOUS_MATCH,
    HIGH_EVIDENCE_MATCH,
    INSUFFICIENT_EVIDENCE,
    DrugImageRecognizer,
    OcrObservation,
)
from backend.services.drug_image_retrieval import EMBEDDING_DIMENSION, PREPROCESSING_VERSION


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
    def __init__(self, text: str) -> None:
        self.text = text

    def extract(self, image: Image.Image) -> OcrObservation:  # noqa: ARG002 - protocol coverage
        return OcrObservation(self.text, "OCR_AVAILABLE")


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
            checksum_sha256=image_id.ljust(64, "a")[:64],
            normalized_checksum_sha256=image_id.ljust(64, "b")[:64],
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


def _reset_uniqueness_index_cache(monkeypatch) -> None:
    monkeypatch.setattr(recognition_module, "_IDENTITY_COUNT_INDEX", None)
    monkeypatch.setattr(recognition_module, "_IDENTITY_STRENGTH_COUNT_INDEX", None)


def _recognize(session: Session, ocr_text: str, image_index: int = 8):
    recognizer = DrugImageRecognizer(FakeEmbedder(), ocr=StaticOcr(ocr_text))
    image = query_image(image_index)
    try:
        return recognizer.recognize(session, image)
    finally:
        image.close()


# --- 1. Unique single-token + strength match: legitimate HIGH_EVIDENCE (positive control) ---


def test_unique_single_token_with_strength_match_reaches_high_evidence(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="snapcef", image_id="img-snapcef", vector_index=8, display_name="Snapcef 16mg/10ml")

    result = _recognize(session, "SNAPCEF\n16mg/10ml")

    assert result.outcome == HIGH_EVIDENCE_MATCH
    assert "SINGLE_TOKEN_NAME_MATCH" in result.decision_reason_codes
    assert "HIGH_EVIDENCE_CONFIRMED" in result.decision_reason_codes


# --- 2. Duplicated single-token, same strength, different real product: must NOT reach HIGH_EVIDENCE ---


def test_duplicated_single_token_same_strength_stays_ambiguous_not_high_evidence(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    # Mirrors a real collision this task's own catalog audit found:
    # "Acyclovir 200mg Stella 10x5" / "Acyclovir 200mg Stella 5x5" -- same
    # brand token, same strength, two distinct real drug_product_id rows.
    add_reference(session, product_id="acyclovir-10x5", image_id="img-a", vector_index=8, display_name="Acyclovir 200mg Stella 10x5")
    add_reference(session, product_id="acyclovir-5x5", image_id="img-b", vector_index=3, display_name="Acyclovir 200mg Stella 5x5")

    result = _recognize(session, "ACYCLOVIR\n200mg")

    assert result.outcome != HIGH_EVIDENCE_MATCH
    assert result.outcome == AMBIGUOUS_MATCH
    assert "CATALOG_IDENTITY_NON_UNIQUE" in result.decision_reason_codes
    assert result.candidates[0].identity_non_unique is True


# --- 3. Same brand, different strength: STRENGTH_CONFLICT, never HIGH_EVIDENCE ---


def test_same_single_token_brand_different_strength_is_hard_conflict(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="doniwell-25", image_id="img-25", vector_index=8, display_name="Doniwell 25mg")

    result = _recognize(session, "DONIWELL\n50mg")  # OCR reads a different strength than the catalog row

    assert result.outcome == INSUFFICIENT_EVIDENCE
    assert "OCR_HARD_CONFLICT" in result.decision_reason_codes
    assert "STRENGTH_CONFLICT" in result.decision_reason_codes


# --- 4. (same as case 2, restated per the task's own risk-case lettering) same brand+strength, different product ---


def test_same_brand_same_strength_different_product_requires_extra_corroboration(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(
        session, product_id="simvastatin-a", image_id="img-sim-a", vector_index=8,
        display_name="A.t Simvastatin 20mg AN Thien 3x10",
    )
    add_reference(
        session, product_id="simvastatin-b", image_id="img-sim-b", vector_index=1,
        display_name="Simvastatin 20mg Stella 3x10",
    )

    result = _recognize(session, "SIMVASTATIN\n20mg")

    assert result.outcome != HIGH_EVIDENCE_MATCH


# --- 5. Multi-token product: unaffected by this hardening (regression check) ---


def test_multi_token_product_name_match_alone_still_reaches_high_evidence(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="pruzena", image_id="img-pruzena", vector_index=8, display_name="Pruzena Forte 10mg")

    result = _recognize(session, "PRUZENA FORTE")  # no strength read at all -- multi-token name match alone must suffice, unchanged from before this task

    assert result.outcome == HIGH_EVIDENCE_MATCH
    assert "OCR_NAME_MATCH" in result.decision_reason_codes
    assert "SINGLE_TOKEN_NAME_MATCH" not in result.decision_reason_codes


# --- 6. Noisy/generic OCR token that matches no real brand: stays ambiguous, no invented confidence ---


def test_noisy_ocr_text_matching_no_brand_stays_ambiguous(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="snapcef", image_id="img-snapcef", vector_index=8, display_name="Snapcef 16mg/10ml")

    result = _recognize(session, "XKQZW MMBBQ 999")

    assert result.outcome != HIGH_EVIDENCE_MATCH


# --- 7. Missing strength on a single-token match: insufficient alone without another signal ---


def test_single_token_match_without_any_strength_or_ingredient_signal_degrades_to_ambiguous(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="snapcef", image_id="img-snapcef", vector_index=8, display_name="Snapcef 16mg/10ml")

    result = _recognize(session, "SNAPCEF")  # brand only, no strength line, no ingredient text

    assert result.outcome == AMBIGUOUS_MATCH
    assert "SINGLE_TOKEN_NEEDS_CORROBORATION" in result.decision_reason_codes
    assert result.outcome != HIGH_EVIDENCE_MATCH


# --- 8. Wrong strength on an otherwise-unique single-token brand: hard conflict, not a softened match ---


def test_single_token_wrong_strength_is_still_a_hard_conflict_not_softened_by_this_change(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="refix", image_id="img-refix", vector_index=8, display_name="Refix 550mg")

    result = _recognize(session, "REFIX\n275mg")

    assert result.outcome == INSUFFICIENT_EVIDENCE
    assert "STRENGTH_CONFLICT" in result.decision_reason_codes


# --- 9. Ingredient corroboration (no strength read at all) is sufficient on its own for a single-token brand ---


def test_single_token_match_with_ingredient_corroboration_reaches_high_evidence(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(
        session, product_id="gaspemin", image_id="img-gaspemin", vector_index=8,
        display_name="Gaspemin 40mg", ingredient="Omeprazole",
    )

    result = _recognize(session, "GASPEMIN\nOmeprazole")  # no strength line at all -- ingredient is the sole corroboration

    assert result.outcome == HIGH_EVIDENCE_MATCH
    assert "INGREDIENT_MATCH" in result.decision_reason_codes


# --- Uniqueness index correctness (unit-level, not through the full recognizer) ---


def test_identity_uniqueness_index_is_catalog_derived_not_a_keyword_list(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    # "Stella 10x5"/"Stella 5x5" are pack suffixes, stripped by the
    # leftmost-cut parser (Fix_drug_OCR_3.md section 3) -- both rows
    # parse to the identical single-token identity ("acyclovir").
    add_reference(session, product_id="a", image_id="img-a", vector_index=8, display_name="Acyclovir 200mg Stella 10x5")
    add_reference(session, product_id="b", image_id="img-b", vector_index=1, display_name="Acyclovir 200mg Stella 5x5")
    add_reference(session, product_id="c", image_id="img-c", vector_index=2, display_name="Acyclovir 400mg Stella 10x5")

    assert recognition_module._is_identity_non_unique(session, ("acyclovir",), {"200 mg"}) is True
    assert recognition_module._is_identity_non_unique(session, ("acyclovir",), {"400 mg"}) is False
    # Fix_drug_OCR_3.md section 8 deliberately strengthens this one case
    # past Fix_drug_OCR_2.md's original single-token-only behavior: with NO
    # strength read at all, 3 real catalog products still share "acyclovir"
    # -- that collision cannot be waved through as "unique enough" just
    # because OCR read no strength. (For a single-token match this makes no
    # observable difference: _decide()'s separate corroboration requirement
    # already blocks a no-strength/no-ingredient single-token match either
    # way. For a MULTI-token match -- which has no such separate
    # corroboration requirement when unique -- this is the fix that closes
    # section 8's real gap: a colliding multi-token identity with zero OCR
    # strength signal must not slip through uncaught.)
    assert recognition_module._is_identity_non_unique(session, ("acyclovir",), set()) is True
    assert recognition_module._is_identity_non_unique(session, ("unknown-brand",), {"200 mg"}) is False


def test_identity_uniqueness_index_covers_multi_token_identities_too(monkeypatch) -> None:
    """Fix_drug_OCR_3.md section 8: the generalized index must gate a
    robust-looking MULTI-token identity match too, not just single-token
    ones -- the real risk the catalog collision audit found (e.g. three
    "B Complex C Vidipha" pack-size SKUs collapsing to one multi-token
    identity under the new leftmost-cut parser)."""

    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="a", image_id="img-a", vector_index=8, display_name="B Complex C Vidipha 2x10")
    add_reference(session, product_id="b", image_id="img-b", vector_index=1, display_name="B Complex C Vidipha 3x10")

    # "B"/"C" are dropped by the 3-char minimum (_meaningful_tokens) --
    # the parsed identity is ("complex", "vidipha").
    identity = ("complex", "vidipha")
    assert recognition_module._is_identity_non_unique(session, identity, set()) is True
    assert recognition_module._is_identity_non_unique(session, ("unrelated", "identity"), set()) is False
