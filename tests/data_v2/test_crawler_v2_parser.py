from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "data_v2"))

from crawler_v2 import PARSER_VERSION, classify_duong_dung


def test_explicit_topical_instruction_resolves_ambiguous_emulsion() -> None:
    assert classify_duong_dung("Nh\u0169 t\u01b0\u01a1ng (Gel)", "<p>Thu\u1ed1c ch\u1ec9 d\u00f9ng ngo\u00e0i da.</p>") == "B\u00f4i ngo\u00e0i da"


def test_unambiguous_form_is_not_overridden_by_another_route_phrase() -> None:
    assert classify_duong_dung("B\u1ed9t pha ti\u00eam", "<p>D\u00f9ng theo \u0111\u01b0\u1eddng ti\u00eam truy\u1ec1n t\u0129nh m\u1ea1ch.</p>") == "Ti\u00eam"


def test_ambiguous_form_without_explicit_route_stays_blank() -> None:
    assert classify_duong_dung("Dung d\u1ecbch", "<p>Tham kh\u1ea3o h\u01b0\u1edbng d\u1eabn s\u1eed d\u1ee5ng.</p>") == ""


def test_explicit_topical_action_resolves_ambiguous_form() -> None:
    assert classify_duong_dung("Nh\u0169 t\u01b0\u01a1ng (Gel)", "<p>B\u00f4i thu\u1ed1c l\u00ean v\u00f9ng da b\u1ecb b\u1ec7nh.</p>") == "B\u00f4i ngo\u00e0i da"


def test_parser_version_was_bumped() -> None:
    assert PARSER_VERSION == "longchau-v2.1.0"
