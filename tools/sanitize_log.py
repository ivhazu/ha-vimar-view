#!/usr/bin/env python3
"""Mask personal data in a Vimar log or capture before posting it publicly.

Usage:  python sanitize_log.py vimar_log.txt            -> writes vimar_log.sanitized.txt
        python sanitize_log.py flows.txt out.txt

Masks: e-mail addresses, DUIDs, UUIDs (plant/user/routine ids), JWT and session
tokens, passwords and secrets, GPS coordinates. Device ids (idsf), device types
(SS_/SF_/SFE_) and values are kept: they are what we need to support a device.
Always read the result before publishing it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RULES: list[tuple[str, str]] = [
    (r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "<JWT>"),
    (r"token-[0-9a-fA-F\-]{36}", "<SESSION_TOKEN>"),
    (r'("(?:token|password|passw|secret|plantsecret|refresh_token|access_token|code)"\s*:\s*")[^"]*(")', r"\1<MASKED>\2"),
    (r"((?:access_token|refresh_token|code|password)=)[^&\s\"']+", r"\1<MASKED>"),
    (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "<EMAIL>"),
    (r"\b0\d{5}[A-Z]{3}\d{5}\b", "<DUID>"),
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "<UUID>"),
    (r'("(?:latitude|longitude)"\s*:\s*)-?\d+(?:\.\d+)?', r"\1 0.0"),
]


def sanitize(text: str) -> str:
    for pattern, repl in RULES:
        text = re.sub(pattern, repl, text)
    return text


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".sanitized" + src.suffix)
    dst.write_text(sanitize(src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    print(f"Written {dst} - please read it before publishing.")


if __name__ == "__main__":
    main()
