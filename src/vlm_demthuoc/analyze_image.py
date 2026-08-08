# -*- coding: utf-8 -*-
"""
Đếm thuốc trong một (hoặc nhiều) file ảnh có sẵn — không cần camera.

Dùng để kiểm tra và tinh chỉnh prompt trên bộ ảnh mẫu trước khi chạy live:

    python analyze_image.py anh1.jpg anh2.jpg
    python analyze_image.py mau/*.jpg --json ket_qua.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

from config import Settings, load_api_key
from providers import BASE_URL_PRESETS, BackendError
from vlm_client import PillCounter

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def parse_args() -> argparse.Namespace:
    defaults = Settings()
    parser = argparse.ArgumentParser(description="Đếm thuốc trong file ảnh bằng VLM.")
    parser.add_argument("images", nargs="+", help="Đường dẫn tới các file ảnh")
    parser.add_argument("--provider", choices=("claude", "openai"), default=defaults.provider)
    parser.add_argument("--base-url", default=defaults.base_url,
                        help=f"URL đầy đủ hoặc tên viết tắt: {', '.join(BASE_URL_PRESETS)}")
    parser.add_argument("--json-mode", choices=("schema", "object", "off"),
                        default=defaults.json_mode)
    parser.add_argument("--model", default=defaults.model)
    parser.add_argument("--effort", default=defaults.effort)
    parser.add_argument("--max-edge", type=int, default=defaults.max_image_edge)
    parser.add_argument("--no-blister", action="store_true",
                        help="Không đếm viên còn nằm trong vỉ")
    parser.add_argument("--json", default="", help="Ghi kết quả ra file .jsonl")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings(
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        json_mode=args.json_mode,
    )
    try:
        counter = PillCounter(
            api_key=load_api_key(settings.provider),
            provider=settings.provider,
            model=settings.model,
            base_url=settings.base_url,
            json_mode=settings.json_mode,
            effort=args.effort,
            max_image_edge=args.max_edge,
            count_pills_in_blister=not args.no_blister,
        )
    except BackendError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Model: {counter.describe()}", file=sys.stderr)

    out = Path(args.json).open("a", encoding="utf-8") if args.json else None
    failures = 0
    try:
        for raw_path in args.images:
            path = Path(raw_path)
            image = cv2.imread(str(path))
            if image is None:
                print(f"{path}: không đọc được ảnh.", file=sys.stderr)
                failures += 1
                continue

            result = counter.count(image)
            if not result.ok:
                print(f"{path}: LỖI — {result.error}", file=sys.stderr)
                failures += 1
                continue

            payload = {"file": str(path), **result.to_dict()}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            if out:
                out.write(json.dumps(payload, ensure_ascii=False) + "\n")
    finally:
        if out:
            out.close()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
