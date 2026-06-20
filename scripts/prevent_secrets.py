#!/usr/bin/env python3
"""Pre-commit hook：阻擋 .env 與疑似 API Key 被提交。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 禁止提交的檔名
BLOCKED_FILENAMES = {".env", ".env.local", ".env.production", ".env.development"}

# 允許出現在範例檔中的 placeholder
ALLOWED_PLACEHOLDERS = {
    "",
    "your_api_key_here",
    "YOUR_API_KEY",
    "changeme",
    "xxx",
}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GEMINI_API_KEY 赋值", re.compile(r"GEMINI_API_KEY\s*=\s*['\"]?([^\s'\"#]+)", re.I)),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z\-_]{20,}")),
    ("Generic Bearer/Key", re.compile(r"(?:api[_-]?key|secret|token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{16,})", re.I)),
]


def _is_blocked_filename(path: Path) -> bool:
    name = path.name.lower()
    return name in BLOCKED_FILENAMES or name.startswith(".env")


def _scan_content(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"無法讀取 {path}: {exc}"]

    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1) if match.lastindex else match.group(0)
            value = (value or "").strip().strip("'\"")
            if value.lower() in ALLOWED_PLACEHOLDERS:
                continue
            if label.startswith("GEMINI") and ("example" in path.name or "sample" in path.name):
                continue
            issues.append(f"{path}: 偵測到 {label}")
            break
    return issues


def main() -> int:
    files = [Path(arg) for arg in sys.argv[1:] if arg.strip()]
    if not files:
        return 0

    errors: list[str] = []
    for path in files:
        if not path.is_file():
            continue
        if _is_blocked_filename(path):
            errors.append(f"禁止提交敏感設定檔：{path}")
            continue
        if path.suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".db", ".pyc"}:
            continue
        errors.extend(_scan_content(path))

    if errors:
        print("pre-commit 安全檢查未通過：")
        for item in errors:
            print(f"  - {item}")
        print("\n請移除 API Key / .env 後再提交。金鑰請只放在本機 .env 或 Render 環境變數。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
