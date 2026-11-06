#!/usr/bin/env python3
"""Fetch waka-box Gist content and render it into README.md."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from html import escape
from pathlib import Path

START_MARKER = "<!-- waka-box start -->"
END_MARKER = "<!-- waka-box end -->"
LINE_PATTERN = re.compile(
    r"^(?P<language>.+?)\.+\s*(?P<time>.+?)\s+\.+\s*(?P<percent>\d+(?:\.\d+)?)%$"
)
BAR_COLORS = ("#41b883", "#00add8", "#2c2d72", "#3178c6", "#8b949e")


def fetch_gist(gist_id: str, token: str | None = None) -> str:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "waka-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(f"https://api.github.com/gists/{gist_id}",
                                     headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        gist = json.load(response)

    files = list(gist.get("files", {}).values())
    if not files:
        raise ValueError("Gist does not contain any files")

    gist_file = files[0]
    if gist_file.get("truncated"):
        raw_request = urllib.request.Request(gist_file["raw_url"],
                                             headers=headers)
        with urllib.request.urlopen(raw_request, timeout=30) as response:
            return response.read().decode("utf-8")

    content = gist_file.get("content")
    if not content:
        raise ValueError("Gist file is empty")
    return content


def parse_stats(content: str) -> list[tuple[str, str, float]]:
    stats = []
    for line in content.splitlines():
        if not line.strip():
            continue
        match = LINE_PATTERN.match(line.strip())
        if not match:
            raise ValueError(f"Unsupported Gist line: {line!r}")
        stats.append((
            match.group("language").strip(),
            re.sub(r"\s+", "", match.group("time")),
            float(match.group("percent")),
        ))
    if not stats:
        raise ValueError("Gist does not contain any statistics")
    return stats


def render_svg(stats: list[tuple[str, str, float]], dark: bool = False) -> str:
    width = 467
    height = 134
    row_height = 19
    bar_x = 184
    bar_width = 200
    rows = []

    for index, (language, duration, percent) in enumerate(stats):
        y = 46 + index * row_height
        fill_width = round(bar_width * max(0.0, min(100.0, percent)) / 100, 1)
        color = BAR_COLORS[index % len(BAR_COLORS)]
        rows.append(f'''  <g>
    <text class="label" x="24" y="{y}">{escape(language)}</text>
    <text class="muted" x="118" y="{y}">{escape(duration)}</text>
    <rect class="track" x="{bar_x}" y="{y - 9}" width="{bar_width}" height="7" rx="3.5" />
    <rect x="{bar_x}" y="{y - 9}" width="{fill_width}" height="7" rx="3.5" fill="{color}" />
    <text class="percent" x="443" y="{y}" text-anchor="end">{percent:.1f}%</text>
  </g>''')

    title_color = "#58a6ff" if dark else "#006aff"
    text_color = "#c9d1d9" if dark else "#417e87"
    muted_color = "#8b949e" if dark else "#417e87"
    track_color = "#30363d" if dark else "#e7edf0"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Weekly development breakdown</title>
  <desc id="desc">WakaTime language usage for the past week</desc>
  <style>
    text {{ font: 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: {text_color}; }}
    .title {{ font-size: 15px; font-weight: 600; fill: {title_color}; }}
    .label {{ font-weight: 600; }}
    .muted, .percent {{ fill: {muted_color}; }}
    .track {{ fill: {track_color}; }}
  </style>
  <rect width="466" height="133" x="0.5" y="0.5" rx="4.5" fill="transparent" />
  <text class="title" x="24" y="23">Weekly development breakdown</text>
{chr(10).join(rows)}
</svg>
'''


def render_block(gist_id: str) -> str:
    return "\n".join([
        START_MARKER,
        "",
        '<p align="center">',
        f'  <a href="https://gist.github.com/{gist_id}">',
        "    <picture>",
        '      <source media="(prefers-color-scheme: dark)" srcset="./profile/wakatime-dark.svg" />',
        '      <source media="(prefers-color-scheme: light)" srcset="./profile/wakatime.svg" />',
        '      <img src="./profile/wakatime.svg" width="100%" alt="Weekly development breakdown" />',
        "    </picture>",
        "  </a>",
        "</p>",
        "",
        "<!-- Powered by https://github.com/abordage/wakatime-box . -->",
        END_MARKER,
    ])


def update_readme(readme: str, block: str) -> str:
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError(
            "README must contain exactly one waka-box marker pair")
    start = readme.index(START_MARKER)
    end = readme.index(END_MARKER, start) + len(END_MARKER)
    return readme[:start] + block + readme[end:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gist-id", default=os.environ.get("GIST_ID"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--svg",
                        type=Path,
                        default=Path("profile/wakatime.svg"))
    parser.add_argument("--dark-svg",
                        type=Path,
                        default=Path("profile/wakatime-dark.svg"))
    args = parser.parse_args()

    if not args.gist_id:
        parser.error("--gist-id or GIST_ID is required")

    content = fetch_gist(args.gist_id, os.environ.get("GH_TOKEN"))
    stats = parse_stats(content)
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text(render_svg(stats), encoding="utf-8")
    args.dark_svg.write_text(render_svg(stats, dark=True), encoding="utf-8")
    block = render_block(args.gist_id)
    original = args.readme.read_text(encoding="utf-8")
    updated = update_readme(original, block)
    if updated != original:
        args.readme.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
