#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path


BLOCKED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}

BLOCKED_EXTS = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".mp4",
    ".zip",
    ".7z",
    ".rar",
    ".xlsx",
    ".xls",
    ".pdf",
}

PATTERNS = [
    (
        "credential env assignment",
        re.compile(
            r"^\s*(?:\$env:|export\s+)?[A-Z0-9_]*(?:API[_-]?KEY|APP[_-]?SECRET|"
            r"SECRET|ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|PASSWORD|PASSWD|WEBHOOK)[A-Z0-9_]*\s*=\s*"
            r"['\"]?(?!$|replace|your-|YOUR_|change-me|test|pw\b|admin@example\.local|"
            r"0\b|1\b|11\b|false\b|true\b)[^'\"\s]{8,}"
        ),
    ),
    (
        "credential literal",
        re.compile(
            r"(?i)(api[_-]?key|app[_-]?secret|access[_-]?token|refresh[_-]?token|"
            r"password|passwd|authorization|bearer|webhook)\s*[:=]\s*['\"]"
            r"(?!$|replace|your-|YOUR_|change-me|test|pw\b|admin@example\.local|"
            r"Bearer user-|Bearer admin-|Bearer test-|Bearer wrong)[^'\"]{8,}['\"]"
        ),
    ),
    ("private ip", re.compile(r"\b(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|192\.168\.\d+\.\d+)\b")),
    ("public ip literal", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
    ("windows user path", re.compile(r"(?i)c:\\\\users\\\\[^\\\\]+")),
    ("source machine path", re.compile(r"(?i)d:\\\\forjarvis")),
    ("ssh key path", re.compile(r"(?i)(?:^|[\\/])\.ssh(?:[\\/]|$)|id_rsa")),
    ("long numeric id", re.compile(r"\b\d{12,20}\b")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone-like number", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
]

ALLOW_LINE = re.compile(
    r"(replace-with|YOUR_PUBLIC_HOST|127\.0\.0\.1|localhost|example\.local|Demo Shop|admin@example\.local|"
    r"Bearer test-token|Bearer other-token|admin-token|system-token|13800138000|0\.0\.0\.0|"
    r"api\.oceanengine\.com|qyapi\.weixin\.qq\.com|\.env\.example)",
    re.I,
)


def iter_text_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in BLOCKED_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in BLOCKED_EXTS:
                yield path, "blocked artifact type", 0, ""
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:8192]:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            yield path, None, None, text


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    findings = []

    for path, artifact_error, _, text in iter_text_files(root):
        rel = path.relative_to(root)
        if str(rel).replace("\\", "/") == "scripts/public_safety_scan.py":
            continue
        if artifact_error:
            findings.append((str(rel), 0, artifact_error, ""))
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if ALLOW_LINE.search(line):
                continue
            for label, pattern in PATTERNS:
                if label == "credential env assignment":
                    rel_text = str(rel).replace("\\", "/")
                    if not (
                        rel_text.endswith(".env")
                        or rel_text.endswith(".env.example")
                        or path.suffix.lower() in {".ps1", ".toml", ".yaml", ".yml", ".json"}
                    ):
                        continue
                if pattern.search(line):
                    preview = line.strip()
                    if len(preview) > 140:
                        preview = preview[:137] + "..."
                    findings.append((str(rel), line_no, label, preview))
                    break

    if findings:
        print("Potential public-safety findings:")
        for rel, line_no, label, preview in findings:
            location = f"{rel}:{line_no}" if line_no else rel
            print(f"- {location} [{label}] {preview}")
        return 1

    print("No public-safety findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
