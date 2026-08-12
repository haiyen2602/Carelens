#!/usr/bin/env python3
"""Prototype: chatbot tra cuu thong tin thuoc trong don, chay that bang OpenAI API.

Day la ban THU NGHIEM de xem & gop y truoc khi build vao src/ that (khong dung
DB/auth - chi doc thang tu data pharmacy/ va don thuoc gia lap/tu sinh trong
file nay). Xem README.md cung thu muc de biet cach chay va cach map sang kien
truc that trong ARCHITECTURE.md / specs/api-contracts.md.

v2 - sua 3 bug phat hien khi test that (xem README "Bug da phat hien") + them:
- Nhan dien cau hoi TONG QUAT VE LICH UONG THUOC (vd "sang nay uong thuoc gi")
  tach rieng khoi cau hoi ve 1 thuoc cu the - tra loi thang tu don thuoc,
  khong can goi LLM (nhanh, khong rui ro bia).
- Bo xay dung "benh an gia dinh": chon that cac thuoc tu data pharmacy/ theo
  danh_muc phu hop 1 tinh huong benh nhan, thay vi don thuoc cung hardcode.

Model mac dinh: gpt-5-nano (xem trao doi voi PM ve gia). Doi qua CHATBOT_MODEL.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data pharmacy"
LOG_PATH = Path(__file__).resolve().parent / "missing_drugs_log.jsonl"

DEFAULT_MODEL = os.environ.get("CHATBOT_MODEL", "gpt-5-nano")
SUMMARIZE_THRESHOLD_CHARS = 800  # chi goi LLM rut gon khi vuot nguong nay

# ---------------------------------------------------------------------------
# 0. Don thuoc mau co dinh (giu lai lam lua chon nhanh "0" - khong can goi
#    LLM de build). Cac "benh an gia dinh" thuc su xem CASE_PROFILES ben duoi.
# ---------------------------------------------------------------------------
MOCK_PRESCRIPTION = [
    {
        "drug_id": "cordamil-40mg-helcor-3x10",
        "ten_thuoc": "Cordamil 40mg Helcor",
        "ham_luong": "40mg",
        "lieu_dung": "1 viên/lần, ngày 1 lần",
        "thoi_diem_dung": "Buổi sáng, sau ăn",
    },
    {
        "drug_id": "galvus-met-50mg-1000mg-6x10",
        "ten_thuoc": "Galvus Met 50mg/1000mg",
        "ham_luong": "Vildagliptin 50mg + Metformin 1000mg",
        "lieu_dung": "1 viên/lần, ngày 2 lần",
        "thoi_diem_dung": "Sáng và tối, ngay sau bữa ăn",
    },
    {
        "drug_id": "berocca-bayer-10v",
        "ten_thuoc": "Berocca",
        "ham_luong": "Vitamin nhóm B, C và khoáng chất",
        "lieu_dung": "1 viên sủi/ngày",
        "thoi_diem_dung": "Buổi sáng, pha với nước",
    },
]

# ---------------------------------------------------------------------------
# "Benh an gia dinh" - danh_muc phai la ten CHINH XAC da co trong data
# pharmacy/ (kiem tra bang cach doc thuc te, khong doan). Moi case chon 1
# thuoc dai dien tung danh_muc trong pool.
# ---------------------------------------------------------------------------
CASE_PROFILES = {
    "1": {
        "label": "Cụ bà 68 tuổi — tăng huyết áp, đái tháo đường type 2, thiếu vitamin nhóm B",
        "danh_muc_list": ["Thuốc tim mạch huyết áp", "Thuốc trị tiểu đường", "Thuốc bổ"],
    },
    "2": {
        "label": "Nam 35 tuổi — viêm họng cấp do nhiễm khuẩn, cần tăng đề kháng",
        "danh_muc_list": ["Thuốc kháng sinh", "Thuốc tai mũi họng", "Thuốc tăng cường sức đề kháng"],
    },
    "3": {
        "label": "Nữ 50 tuổi — viêm da dị ứng, mất ngủ do căng thẳng, rối loạn tiêu hoá nhẹ",
        "danh_muc_list": ["Thuốc bôi ngoài da", "Thuốc an thần", "Thuốc tiêu hoá"],
    },
}

# Gan thoi diem dung THEO DANH MUC - chi la quy uoc hop ly cho demo, KHONG
# phai tu van y khoa thuc; ban that phai lay tu bac si nhap khi ke don.
THOI_DIEM_BY_DANH_MUC = {
    "Thuốc tim mạch huyết áp": "Buổi sáng, sau ăn",
    "Thuốc trị tiểu đường": "Ngay trước hoặc trong bữa ăn sáng và tối",
    "Thuốc bổ": "Buổi sáng",
    "Thuốc kháng sinh": "Sau ăn, chia đều các cữ trong ngày",
    "Thuốc tai mũi họng": "Sau ăn",
    "Thuốc tăng cường sức đề kháng": "Buổi sáng",
    "Thuốc bôi ngoài da": "Bôi 2 lần/ngày, sáng và tối",
    "Thuốc an thần": "Buổi tối, trước khi ngủ 30 phút",
    "Thuốc tiêu hoá": "Trước bữa ăn 30 phút",
}
DEFAULT_THOI_DIEM = "Theo hướng dẫn của bác sĩ"

FIELD_KEYWORDS = {
    "tac_dung": ["tac dung", "cong dung", "dieu tri benh gi", "chi dinh"],
    "tac_dung_phu": ["tac dung phu", "phan ung phu", "adr", "bien chung"],
    "huong_dan_su_dung": ["cach dung", "huong dan su dung", "dung nhu the nao", "cach uong"],
    "duong_dung": ["duong dung", "uong hay tiem", "boi hay uong", "dung theo duong nao", "duong nao"],
    "huong_dan_bao_quan": ["bao quan", "luu tru", "de o dau"],
    "luu_y_dac_biet": ["luu y", "than trong", "canh bao", "kieng ky", "chong chi dinh"],
    "dang_thuoc": ["dang thuoc", "dang bao che", "vien hay siro"],
    "tong_so_luong": ["so luong", "bao nhieu vien trong hop", "quy cach"],
}

# Cau hoi TONG QUAT ve lich uong thuoc (khong nhac ten thuoc cu the) - phai
# kiem tra TRUOC buoc khop ten thuoc, vi cac cau nay khong chua ten thuoc nao
# nen se luon that bai neu di qua nhanh tim-thuoc-trong-don truoc.
SCHEDULE_KEYWORDS = [
    "danh sach thuoc", "thuoc can uong", "uong thuoc gi", "can uong gi",
    "thuoc hom nay", "lich uong thuoc", "toi can uong", "phai uong thuoc gi",
    "danh sach don thuoc",
]
TIME_OF_DAY_KEYWORDS = {"sang": "sáng", "trua": "trưa", "chieu": "chiều", "toi": "tối"}

NUMBER_UNIT_RE = re.compile(
    r"\d+([.,]\d+)?\s*(mg|ml|g|%|viên|lần|ngày|giờ|tuần|tháng|mcg|iu)",
    re.IGNORECASE,
)


def strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    ascii_text = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", ascii_text)


def normalize(text: str) -> str:
    return strip_diacritics(text or "").lower().strip()


def _tokenize(text: str) -> set[str]:
    """Nhu normalize() nhung con bo het dau cau (":", "?", ","...) roi tach
    tu - sua bug thuc te: "Cordamil:40" bi coi la 1 token dinh lien, khong
    khop duoc voi token "cordamil" rieng le."""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", normalize(text))
    return set(cleaned.split())


def _meaningful_tokens(text: str) -> set[str]:
    """Tu 'dang ke' - bo token la so/don vi hoac qua ngan (vd '40', 'mg') de
    tranh khop nham voi tu chung chung trong cau hoi."""
    return {t for t in _tokenize(text) if len(t) >= 4 and not t[0].isdigit()}


# ---------------------------------------------------------------------------
# Kho tham chieu data pharmacy/ - doc that tu repo, khong hardcode.
# ---------------------------------------------------------------------------
def load_corpus() -> dict[str, dict]:
    corpus: dict[str, dict] = {}
    for category_dir in sorted(DATA_DIR.iterdir()):
        f = category_dir / "thuoc.json"
        if not f.exists():
            continue
        for record in json.loads(f.read_text(encoding="utf-8")):
            corpus[record["id"]] = record
    return corpus


# ---------------------------------------------------------------------------
# Khop ten thuoc nguoi dung go -> dung item trong DON THUOC HIEN TAI (khong
# phai toan bo kho). Khop theo tu khoa (khong can go du cum), ca theo
# ten_thuoc lan tung hoat chat trong ham_luong.
# ---------------------------------------------------------------------------
def find_prescription_item(query: str, prescription: list[dict]) -> dict | None:
    q_tokens = _tokenize(query)

    for item in prescription:
        if _meaningful_tokens(item["ten_thuoc"]) & q_tokens:
            return item

    for item in prescription:
        # tach ham_luong theo dau '+'/';' de khop tung hoat chat rieng
        # (vd "Vildagliptin 50mg + Metformin 1000mg" -> hoi "Metformin" van khop)
        for part in re.split(r"[+;]", item["ham_luong"]):
            if _meaningful_tokens(part) & q_tokens:
                return item
    return None


def is_schedule_query(query: str) -> bool:
    q = normalize(query)
    return any(kw in q for kw in SCHEDULE_KEYWORDS)


def classify_field(query: str) -> str | None:
    """Chon keyword khop DAI NHAT tren toan bo field (khong dung thu tu dict)
    - vd "tac dung phu" phai thang "tac dung" du field 'tac_dung' duoc khai
    bao truoc, vi "tac dung" la substring cua "tac dung phu"."""
    q = normalize(query)
    best_field, best_len = None, 0
    for field, keywords in FIELD_KEYWORDS.items():
        for kw in keywords:
            kw_norm = normalize(kw)
            if kw_norm in q and len(kw_norm) > best_len:
                best_field, best_len = field, len(kw_norm)
    return best_field  # None = cau hoi tong quat ("chi tiet ve X"), tra loi tong hop


# ---------------------------------------------------------------------------
# Goi LLM - chi de DIEN DAT LAI noi dung da truy xuat, khong duoc tu suy
# luan them thong tin ngoai context truyen vao.
# ---------------------------------------------------------------------------
def get_openai_client():
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[LOI] Khong tim thay OPENAI_API_KEY trong .env - khong the goi LLM.", file=sys.stderr)
        sys.exit(1)
    from openai import OpenAI

    return OpenAI(api_key=api_key)


SYSTEM_PROMPT = (
    "Ban la tro ly tra loi thong tin thuoc cho benh nhan bang tieng Viet. "
    "CHI duoc dung dung noi dung trong phan 'DU LIEU NGUON' duoi day de tra loi. "
    "TUYET DOI khong duoc them so lieu, lieu luong, tac dung, hay bat ky thong tin "
    "nao khong co trong DU LIEU NGUON, du ban co the biet tu kien thuc chung. "
    "Neu DU LIEU NGUON CO thong tin lien quan cau hoi, hay tra loi TU TIN bang "
    "chinh du lieu do - khong can nhac di nhac lai 'khong co thong tin cu the' "
    "khi ban thuc su da co du lieu de tra loi. CHI noi 'khong co thong tin' khi "
    "DU LIEU NGUON thuc su rong hoac hoan toan khong lien quan cau hoi duoc hoi. "
    "Tra loi ngan gon, de hieu, giong nguoi dan y te noi chuyen voi benh nhan."
)


def call_llm(client, question: str, context: str, model: str) -> str:
    if not context.strip():
        return "Hiện tại tôi chưa có thông tin về nội dung này, bạn nên hỏi bác sĩ/dược sĩ nhé."
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"DU LIEU NGUON:\n{context}\n\nCAU HOI CUA BENH NHAN: {question}",
            },
        ],
        # gpt-5-nano (reasoning-tier) chi nhan temperature mac dinh - khong
        # duoc truyen tham so nay khi doi model, kiem tra lai neu doi model.
    )
    return resp.choices[0].message.content.strip()


def extract_number_units(text: str) -> set[str]:
    return {normalize(m.group(0)) for m in NUMBER_UNIT_RE.finditer(text)}


def validate_no_fabricated_numbers(source: str, generated: str) -> bool:
    """Tra False neu ban sinh ra co so+don vi KHONG xuat hien trong nguon goc
    (dau hieu LLM bia so lieu) - day la buoc chan bang code, khong phu thuoc
    hoan toan vao prompt."""
    fabricated = extract_number_units(generated) - extract_number_units(source)
    return not fabricated


def summarize_if_long(client, text: str, model: str) -> tuple[str, bool]:
    """Rut gon text neu qua dai, co validate chong bia so lieu.
    Return (text_de_hien, da_rut_gon_thanh_cong)."""
    if len(text) <= SUMMARIZE_THRESHOLD_CHARS:
        return text, False
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Rut gon doan van ban y te sau thanh 3-4 cau ngan gon, tieng Viet, "
                    "de benh nhan de hieu. CHI duoc rut gon/dien dat lai - TUYET DOI "
                    "khong duoc them so lieu (mg, vien, lan/ngay...) khong co trong ban goc."
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    summary = resp.choices[0].message.content.strip()
    if validate_no_fabricated_numbers(text, summary):
        return summary, True
    print("  [CANH BAO NOI BO] Ban rut gon co so lieu la, huy va dung ban goc.", file=sys.stderr)
    return text, False


def derive_doctor_style_dosage(client, corpus_lieu_dung: str, model: str) -> str:
    """Tu doan lieu_dung THAM KHAO (co the rat dai) trong data pharmacy/, sinh
    1 dong NGAN GON kieu bac si ghi trong don - dung cho buoc build benh an
    gia dinh. Van qua validate chong bia so, that bai -> fallback an toan."""
    text = (corpus_lieu_dung or "").strip()
    if not text:
        return "Theo chỉ định của bác sĩ"
    if len(text) <= 150:
        return text
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu doan huong dan lieu dung y te sau, viet lai thanh DUNG 1 DONG "
                    "ngan gon kieu bac si ghi trong don thuoc (vd '1 vien/lan, ngay 2 "
                    "lan'). CHI duoc dung so lieu CO SAN trong doan van, TUYET DOI "
                    "khong bia so moi."
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    short = resp.choices[0].message.content.strip()
    if validate_no_fabricated_numbers(text, short):
        return short
    print("  [CANH BAO NOI BO] Lieu tu sinh cho benh an co so la, dung cau mac dinh.", file=sys.stderr)
    return "Theo chỉ định của bác sĩ (xem chi tiết trong đơn)"


# Cac cum cau chung chung ("boilerplate") ma nhieu trang thuoc dung khi
# KHONG co lieu dung cu the (vd "Tham khao y kien bac si...") - can loai
# nhung ban ghi chi co dung cau nay, neu khong thuat toan "chon ngan nhat"
# se uu tien nham chuoi rong/cau vo nghia vi chung ngan nhat.
GENERIC_LIEU_DUNG_MARKERS = [
    "tham khao", "tuy thuoc vao the trang", "y kien bac si", "chuyen vien y te",
]


def _is_generic_lieu_dung(text: str) -> bool:
    t = normalize(text)
    # chi coi la "chung chung" khi NGAN va co dau hieu boilerplate - doan dai
    # van co the la lieu dung that kem 1 cau nhac nho o cuoi
    return len(text) < 250 and any(m in t for m in GENERIC_LIEU_DUNG_MARKERS)


def pick_representative(corpus: dict[str, dict], danh_muc: str) -> dict | None:
    """Chon 1 thuoc dai dien cho danh_muc: uu tien ban ghi co du tac_dung/
    tac_dung_phu/luu_y_dac_biet/lieu_dung (demo phong phu hon), tranh
    lieu_dung rong hoac chi la cau chung chung, va gan voi do dai ~120 ky tu
    (du cu the, khong qua dai) - khong don gian "chon ngan nhat" (se bi
    chuoi rong/cau vo nghia lot vao vi chung luon ngan nhat)."""
    candidates = [r for r in corpus.values() if r.get("danh_muc") == danh_muc]
    rich = [
        r for r in candidates
        if r.get("tac_dung") and r.get("tac_dung_phu") and r.get("luu_y_dac_biet") and r.get("lieu_dung")
    ]
    pool = rich or candidates
    if not pool:
        return None

    def sort_key(r: dict) -> tuple[bool, int]:
        text = r.get("lieu_dung") or ""
        return (not text or _is_generic_lieu_dung(text), abs(len(text) - 120))

    pool.sort(key=sort_key)
    return pool[0]


def build_case(client, corpus: dict[str, dict], case_key: str, model: str) -> tuple[str, list[dict]]:
    """Xay 'benh an gia dinh': chon that cac thuoc tu data pharmacy/ theo
    danh_muc phu hop tinh huong benh nhan, tu sinh lieu_dung ngan gon (co
    validate) + gan thoi_diem_dung theo quy uoc danh_muc."""
    profile = CASE_PROFILES[case_key]
    items = []
    for danh_muc in profile["danh_muc_list"]:
        record = pick_representative(corpus, danh_muc)
        if record is None:
            print(f"  [BO QUA] Khong tim thay thuoc nao trong danh_muc '{danh_muc}'.", file=sys.stderr)
            continue
        items.append(
            {
                "drug_id": record["id"],
                "ten_thuoc": record["ten_thuoc"],
                "ham_luong": record["ham_luong"],
                "lieu_dung": derive_doctor_style_dosage(client, record.get("lieu_dung", ""), model),
                "thoi_diem_dung": THOI_DIEM_BY_DANH_MUC.get(danh_muc, DEFAULT_THOI_DIEM),
            }
        )
    return profile["label"], items


# ---------------------------------------------------------------------------
# Log hang doi bo sung du lieu - CHI ghi khi thuoc CO trong don nhung KHONG
# co trong kho (khac voi "hoi thuoc ngoai don" - khong log truong hop do).
# ---------------------------------------------------------------------------
def log_missing_drug(item: dict) -> None:
    entry = {"drug_id": item["drug_id"], "ten_thuoc": item["ten_thuoc"]}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Dieu phoi chinh.
# ---------------------------------------------------------------------------
@dataclass
class AnswerResult:
    reply: str
    sources: list[dict]


def answer_schedule_query(query: str, prescription: list[dict]) -> AnswerResult:
    """Cau hoi tong quat ve lich uong thuoc - tra loi THANG TU DON THUOC, khong
    can goi LLM (du lieu da co san, khong co gi de 'dien dat lai' rui ro)."""
    q = normalize(query)
    # Dung KEY (khong dau, vd "sang") de so khop vi thoi_diem_dung cung duoc
    # normalize() bo dau truoc khi so - bug thuc te: so nham "sáng" (co dau,
    # tu LABEL) voi chuoi da bo dau nen khong bao gio khop.
    time_entry = next(((key, label) for key, label in TIME_OF_DAY_KEYWORDS.items() if key in q), None)

    if time_entry:
        time_key, time_label = time_entry
        matched = [it for it in prescription if time_key in normalize(it["thoi_diem_dung"])]
        if not matched:
            return AnswerResult(
                reply=f"Trong đơn hiện tại, tôi không thấy thuốc nào ghi rõ dùng vào buổi {time_label}.",
                sources=[],
            )
    else:
        matched = prescription

    lines = [f"- {it['ten_thuoc']}: {it['lieu_dung']} ({it['thoi_diem_dung']})" for it in matched]
    reply = "Theo đơn thuốc hiện tại của bạn:\n" + "\n".join(lines)
    sources = [{"drug_id": it["drug_id"], "field": "prescription"} for it in matched]
    return AnswerResult(reply=reply, sources=sources)


def answer_question(client, query: str, prescription: list[dict], corpus: dict[str, dict], model: str) -> AnswerResult:
    if is_schedule_query(query):
        return answer_schedule_query(query, prescription)

    item = find_prescription_item(query, prescription)
    if item is None:
        return AnswerResult(
            reply="Tôi không thấy thuốc bạn hỏi trong đơn thuốc hiện tại của bạn. Bạn có muốn hỏi bác sĩ không?",
            sources=[],
        )

    record = corpus.get(item["drug_id"])
    if record is None:
        log_missing_drug(item)
        return AnswerResult(
            reply="Hiện tại tôi chưa có thông tin về thuốc này. Tôi sẽ cập nhật thêm.",
            sources=[],
        )

    field = classify_field(query)
    if field is not None:
        parts = [str(record.get(field) or "")]
        fields_used = [field]
    else:
        # cau hoi tong quat ("cho toi biet chi tiet ve...") -> gop vai field
        # chinh lam ngu canh, khong dua toan bo record (giu context gon)
        fields_used = [f for f in ("tac_dung", "dang_thuoc", "duong_dung", "luu_y_dac_biet") if record.get(f)]
        parts = [f"{f}: {record[f]}" for f in fields_used]

    # Neu ten thuoc (vd "Cordamil") khac ten day du trong don (vd "Cordamil
    # 40mg Helcor"), them dong dau de LLM khong bi mo ho ve dang tra loi
    # dung thuoc nao -> tranh cau tra loi tu mau thuan ("khong co thong tin
    # cu the ve X" roi lai ke chi tiet ve X ngay sau do).
    context = f"Thông tin thuốc: {item['ten_thuoc']} ({item['ham_luong']})\n" + "\n".join(parts)

    if len(context) > SUMMARIZE_THRESHOLD_CHARS:
        context, _ = summarize_if_long(client, context, model)

    reply = call_llm(client, query, context, model)
    sources = [{"drug_id": item["drug_id"], "field": f} for f in fields_used] if any(parts) else []
    return AnswerResult(reply=reply, sources=sources)


def print_prescription_overview(label: str, prescription: list[dict]) -> None:
    print("=" * 60)
    print(f"Bệnh án: {label}")
    print("-" * 60)
    print("LOP 1 - Danh sach thuoc trong don (chi hien ten):")
    for item in prescription:
        print(f"  • {item['ten_thuoc']}")
    print()
    print("LOP 2 - An vao tung thuoc de xem the co dong (tu DON THUOC, khong")
    print("        phai tu kho tham chieu):")
    for item in prescription:
        print(f"\n  [{item['ten_thuoc']}]")
        print(f"    Thành phần   : {item['ham_luong']}")
        print(f"    Liều dùng    : {item['lieu_dung']}")
        print(f"    Thời điểm    : {item['thoi_diem_dung']}")
    print("=" * 60)


def print_suggested_chips(prescription: list[dict]) -> None:
    print("\nGoi y cau hoi (chip trong UI that se la nut bam):")
    print("  → Sáng nay tôi cần uống thuốc gì?")
    for item in prescription:
        print(f"  → Tác dụng phụ của {item['ten_thuoc']} là gì?")
    print(f"  → {prescription[0]['ten_thuoc']} nên uống lúc nào, bảo quản ra sao?")


def choose_case(client, corpus: dict[str, dict]) -> tuple[str, list[dict]]:
    print("\nChọn bệnh án để thử (thuốc lấy THẬT từ data pharmacy/):")
    print("  0. Đơn mẫu cố định (nhanh, không cần build)")
    for key, profile in CASE_PROFILES.items():
        print(f"  {key}. {profile['label']}")
    choice = input("Chọn (Enter = 1): ").strip() or "1"

    if choice == "0" or choice not in CASE_PROFILES:
        return "Đơn mẫu cố định", MOCK_PRESCRIPTION

    print(f"[setup] Đang build bệnh án #{choice} từ data pharmacy/ (gọi LLM rút gọn liều dùng nếu cần)...")
    return build_case(client, corpus, choice, DEFAULT_MODEL)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(f"[setup] Doc kho du lieu tu {DATA_DIR} ...")
    corpus = load_corpus()
    print(f"[setup] Da nap {len(corpus)} thuoc tham chieu.")
    print(f"[setup] Model dung de tra loi: {DEFAULT_MODEL} (doi qua bien CHATBOT_MODEL)")

    client = get_openai_client()

    label, prescription = choose_case(client, corpus)
    if not prescription:
        print("[LOI] Khong build duoc benh an nao co thuoc - kiem tra lai danh_muc.", file=sys.stderr)
        return 1

    print_prescription_overview(label, prescription)
    print_suggested_chips(prescription)

    print("\nGo cau hoi (vd: 'Metformin có tác dụng phụ gì?'), 'quit' de thoat.\n")
    while True:
        try:
            query = input("Bạn hỏi: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query or query.lower() in ("quit", "exit", "thoat"):
            break
        result = answer_question(client, query, prescription, corpus, DEFAULT_MODEL)
        print(f"\nChatbot: {result.reply}")
        if result.sources:
            print(f"  (nguồn: {result.sources})")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
