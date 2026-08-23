"""Chay golden set VLM (eval.md + anh_test/) qua DUNG ham production
dem_thuoc_trong_anh() - danh gia do chinh xac dem thuoc THAT, khong gia lap
monkeypatch nhu tests/services/photo_verification/test_verifier.py. Goi API
that, TON PHI THAT (xem VLM_API_KEY/VLM_MODEL trong .env, doc qua
backend.config.get_settings() - dung nguon voi app that).

Anh trong anh_test/ duoc dua qua nen_anh() (cung ham photo_routes.py dung
that) truoc khi goi model - dam bao PNG/JPG deu thanh JPEG that dung dinh
dang ham dem_thuoc_trong_anh() ky vong (ham nay luon khai bao
"image/jpeg" khi goi API, xem vlm_bridge.py:254), khong gui thang bytes
goc co the sai dinh dang.

Chay: .venv/Scripts/python.exe eval/eval_vlm/run_eval_vlm.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.config import get_settings  # noqa: E402
from backend.services.photo_verification.image_processing import nen_anh  # noqa: E402
from backend.services.photo_verification.vlm_bridge import dem_thuoc_trong_anh  # noqa: E402
from backend.services.vlm_telemetry import get_vlm_telemetry_service  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
ANH_DIR = EVAL_DIR / "anh_test"
EVAL_MD = EVAL_DIR / "eval.md"

# Nhan tieng Viet trong cot "Ky vong" -> dung khoa cua KetQuaDemVlm.counts
# (backend/services/photo_verification/count_keys.py). "Ong thuoc" KHONG co
# khoa rieng - vlm_prompts.py dinh nghia ro ampoule/vial tinh chung vao
# lo_thuoc ("Tinh ca lo thuy tinh nho (vial) va ong thuoc thuy tinh (ampoule)").
_NHAN_TO_KHOA = {
    "viên nén": "vien_nen",
    "viên nang": "vien_nang",
    "tuýp thuốc": "tuyp_thuoc",
    "lọ thuốc": "lo_thuoc",
    "hộp thuốc": "hop_thuoc",
    "gói thuốc": "goi_thuoc",
    "ống thuốc": "lo_thuoc",
}

_CAC_KHOA = ("vien_nang", "vien_nen", "tuyp_thuoc", "lo_thuoc", "hop_thuoc", "goi_thuoc")
_KHONG_PHAI_THUOC = "không phải thuốc"


def _parse_ky_vong(text: str) -> dict[str, int] | None:
    """None = case "khong phai thuoc" (kiem tra rieng, khong so khoa dem).
    Nguoc lai tra du 6 khoa, khoa khong nhac toi = 0."""
    if _KHONG_PHAI_THUOC in text.strip().lower():
        return None

    ky_vong = dict.fromkeys(_CAC_KHOA, 0)
    for phan in text.split(","):
        khop = re.match(r"\s*([^=]+?)\s*=\s*(\d+)\s*$", phan)
        if not khop:
            raise ValueError(f"Không parse được kỳ vọng: {phan!r} (trong {text!r})")
        nhan = khop.group(1).strip().lower()
        so = int(khop.group(2))
        khoa = _NHAN_TO_KHOA.get(nhan)
        if khoa is None:
            raise ValueError(f"Nhãn không nhận diện được: {nhan!r} (trong {text!r})")
        ky_vong[khoa] += so
    return ky_vong


def _doc_bang(md_path: Path) -> list[dict]:
    rows = []
    for dong in md_path.read_text(encoding="utf-8").splitlines()[2:]:
        dong = dong.strip()
        if not dong.startswith("|"):
            continue
        cot = [c.strip() for c in dong.strip("|").split("|")]
        if len(cot) < 6:
            continue
        stt, case, don_thuoc, mo_ta_anh, do_kho, ky_vong_raw = cot[:6]
        rows.append({
            "stt": stt, "case": case, "don_thuoc": don_thuoc,
            "mo_ta_anh": mo_ta_anh, "do_kho": do_kho, "ky_vong_raw": ky_vong_raw,
        })
    return rows


def _tim_file_anh(case: str) -> Path:
    khop = list(ANH_DIR.glob(f"{case}.*"))
    if not khop:
        raise FileNotFoundError(f"Không tìm thấy ảnh cho case {case!r} trong {ANH_DIR}")
    return khop[0]


def main() -> int:
    settings = get_settings()
    telemetry = get_vlm_telemetry_service()
    # Nhan dien lan chay nay tren Langfuse Cloud (tag "golden-eval" +
    # eval_run_id chung cho ca 25 trace) - de so sanh % dat giua cac lan
    # chay sau khi sua prompt, khong phai tu so file JSON cu/moi bang tay.
    eval_run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    rows = _doc_bang(EVAL_MD)
    print(f"Đã đọc {len(rows)} case từ {EVAL_MD}")
    print(f"VLM: provider={settings.vlm_provider} model={settings.vlm_model} base_url={settings.vlm_base_url}")
    print(f"Langfuse: connected={telemetry.is_langfuse_connected()} eval_run_id={eval_run_id}")
    print()

    chi_tiet: list[dict] = []
    for i, row in enumerate(rows, 1):
        case = row["case"]
        print(f"[{i}/{len(rows)}] {case} ({row['do_kho']}) ... ", end="", flush=True)
        try:
            anh_path = _tim_file_anh(case)
            anh_goc = anh_path.read_bytes()
            anh_jpeg = nen_anh(anh_goc, settings.photo_max_edge_px, settings.photo_jpeg_quality)
            ky_vong = _parse_ky_vong(row["ky_vong_raw"])

            ket_qua_vlm = dem_thuoc_trong_anh(anh_jpeg, settings)

            if not ket_qua_vlm.ok:
                print(f"LỖI GỌI VLM: {ket_qua_vlm.error}")
                chi_tiet.append({**row, "loi": ket_qua_vlm.error, "dat": False})
                continue

            if ky_vong is None:
                # Case "khong phai thuoc": dat neu KHONG dem nham vao bat ky
                # khoa thuoc that nao - khong doi hoi dung chinh xac so luong
                # khong_phai_thuoc (chi la tin hieu phu, khong phai tieu chi).
                dat = all(ket_qua_vlm.counts.get(k, 0) == 0 for k in _CAC_KHOA)
            else:
                dat = all(ket_qua_vlm.counts.get(k, 0) == ky_vong[k] for k in _CAC_KHOA)

            print("ĐẠT" if dat else "SAI")
            chi_tiet.append({
                **row,
                "ky_vong": ky_vong if ky_vong is not None else "khong_phai_thuoc",
                "thuc_te": dict(ket_qua_vlm.counts),
                "khong_phai_thuoc_dem_duoc": ket_qua_vlm.khong_phai_thuoc,
                "do_tin_cay": ket_qua_vlm.do_tin_cay,
                "ghi_chu_model": ket_qua_vlm.ghi_chu,
                "latency_sec": ket_qua_vlm.latency_sec,
                "dat": dat,
            })

            # Ghi 1 trace/case len Langfuse (tai dung dung ha tang
            # vlm_telemetry.py, khong viet telemetry rieng cho eval) - tag
            # "golden-eval" phan biet voi trace production that.
            trace = telemetry.create_trace(
                trace_id=f"golden-eval:{eval_run_id}:{case}",
                name="vlm.golden_eval_case",
                input_data={"expected": ky_vong if ky_vong is not None else "khong_phai_thuoc"},
                metadata={"eval_run_id": eval_run_id, "case": case, "do_kho": row["do_kho"]},
                tags=["golden-eval"],
            )
            obs = telemetry.start_observation(trace, "vlm.model_call", obs_type="generation")
            telemetry.end_observation(
                obs, output_data={"counts": ket_qua_vlm.counts, "do_tin_cay": ket_qua_vlm.do_tin_cay}
            )
            telemetry.record_score(trace, "golden_match", 1.0 if dat else 0.0)
            telemetry.finalize_trace(trace, output_data={"dat": dat}, status="success" if dat else "mismatch")
        except Exception as exc:  # noqa: BLE001 - eval script, 1 case loi khong duoc dung ca vong chay
            print(f"LỖI: {exc}")
            chi_tiet.append({**row, "loi": str(exc), "dat": False})

    tong = len(chi_tiet)
    so_dat = sum(1 for r in chi_tiet if r.get("dat"))
    theo_do_kho: dict[str, list[bool]] = {}
    for r in chi_tiet:
        theo_do_kho.setdefault(r["do_kho"], []).append(bool(r.get("dat")))

    # Bang doi chieu do_tin_cay model tu bao cao vs ty le dung THAT - tinh tu
    # dong (truoc phai lam tay tu file JSON) de moi lan chay deu thay ngay
    # tin hieu nay co con dang tin cay sau khi sua prompt hay khong.
    theo_do_tin_cay: dict[str, list[bool]] = {}
    for r in chi_tiet:
        if r.get("do_tin_cay"):
            theo_do_tin_cay.setdefault(r["do_tin_cay"], []).append(bool(r.get("dat")))

    bao_cao = {
        "chay_luc": datetime.now(UTC).isoformat(),
        "eval_run_id": eval_run_id,
        "vlm_provider": settings.vlm_provider,
        "vlm_model": settings.vlm_model,
        "tong_case": tong,
        "so_dat": so_dat,
        "ty_le_dat_pct": round(so_dat / tong * 100, 1) if tong else 0.0,
        "theo_do_kho": {
            k: {"so_dat": sum(v), "tong": len(v), "ty_le_pct": round(sum(v) / len(v) * 100, 1)}
            for k, v in theo_do_kho.items()
        },
        "theo_do_tin_cay": {
            k: {"so_dat": sum(v), "tong": len(v), "ty_le_pct": round(sum(v) / len(v) * 100, 1)}
            for k, v in theo_do_tin_cay.items()
        },
        "chi_tiet": chi_tiet,
    }

    (EVAL_DIR / "eval_report.json").write_text(
        json.dumps(bao_cao, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dong = [
        "# Kết quả eval VLM (đếm thuốc)", "",
        f"Chạy lúc: {bao_cao['chay_luc']}",
        f"Model: `{bao_cao['vlm_provider']}/{bao_cao['vlm_model']}`", "",
        f"**Tổng: {so_dat}/{tong} đạt ({bao_cao['ty_le_dat_pct']}%)**", "",
        "| Độ khó | Đạt/Tổng | % |", "|---|---|---|",
    ]
    for k, v in bao_cao["theo_do_kho"].items():
        dong.append(f"| {k} | {v['so_dat']}/{v['tong']} | {v['ty_le_pct']}% |")
    dong += ["", "| Độ tin cậy | Đạt/Tổng | % |", "|---|---|---|"]
    for k, v in bao_cao["theo_do_tin_cay"].items():
        dong.append(f"| {k} | {v['so_dat']}/{v['tong']} | {v['ty_le_pct']}% |")
    dong += [
        "", "## Chi tiết từng case", "",
        "| Case | Độ khó | Kỳ vọng | Thực tế (khác 0) | Độ tin cậy | Kết quả |",
        "|---|---|---|---|---|---|",
    ]
    for r in chi_tiet:
        thuc_te_str = ", ".join(f"{k}={v}" for k, v in r.get("thuc_te", {}).items() if v) or "(rỗng)"
        if r.get("loi"):
            trang_thai = f"⚠️ Lỗi: {r['loi']}"
        else:
            trang_thai = "✅" if r.get("dat") else "❌"
        dong.append(
            f"| {r['case']} | {r['do_kho']} | {r['ky_vong_raw']} | {thuc_te_str} "
            f"| {r.get('do_tin_cay', '-')} | {trang_thai} |"
        )
    (EVAL_DIR / "eval_report.md").write_text("\n".join(dong), encoding="utf-8")

    print()
    print(f"Kết quả: {so_dat}/{tong} đạt ({bao_cao['ty_le_dat_pct']}%)")
    print(f"Đã ghi {EVAL_DIR / 'eval_report.json'} và {EVAL_DIR / 'eval_report.md'}")
    if telemetry.is_langfuse_connected():
        print(f"Đã ghi {tong} trace lên Langfuse với tag 'golden-eval', eval_run_id={eval_run_id}")
    else:
        print("Langfuse chưa kết nối (thiếu VLM_LANGFUSE_PUBLIC_KEY/SECRET_KEY) - chỉ có báo cáo local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
