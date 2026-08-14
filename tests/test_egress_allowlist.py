"""Vong 2 (chatbot-rag-design.md muc 12.4) - test kien truc NHE: quet toan
bo `backend/*.py` xem co import TRUC TIEP 1 HTTP client (requests/httpx/aiohttp/
urllib.request) nao KHONG nam trong backend/egress_allowlist.py hay khong.

Hien tai: repo dung `openai`/`langchain_openai` SDK (goi httpx NOI BO nhu 1
dependency da vet, khong phai code tu viet) - KHONG co file nao trong backend/
truc tiep import requests/httpx/aiohttp/urllib.request, nen test nay hien
PASS voi 0 vi pham. Muc dich la REGRESSION GUARD: neu sau nay ai vo tinh (hoac
co y) them 1 duong goi ra ngoai khong qua allowlist, test nay phai bat duoc,
khong duoc de lot qua am tham."""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.egress_allowlist import ALLOWED_EGRESS_MODULES  # noqa: E402

_NETWORK_CLIENT_MODULES = {"requests", "httpx", "aiohttp", "urllib.request"}
_BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"

# Thu muc nam DUOI backend/ nhung khong phai code cua app - bo qua khi quet.
# `.venv` la venv dev cua may nay (hang chuc nghin file site-packages, trong do
# co ca requests/httpx that) - quet vao la test chay rat lau va fail hang loat
# voi vi pham cua thu vien ben thu ba, khong phai code repo. Truoc khi doi ten
# src/ -> backend/, venv nam ngoai cay bi quet nen khong can loai tru.
# vlm_demthuoc KHONG bi loai: no da nam trong pham vi quet tu truoc (src/
# vlm_demthuoc/), giu nguyen de khong am tham thu hep guard.
_SKIP_DIRS = {".venv", "__pycache__"}


def _imports_network_client(py_file: Path) -> bool:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name in _NETWORK_CLIENT_MODULES for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module in _NETWORK_CLIENT_MODULES:
                return True
    return False


def test_no_direct_network_client_import_outside_allowlist():
    violations = []
    for py_file in _BACKEND_ROOT.rglob("*.py"):
        if _SKIP_DIRS & set(py_file.relative_to(_BACKEND_ROOT).parts):
            continue
        rel_path = py_file.relative_to(_BACKEND_ROOT.parent).as_posix()
        if _imports_network_client(py_file) and rel_path not in ALLOWED_EGRESS_MODULES:
            violations.append(rel_path)

    assert violations == [], (
        f"File(s) import truc tiep 1 HTTP client nhung KHONG nam trong "
        f"backend/egress_allowlist.py::ALLOWED_EGRESS_MODULES: {violations}. "
        "Them vao allowlist (kem ly do) neu day la duong goi ra ngoai duoc "
        "chu dinh, hoac xoa import neu khong can thiet."
    )


def test_allowlist_entries_still_exist_as_files():
    """Neu 1 entry trong allowlist bi doi ten file/xoa ma khong cap nhat
    allowlist, list se am tham "bao ve" 1 file khong con ton tai - bat loi
    nay som thay vi de allowlist stale."""
    for rel_path in ALLOWED_EGRESS_MODULES:
        full_path = Path(__file__).resolve().parent.parent / rel_path
        assert full_path.is_file(), f"Allowlist tro toi file khong ton tai: {rel_path}"
