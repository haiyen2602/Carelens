"""Fix_drug_OCR_3.md: catalog identity parsing hardening test set.

Two groups of tests:

1. `parse_catalog_identity()` unit tests -- the leftmost-cut parser itself
   (section 3/4), including the two real catalog examples the task is
   built around (Snapcef, LONG Huyet PH) and the punctuation/abbreviation
   edge cases sections 6/10 call out.
2. Section 11's lettered hard-negative tests (A-G), run through the full
   `DrugImageRecognizer`, using real catalog-shaped multi-token names --
   the single-token equivalents of most of these are already covered by
   tests/services/test_drug_image_ocr_name_hardening.py (Fix_drug_OCR_2.md)
   and are not repeated here. Required: false HIGH_EVIDENCE_MATCH = 0 on
   every hard negative below.
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
    DrugImageRecognizer,
    OcrObservation,
    parse_catalog_identity,
)
from backend.services.drug_image_retrieval import EMBEDDING_DIMENSION, PREPROCESSING_VERSION

# ==================================================================
# Group 1: parse_catalog_identity() unit tests
# ==================================================================


def test_long_huyet_ph_splits_identity_from_pack_and_description() -> None:
    """The task's own headline reproduction case (section 3 example)."""

    identity = parse_catalog_identity("LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ")

    assert identity.identity_text == "LONG Huyết PH"
    assert identity.pack_text == "2x12"
    assert identity.strength_text is None
    assert identity.descriptive_text == "TAN BẦM TÍM GIẢM PHÙ NỀ"


def test_snapcef_unaffected_by_the_new_parser() -> None:
    """The task's own explicit regression guard (section 3 example) --
    the "remove each matched span, keep the remainder" strategy that was
    tried and rejected corrupted this exact case by leaking "Hải Dương"
    into identity_text; the leftmost-cut strategy must not."""

    identity = parse_catalog_identity("Snapcef 16mg/10ml HẢI Dương 20 ỐNG X 10ml")

    assert identity.identity_text == "Snapcef"
    assert identity.strength_text is not None
    assert "16" in identity.strength_text


def test_bare_hyphen_compound_brand_token_is_not_split() -> None:
    """A hyphen with NO surrounding whitespace is a compound brand token
    (section 4: preserve meaningful identity tokens), not a descriptive
    delimiter -- only "\\s[-,:]\\s" (whitespace on both sides) counts."""

    identity = parse_catalog_identity("Agi-neurin Agimexpharm 10x10")

    assert identity.identity_text.strip().startswith("Agi-neurin")
    assert identity.descriptive_text is None or "neurin" not in (identity.descriptive_text or "").lower()


def test_combo_dose_slash_notation_is_not_treated_as_strength() -> None:
    identity = parse_catalog_identity("Agilosart-h 100/12.5 Agimexpharm 3x10")

    assert identity.identity_text.strip().startswith("Agilosart-h")


def test_abbreviated_pack_count_is_recognized() -> None:
    identity = parse_catalog_identity("Bilomag 6x10v")

    assert identity.identity_text.strip() == "Bilomag"
    assert identity.pack_text is not None


def test_p_slash_h_abbreviation_normalizes_consistently_with_dotted_form() -> None:
    """Section 10: P/H, PH, P.H. must compare safely/consistently."""

    slash_tokens = recognition_module._meaningful_tokens("LONG Huyết P/H")
    dotted_tokens = recognition_module._meaningful_tokens("LONG Huyết P.H.")
    plain_tokens = recognition_module._meaningful_tokens("LONG Huyết PH")

    assert slash_tokens == dotted_tokens == plain_tokens


def test_short_preserved_suffix_alone_does_not_force_a_descriptive_split() -> None:
    """A trailing " - Plus"/" - XR"-shaped suffix that is itself just a
    preserved short qualifier must not be misread as a real descriptive
    marketing suffix."""

    identity = parse_catalog_identity("SomeBrand 10mg - XR")

    assert identity.descriptive_text is None


def test_display_name_is_never_mutated_by_parsing() -> None:
    """Section 16: this parsing must never rewrite stored display_name --
    parse_catalog_identity is a pure function over its input string."""

    raw = "LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ"
    parse_catalog_identity(raw)
    assert raw == "LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ"


# ==================================================================
# Group 2: full-recognizer hard-negative tests (section 11, cases A-G)
# ==================================================================


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


# --- A. Same multi-token identity, different strength: hard conflict ---


def test_a_same_multi_token_identity_different_strength_is_hard_conflict(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="bvc-500", image_id="img-500", vector_index=8, display_name="Bio Vitamin C 500mg")

    result = _recognize(session, "BIO VITAMIN C\n1000mg")  # OCR reads a strength the catalog row does not have

    assert result.outcome != HIGH_EVIDENCE_MATCH
    assert "STRENGTH_CONFLICT" in result.decision_reason_codes


# --- B. Same multi-token identity, same (absent) strength, different real product ---


def test_b_same_multi_token_identity_no_strength_two_products_stays_ambiguous(monkeypatch) -> None:
    """Mirrors the real catalog collision this task's own audit found:
    multiple "B Complex C Vidipha" pack-size SKUs collapsing to one
    multi-token identity with no strength data at all -- this is exactly
    the section 8 gap (multi-token matches previously had NO uniqueness
    gate at all)."""

    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="bcv-2x10", image_id="img-a", vector_index=8, display_name="B Complex C Vidipha 2x10")
    add_reference(session, product_id="bcv-3x10", image_id="img-b", vector_index=3, display_name="B Complex C Vidipha 3x10")

    result = _recognize(session, "B COMPLEX C VIDIPHA")

    assert result.outcome != HIGH_EVIDENCE_MATCH
    assert result.outcome == AMBIGUOUS_MATCH
    assert "CATALOG_IDENTITY_NON_UNIQUE" in result.decision_reason_codes


# --- C. Identity differs only by a meaningful suffix (Forte) ---


def test_c_forte_suffix_distinguishes_identity_ocr_missing_it_does_not_confirm_forte_variant(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="pruzena-plain", image_id="img-plain", vector_index=3, display_name="Pruzena 10mg")
    add_reference(session, product_id="pruzena-forte", image_id="img-forte", vector_index=8, display_name="Pruzena Forte 10mg")

    # Visual Top-1 is the Forte variant (vector_index=8 matches query_image(8)
    # below), but OCR never read the word "Forte" -- must not confirm Forte.
    result = _recognize(session, "PRUZENA\n10mg", image_index=8)

    assert result.outcome != HIGH_EVIDENCE_MATCH


# --- D. Similar herbal products sharing generic descriptive text ---


def test_d_shared_descriptive_text_alone_never_reaches_high_evidence(monkeypatch) -> None:
    """Two different real brands sharing the same marketing/descriptive
    suffix -- since descriptive_text is excluded from identity comparison
    entirely (section 6), OCR reading ONLY that shared marketing phrase
    must not be able to confirm either product."""

    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(
        session, product_id="long-huyet", image_id="img-long", vector_index=8,
        display_name="LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ",
    )
    add_reference(
        session, product_id="other-brand", image_id="img-other", vector_index=3,
        display_name="Cao Xoa ABC 3x10 - TAN BẦM TÍM GIẢM PHÙ NỀ",
    )

    result = _recognize(session, "TAN BAM TIM GIAM PHU NE")  # descriptive text only, no brand identity at all

    assert result.outcome != HIGH_EVIDENCE_MATCH


# --- E. Same first token(s), different real brand ---


def test_e_same_leading_token_different_real_brand_requires_full_identity_match(monkeypatch) -> None:
    """No "take first N words" shortcut (section 4): identity comparison
    must use the FULL parsed identity, not just a shared leading token."""

    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(session, product_id="agi-fexofast", image_id="img-fexofast", vector_index=8, display_name="Agi Fexofast 60mg")
    add_reference(session, product_id="agi-colcemin", image_id="img-colcemin", vector_index=3, display_name="Agi Colcemin 0.5mg")

    # Visual Top-1 is Colcemin, but OCR fully names the OTHER real "Agi"
    # product (Fexofast) -- must not let Colcemin ride through as a match.
    result = _recognize(session, "AGI FEXOFAST\n60mg", image_index=3)

    assert result.outcome != HIGH_EVIDENCE_MATCH


# --- F. Packaging suffix differs, identity + strength otherwise shared ---


def test_f_pack_suffix_differs_same_identity_and_strength_stays_ambiguous(monkeypatch) -> None:
    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(
        session, product_id="snapcef-20", image_id="img-20", vector_index=8,
        display_name="Snapcef 16mg/10ml HẢI Dương 20 ống x 10ml",
    )
    add_reference(
        session, product_id="snapcef-10", image_id="img-10", vector_index=3,
        display_name="Snapcef 16mg/10ml HẢI Dương 10 ống x 10ml",
    )

    result = _recognize(session, "SNAPCEF\n16mg/10ml")  # identity + strength read, no pack info read

    assert result.outcome != HIGH_EVIDENCE_MATCH
    assert "CATALOG_IDENTITY_NON_UNIQUE" in result.decision_reason_codes


# --- G. Descriptive suffix differs but identity is the same: must NOT block ---


def test_g_descriptive_mismatch_does_not_block_an_otherwise_unique_corroborated_match(monkeypatch) -> None:
    """This is the original LONG Huyết reproduction case (section 1/9):
    catalog descriptive_text ("...GIAM PHU NE") differs from the real
    printed box text ("...MAU LANH VET THUONG"), but identity_text is
    unique and fully OCR-corroborated, and visual Top-1 is correct.
    Section 6: descriptive mismatch must NOT become OCR_HARD_CONFLICT."""

    _reset_uniqueness_index_cache(monkeypatch)
    session = session_with_schema()
    add_reference(
        session, product_id="long-huyet", image_id="img-long", vector_index=8,
        display_name="LONG Huyết PH 2x12 - TAN BẦM TÍM GIẢM PHÙ NỀ",
    )

    # Real box text (from the reproduced case): identity matches, but the
    # printed marketing tagline differs from the catalog's own descriptive
    # suffix -- descriptive text must simply be ignored, not compared.
    result = _recognize(session, "LONG HUYẾT P/H\nTan bam tim\nMau lanh vet thuong")

    assert result.outcome == HIGH_EVIDENCE_MATCH
    assert "OCR_HARD_CONFLICT" not in result.decision_reason_codes
    assert "DESCRIPTION_IGNORED_FOR_IDENTITY" in result.decision_reason_codes
