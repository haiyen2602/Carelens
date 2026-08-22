"""Danh sach chat bi kiem soat - chan ngay o buoc TAO yeu cau bo sung thuoc.

Vi sao chan o buoc tao chu khong doi toi buoc duyet: bac si nhan phan hoi ngay
thay vi cho, va admin khong bao gio phai nhin thay loai yeu cau nay trong hang
doi. Mot canh cua it nguoi di qua thi it co co hoi bam nham.

GIOI HAN CAN BIET: day KHONG phai allowlist. FB-14 duoc va vi danh muc thuoc
la tap dong; duong `drug_request` mo lai loi ghi ten tu do, chi khac la co
admin dung giua. Danh sach nay thu hep be mat do, KHONG dong lai duoc.

[CAN CHOT - can nguoi co chuyen mon y te/phap ly soat lai]
Danh sach duoi day la tap KHOI DAU do dev dat, KHONG phai trich xuat day du
tu van ban phap quy. Viet Nam co danh muc thuoc gay nghien / huong than /
tien chat ban hanh theo thong tu cua Bo Y te - can doi chieu va bo sung.
Dung coi danh sach nay la da du.

Cach so khop: bo dau, thuong hoa, roi tim chuoi con. "Heroin", "heroine",
"HEROIN 10mg" deu dinh. Doi lai se co false positive (mot ten thuong mai hop
le co the chua chuoi con trung) - chap nhan duoc: bac si bi tu choi con doi
duoc, con thuoc bi kiem soat lot vao don thi khong.
"""

from __future__ import annotations

import unicodedata

# Ten hoat chat, khong phai ten thuong mai. Viet thuong, khong dau.
CHAT_BI_KIEM_SOAT: frozenset[str] = frozenset(
    {
        # Opioid
        "heroin",
        "diacetylmorphin",
        "diamorphin",
        "morphin",
        "morphine",
        "fentanyl",
        "sufentanil",
        "remifentanil",
        "pethidin",
        "meperidin",
        "methadon",
        "buprenorphin",
        "oxycodon",
        "hydromorphon",
        "codein",
        "tramadol",
        # Chat kich thich
        "amphetamin",
        "methamphetamin",
        "metamfetamin",
        "cocain",
        "cocaine",
        "methylphenidat",
        "modafinil",
        # Huong than / an than
        "ketamin",
        "midazolam",
        "diazepam",
        "alprazolam",
        "clonazepam",
        "lorazepam",
        "phenobarbital",
        "zolpidem",
        # Tien chat / chat gay ao giac
        "ephedrin",
        "pseudoephedrin",
        "ergotamin",
        "lysergid",
        "psilocybin",
        "cannabis",
        "tetrahydrocannabinol",
    }
)


def _chuan_hoa(chuoi: str) -> str:
    """Bo dau tieng Viet + thuong hoa, de so khop khong phu thuoc cach go."""
    khong_dau = unicodedata.normalize("NFD", chuoi)
    khong_dau = "".join(ky_tu for ky_tu in khong_dau if unicodedata.category(ky_tu) != "Mn")
    return khong_dau.lower().strip()


def tim_chat_bi_kiem_soat(ten_thuoc: str) -> str | None:
    """Tra ve ten chat bi chan neu `ten_thuoc` chua no, None neu khong.

    Tra ve chinh chuoi khop (thay vi True/False) de thong bao loi noi duoc ro
    la vuong o dau - bac si go mot ten thuong mai dai se khong doan noi vi sao
    bi tu choi neu chi nhan mot cau chung chung.
    """
    chuan = _chuan_hoa(ten_thuoc)
    for chat in CHAT_BI_KIEM_SOAT:
        if chat in chuan:
            return chat
    return None
