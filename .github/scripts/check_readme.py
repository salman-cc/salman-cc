#!/usr/bin/env python3
"""Validate the profile README and SVG assets before merge.

Catches broken relative asset links, malformed SVG XML, missing automation
markers, stale account handles, or inline HTML markup that GitHub's sanitizer
would strip.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

README = Path("README.md")
ASSETS_DIR = Path("assets")

MARKERS = [
    ("<!-- COUNTERS:START -->", "<!-- COUNTERS:END -->"),
    ("<!-- ACTIVITY:START -->", "<!-- ACTIVITY:END -->"),
]

STYLE_RULES = [
    ("\u2014", "em dash. Use a comma, a colon, a full stop, or split the sentence."),
    ("\u2013", "en dash in prose. Use a hyphen or rewrite."),
    ("\u201c", "curly opening quote. Use a straight quote."),
    ("\u201d", "curly closing quote. Use a straight quote."),
    ("\u2018", "curly opening apostrophe. Use a straight apostrophe."),
    ("\u2019", "curly apostrophe. Use a straight apostrophe."),
]

AI_PHRASES = [
    "delve", "tapestry", "testament to", "underscores", "showcases", "showcasing",
    "pivotal", "intricate", "fostering", "bolsters", "garnered", "myriad",
    "plethora", "seamless", "seamlessly", "cutting-edge", "in the realm of",
    "it is important to note", "it's important to note", "in conclusion",
    "furthermore", "moreover", "a wide range of", "wide array of",
    "serves as a", "stands as a", "nestled", "vibrant", "robust solution",
]

FORBIDDEN_PATTERNS = [
    (r"<style\b", "inline <style> tags are stripped by GitHub"),
    (r"<script\b", "inline <script> tags are stripped by GitHub"),
    (r"<svg\b", "inline <svg> is stripped by GitHub; reference an SVG file instead"),
    (r"\bclass\s*=", "class attributes are stripped by GitHub; use align="),
    (r"\bid\s*=", "id attributes are stripped by GitHub"),
]

RELATIVE_ASSET = re.compile(r"(?:src|srcset|href)=\"((?!https?://|#|mailto:)[^\"]+)\"")
RELATIVE_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def relative_targets(content: str) -> set[str]:
    """Collect every repository-relative path referenced by the README."""
    targets = set()
    for match in RELATIVE_ASSET.findall(content) + RELATIVE_LINK.findall(content):
        if match.startswith(("http://", "https://", "#", "mailto:", "data:")):
            continue
        targets.add(match)
    return targets


def validate_svgs(problems: list[str]) -> None:
    """Verify every SVG file under assets/ is well-formed XML."""
    if not ASSETS_DIR.exists():
        return
    for svg_file in sorted(ASSETS_DIR.glob("*.svg")):
        if svg_file.stat().st_size == 0:
            problems.append(f"SVG asset is empty: {svg_file}")
            continue
        try:
            ET.parse(svg_file)
        except ET.ParseError as exc:
            problems.append(f"Invalid XML in {svg_file}: {exc}")


def main() -> int:
    if not README.exists():
        print(f"::error::{README} is missing.")
        return 1

    content = README.read_text(encoding="utf-8")
    problems: list[str] = []

    for start, end in MARKERS:
        if content.count(start) != 1 or content.count(end) != 1:
            problems.append(
                f"Marker pair {start} / {end} must appear exactly once "
                f"(found {content.count(start)} / {content.count(end)})."
            )
        elif content.index(start) > content.index(end):
            problems.append(f"Marker pair {start} / {end} is out of order.")

    if "ccsalman545" in content:
        problems.append("README still references old GitHub username 'ccsalman545'.")

    for path in sorted(relative_targets(content)):
        target = Path(path.split("?")[0].split("#")[0])
        if target.is_absolute() or not target.exists():
            problems.append(f"Referenced path does not exist: {path}")
        elif target.suffix.lower() == ".svg" and target.stat().st_size == 0:
            problems.append(f"SVG asset is empty: {path}")

    validate_svgs(problems)

    seen_style: list[str] = []
    for needle, reason in STYLE_RULES:
        if needle in content:
            seen_style.append(reason)
    if seen_style:
        problems.append("House style: " + "; ".join(sorted(set(seen_style))) + ".")

    hits = sorted({phrase for phrase in AI_PHRASES if phrase in content.lower()})
    if hits:
        problems.append(
            "Phrasing to rewrite (reads as machine-written): " + ", ".join(hits) + "."
        )

    for pattern, reason in FORBIDDEN_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            problems.append(f"README contains markup GitHub will remove: {reason}.")

    if len(content.encode("utf-8")) > 512_000:
        problems.append("README exceeds 512 KB; GitHub will refuse to render it.")

    for problem in problems:
        print(f"::error::{problem}")

    if problems:
        print(f"\n{len(problems)} problem(s) found.")
        return 1

    labels = re.findall(r"<!--\s*(.*?)\s*-->", "".join(start for start, _ in MARKERS))
    markers = ", ".join(labels)
    print(f"README checks passed ({len(content):,} characters, markers: {markers}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
