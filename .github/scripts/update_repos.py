#!/usr/bin/env python3
"""Refresh GitHub telemetry SVG, plain-text fallback counters, and Shields JSON.

All statistics come directly from the official GitHub REST and GraphQL APIs
using only Python's standard library. Rendering the telemetry card to a local
SVG inside ``assets/github-telemetry.svg`` eliminates broken external widget
hosts while keeping a plain Markdown fallback block in ``README.md``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from profile_common import (  # noqa: E402
    github_graphql,
    github_json,
    is_profile_repo,
    iso_date,
    replace_block,
    username,
    xml_escape,
)

README = Path(os.environ.get("README_PATH", "README.md"))
DATA_DIR = Path(os.environ.get("DATA_PATH", "data"))
TELEMETRY_SVG = Path(os.environ.get("TELEMETRY_SVG", "assets/github-telemetry.svg"))

COUNTERS_START = "<!-- COUNTERS:START -->"
COUNTERS_END = "<!-- COUNTERS:END -->"

GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
  }
}
"""

# Group closely related build/hardware file types into clear engineering buckets
# while keeping every number strictly derived from GitHub's Languages API.
LANGUAGE_GROUPS: dict[str, str] = {
    "C": "C (Firmware & Systems)",
    "C++": "C / C++",
    "Makefile": "Make & CMake",
    "CMake": "Make & CMake",
    "JavaScript": "JavaScript & TypeScript",
    "TypeScript": "JavaScript & TypeScript",
    "Python": "Python",
    "Shell": "Shell & QML (Linux)",
    "QML": "Shell & QML (Linux)",
    "Assembly": "ARM Assembly & Linker",
    "Linker Script": "ARM Assembly & Linker",
    "Verilog": "Verilog / HDL",
    "SystemVerilog": "Verilog / HDL",
    "VHDL": "Verilog / HDL",
}

IGNORED_LANGUAGES = {"HTML", "CSS", "Dockerfile", "Procfile"}


def fetch_account() -> dict:
    return github_json(f"/users/{username()}")


def fetch_repositories() -> tuple[list[dict], list[dict]]:
    """Return (all public repos, original non-fork active repos excluding profile repo)."""
    payload = github_json(f"/users/{username()}/repos?per_page=100&sort=pushed")
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected payload shape for the repositories endpoint.")

    all_public = [r for r in payload if isinstance(r, dict) and not r.get("disabled")]
    original = [
        r
        for r in all_public
        if not r.get("fork")
        and not r.get("archived")
        and not is_profile_repo(r.get("full_name", ""))
    ]
    return all_public, original


def fetch_language_breakdown(original_repos: list[dict]) -> tuple[list[tuple[str, int, int]], int]:
    """Return ([(group_label, repo_count, byte_total), ...], distinct_raw_lang_count)."""
    raw_languages: set[str] = set()
    group_repos: dict[str, set[str]] = {}
    group_bytes: dict[str, int] = {}

    for repo in original_repos:
        name = repo.get("name", "")
        if not name:
            continue
        langs = github_json(f"/repos/{username()}/{name}/languages")
        if not isinstance(langs, dict):
            continue
        for lang, byte_count in langs.items():
            raw_languages.add(lang)
            if lang in IGNORED_LANGUAGES:
                continue
            label = LANGUAGE_GROUPS.get(lang, lang)
            group_repos.setdefault(label, set()).add(name)
            group_bytes[label] = group_bytes.get(label, 0) + int(byte_count or 0)

    ranked = sorted(
        [(label, len(repos), group_bytes.get(label, 0)) for label, repos in group_repos.items()],
        key=lambda item: (-item[1], -item[2], item[0]),
    )
    return ranked[:6], len(raw_languages)


def fallback_calendar() -> dict:
    """Build an empty 53-week calendar structure when GraphQL is unavailable."""
    today = datetime.now(timezone.utc).date()
    # Align start to Sunday 52 weeks ago
    start = today - timedelta(days=today.weekday() + 1 + 52 * 7)
    weeks: list[dict] = []
    cursor = start
    while cursor <= today:
        days: list[dict] = []
        for _ in range(7):
            if cursor <= today:
                days.append({"contributionCount": 0, "date": cursor.isoformat()})
            cursor += timedelta(days=1)
        weeks.append({"contributionDays": days})
    return {
        "totalContributions": 0,
        "totalCommitContributions": 0,
        "totalPullRequestContributions": 0,
        "weeks": weeks[-53:],
    }


def fetch_contributions() -> dict:
    """Fetch 52-week contribution calendar from GitHub GraphQL with graceful fallback."""
    data = github_graphql(GRAPHQL_QUERY, {"login": username()})
    if not data:
        return fallback_calendar()
    collection = (data.get("user") or {}).get("contributionsCollection") or {}
    calendar = collection.get("contributionCalendar") or {}
    weeks = calendar.get("weeks") or []
    if not weeks:
        return fallback_calendar()
    return {
        "totalContributions": int(calendar.get("totalContributions") or 0),
        "totalCommitContributions": int(collection.get("totalCommitContributions") or 0),
        "totalPullRequestContributions": int(collection.get("totalPullRequestContributions") or 0),
        "weeks": weeks[-53:],
    }


def cell_color(count: int) -> str:
    """Map daily contribution counts to the dark + #FF6B35 Signal Orange ramp."""
    if count <= 0:
        return "#151B28"
    if count <= 3:
        return "#4E2518"
    if count <= 9:
        return "#8A391D"
    if count <= 19:
        return "#C85028"
    return "#FF6B35"


def render_telemetry_svg(
    *,
    public_repos: int,
    non_fork_total: int,
    original_count: int,
    fork_count: int,
    distinct_langs: int,
    languages: list[tuple[str, int, int]],
    contributions: dict,
    last_pushed_label: str,
) -> str:
    """Render the 880x356 dark-themed #FF6B35 telemetry dashboard SVG."""
    weeks = contributions["weeks"]
    total_contrib = contributions["totalContributions"]
    total_commits = contributions["totalCommitContributions"]
    total_prs = contributions["totalPullRequestContributions"]

    all_days = [d for w in weeks for d in (w.get("contributionDays") or [])]
    active_days = sum(1 for d in all_days if int(d.get("contributionCount") or 0) > 0)
    peak_day = max((int(d.get("contributionCount") or 0) for d in all_days), default=0)

    c_repos = next((cnt for label, cnt, _ in languages if label.startswith("C ")), 0)

    # Build heatmap cells and non-overlapping month labels
    grid_x0 = 64.0
    grid_y0 = 194.0
    step = 8.6
    heatmap_rects: list[str] = []
    month_labels: list[str] = []
    last_month = None
    last_label_x = -100.0

    for col_idx, week in enumerate(weeks):
        days = week.get("contributionDays") or []
        x = grid_x0 + col_idx * step
        if days:
            first_date = days[0].get("date", "")
            if len(first_date) >= 7:
                month_num = first_date[5:7]
                if month_num != last_month:
                    last_month = month_num
                    if x - last_label_x >= 30.0 and x <= 492.0:
                        try:
                            m_name = datetime.fromisoformat(first_date).strftime("%b")
                        except ValueError:
                            m_name = ""
                        if m_name:
                            month_labels.append(
                                f'      <text x="{x:.1f}" y="185" font-size="8.5" fill="#64748B">{m_name}</text>'
                            )
                            last_label_x = x

        for row_idx, day in enumerate(days[:7]):
            y = grid_y0 + row_idx * step
            cnt = int(day.get("contributionCount") or 0)
            fill = cell_color(cnt)
            heatmap_rects.append(
                f'      <rect x="{x:.1f}" y="{y:.1f}" width="7" height="7" rx="1.6" fill="{fill}"/>'
            )

    # Build horizontal language bars
    max_repos = max((cnt for _, cnt, _ in languages), default=1)
    bar_colors = ["#FF6B35", "#FF7F4D", "#FF9468", "#E0A890", "#94A3B8", "#64748B"]
    lang_rows: list[str] = []
    for idx, (label, repo_cnt, _) in enumerate(languages[:6]):
        row_y = 186 + idx * 22
        bar_y = row_y + 5
        width_px = max(18.0, round(276.0 * (repo_cnt / max_repos), 1))
        color = bar_colors[min(idx, len(bar_colors) - 1)]
        noun = "repo" if repo_cnt == 1 else "repos"
        lang_rows.append(
            f'      <text x="564" y="{row_y}" font-family="\'Inter\', -apple-system, BlinkMacSystemFont, \'Segoe UI\', \'DejaVu Sans\', sans-serif" font-size="10.2" font-weight="600" fill="#E2E8F0">{xml_escape(label)}</text>\n'
            f'      <text x="840" y="{row_y}" text-anchor="end" font-family="\'JetBrains Mono\', ui-monospace, SFMono-Regular, Menlo, Consolas, \'DejaVu Sans Mono\', monospace" font-size="9.2" fill="#94A3B8">{repo_cnt} {noun}</text>\n'
            f'      <rect x="564" y="{bar_y}" width="276" height="4" rx="2" fill="#161D2B"/>\n'
            f'      <rect x="564" y="{bar_y}" width="{width_px}" height="4" rx="2" fill="{color}"/>'
        )

    legend_x0 = 428
    legend_colors = ["#151B28", "#4E2518", "#8A391D", "#C85028", "#FF6B35"]
    legend_swatches = "\n".join(
        f'      <rect x="{legend_x0 + i * 11}" y="308" width="8" height="8" rx="1.6" fill="{c}"/>'
        for i, c in enumerate(legend_colors)
    )

    user_upper = xml_escape(username().upper())

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="880" height="356" viewBox="0 0 880 356" role="img" aria-labelledby="telTitle telDesc">
  <title id="telTitle">GitHub Engineering Telemetry for @{xml_escape(username())}</title>
  <desc id="telDesc">{public_repos} public repositories ({original_count} original), {total_contrib} contributions in the last year ({total_commits} commits, {total_prs} pull requests), 52-week contribution heatmap, and language breakdown across original repositories.</desc>

  <defs>
    <linearGradient id="telBg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#090C12"/>
      <stop offset="100%" stop-color="#0D111A"/>
    </linearGradient>
    <clipPath id="telClip">
      <rect x="0.5" y="0.5" width="879" height="355" rx="12"/>
    </clipPath>
  </defs>

  <g clip-path="url(#telClip)">
    <rect width="880" height="356" fill="url(#telBg)"/>

    <!-- Header Bar -->
    <line x1="0" y1="42" x2="880" y2="42" stroke="#1B2230" stroke-width="1"/>
    <rect x="22" y="16" width="8" height="8" rx="2" fill="#FF6B35"/>
    <text x="38" y="24.5" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="10.5" font-weight="600" letter-spacing="1.1" fill="#CBD5E1">GITHUB TELEMETRY // @{user_upper}</text>
    <text x="858" y="24.5" text-anchor="end" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="9.5" fill="#64748B">VERIFIED VIA GITHUB API · LATEST PUSH {xml_escape(last_pushed_label.upper())}</text>

    <!-- KPI Row -->
    <g>
      <!-- Tile 1 -->
      <rect x="22" y="56" width="198" height="72" rx="8" fill="#101520" stroke="#21293A" stroke-width="1"/>
      <text x="36" y="75" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="9" letter-spacing="0.8" fill="#8B98AE">PUBLIC REPOSITORIES</text>
      <text x="36" y="101" font-family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'DejaVu Sans', sans-serif" font-size="21" font-weight="700" fill="#F8FAFC">{public_repos}</text>
      <text x="36" y="118" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="8.8" fill="#64748B">{non_fork_total} non-fork · {fork_count} fork</text>

      <!-- Tile 2 -->
      <rect x="234" y="56" width="198" height="72" rx="8" fill="#101520" stroke="#21293A" stroke-width="1"/>
      <text x="248" y="75" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="9" letter-spacing="0.8" fill="#8B98AE">CONTRIBUTIONS (1Y)</text>
      <text x="248" y="101" font-family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'DejaVu Sans', sans-serif" font-size="21" font-weight="700" fill="#FF6B35">{total_contrib}</text>
      <text x="248" y="118" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="8.8" fill="#64748B">{total_commits} commits · {total_prs} PRs</text>

      <!-- Tile 3 -->
      <rect x="446" y="56" width="198" height="72" rx="8" fill="#101520" stroke="#21293A" stroke-width="1"/>
      <text x="460" y="75" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="9" letter-spacing="0.8" fill="#8B98AE">PRIMARY ENGINEERING</text>
      <text x="460" y="101" font-family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'DejaVu Sans', sans-serif" font-size="19.5" font-weight="700" fill="#F8FAFC">C / Embedded</text>
      <text x="460" y="118" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="8.8" fill="#FF6B35">{c_repos} firmware &amp; Linux repos</text>

      <!-- Tile 4 -->
      <rect x="658" y="56" width="200" height="72" rx="8" fill="#101520" stroke="#21293A" stroke-width="1"/>
      <text x="672" y="75" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="9" letter-spacing="0.8" fill="#8B98AE">DETECTED LANGUAGES</text>
      <text x="672" y="101" font-family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'DejaVu Sans', sans-serif" font-size="21" font-weight="700" fill="#F8FAFC">{distinct_langs}</text>
      <text x="672" y="118" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="8.8" fill="#64748B">across {original_count} original repos</text>
    </g>

    <!-- Left Bento: 52-Week Contribution Heatmap -->
    <g>
      <rect x="22" y="140" width="514" height="196" rx="8" fill="#101520" stroke="#21293A" stroke-width="1"/>
      <text x="38" y="162" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="9.5" font-weight="700" letter-spacing="0.8" fill="#CBD5E1">CONTRIBUTION ACTIVITY · 52 WEEKS</text>
      <text x="520" y="162" text-anchor="end" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="9" fill="#8B98AE">{active_days} active days · peak {peak_day}/day</text>

      <!-- Weekday labels -->
      <g font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="8" fill="#64748B">
        <text x="38" y="208.5">Mon</text>
        <text x="38" y="225.7">Wed</text>
        <text x="38" y="242.9">Fri</text>
      </g>

      <!-- Month labels -->
      <g font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace">
{chr(10).join(month_labels)}
      </g>

      <!-- Calendar cells -->
{chr(10).join(heatmap_rects)}

      <!-- Heatmap footer & legend -->
      <line x1="38" y1="296" x2="520" y2="296" stroke="#1B2333" stroke-width="1"/>
      <text x="38" y="315" font-family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'DejaVu Sans', sans-serif" font-size="10" fill="#8B98AE">STM32H7 firmware, native C WebRTC &amp; Linux systems</text>
      <text x="400" y="315" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="8.5" fill="#64748B">Less</text>
{legend_swatches}
      <text x="488" y="315" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="8.5" fill="#64748B">More</text>
    </g>

    <!-- Right Bento: Language Breakdown -->
    <g>
      <rect x="550" y="140" width="308" height="196" rx="8" fill="#101520" stroke="#21293A" stroke-width="1"/>
      <text x="564" y="162" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="9.5" font-weight="700" letter-spacing="0.8" fill="#CBD5E1">MOST-USED LANGUAGES (NON-FORK)</text>

{chr(10).join(lang_rows)}

      <text x="564" y="325" font-family="'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="8.3" fill="#64748B">Ranked by active repository count via GitHub Linguist</text>
    </g>
  </g>

  <rect x="0.5" y="0.5" width="879" height="355" rx="12" fill="none" stroke="#222938" stroke-width="1"/>
</svg>
"""


def render_counters_markdown(
    *,
    public_repos: int,
    original_count: int,
    total_contrib: int,
    total_commits: int,
    languages: list[tuple[str, int, int]],
    last_pushed_label: str,
) -> str:
    """Plain-Markdown fallback telemetry line that works even if images are disabled."""
    top_names = ", ".join(label.split(" (")[0] for label, _, _ in languages[:4])
    user = username()
    return (
        f"<sub>"
        f"**Snapshot** ([all {public_repos} public repositories](https://github.com/{user}?tab=repositories)): "
        f"`{original_count}` original repositories · "
        f"`{total_contrib}` contributions in the past year (`{total_commits}` commits) · "
        f"Core stack: `{top_names}` · "
        f"Latest push: `{last_pushed_label}`"
        f"</sub>"
    )


def endpoint(label: str, message: str, color: str, named_logo: str | None = None) -> dict:
    """Shields.io endpoint schema payload."""
    payload = {
        "schemaVersion": 1,
        "label": label,
        "message": str(message),
        "color": color,
        "cacheSeconds": 43200,
        "style": "flat-square",
    }
    if named_logo:
        payload["namedLogo"] = named_logo
    return payload


def write_data(
    stars: int, forks: int, public_repos: int, followers: int, languages: int, refreshed: str
) -> bool:
    """Publish Shields endpoint JSON files; return True when anything changed."""
    files = {
        "stars.json": endpoint("stars", stars, "FF6B35", "github"),
        "forks.json": endpoint("forks", forks, "1E2430", "github"),
        "repos.json": endpoint("repositories", public_repos, "FF6B35", "github"),
        "followers.json": endpoint("followers", followers, "1E2430", "github"),
        "languages.json": endpoint("languages", languages, "FF6B35"),
        "updated.json": endpoint("latest push", refreshed, "1E2430"),
    }

    changed = False
    for filename, payload in files.items():
        target = DATA_DIR / filename
        rendered = json.dumps(payload, indent=2) + "\n"
        if target.exists() and target.read_text(encoding="utf-8") == rendered:
            continue
        target.write_text(rendered, encoding="utf-8")
        changed = True
    return changed


def main() -> int:
    try:
        account = fetch_account()
        all_public, original_repos = fetch_repositories()
        languages, distinct_langs = fetch_language_breakdown(original_repos)
        contributions = fetch_contributions()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"::error::{error}")
        return 1

    public_repos = int(account.get("public_repos") or len(all_public))
    followers = int(account.get("followers") or 0)
    original_count = len(original_repos)
    fork_count = sum(1 for r in all_public if r.get("fork"))
    stars = sum(int(r.get("stargazers_count") or 0) for r in original_repos)
    forks = sum(int(r.get("forks_count") or 0) for r in original_repos)

    latest_iso = max((r.get("pushed_at") or "" for r in original_repos), default="")
    last_pushed_label = iso_date(latest_iso) if latest_iso else "recently"

    non_fork_total = sum(1 for r in all_public if not r.get("fork"))

    svg_content = render_telemetry_svg(
        public_repos=public_repos,
        non_fork_total=non_fork_total,
        original_count=original_count,
        fork_count=fork_count,
        distinct_langs=distinct_langs,
        languages=languages,
        contributions=contributions,
        last_pushed_label=last_pushed_label,
    )
    TELEMETRY_SVG.parent.mkdir(parents=True, exist_ok=True)
    svg_changed = not TELEMETRY_SVG.exists() or TELEMETRY_SVG.read_text(encoding="utf-8") != svg_content
    if svg_changed:
        TELEMETRY_SVG.write_text(svg_content, encoding="utf-8")

    readme_changed = False
    if README.exists():
        content = README.read_text(encoding="utf-8")
        if COUNTERS_START in content and COUNTERS_END in content:
            updated = replace_block(
                content,
                COUNTERS_START,
                COUNTERS_END,
                render_counters_markdown(
                    public_repos=public_repos,
                    original_count=original_count,
                    total_contrib=contributions["totalContributions"],
                    total_commits=contributions["totalCommitContributions"],
                    languages=languages,
                    last_pushed_label=last_pushed_label,
                ),
            )
            if updated != content:
                README.write_text(updated, encoding="utf-8")
                readme_changed = True

    DATA_DIR.mkdir(exist_ok=True)
    data_changed = write_data(
        stars, forks, public_repos, followers, distinct_langs, last_pushed_label
    )

    print(
        f"Telemetry synced: {public_repos} public repos ({original_count} original) · "
        f"{contributions['totalContributions']} contributions · {distinct_langs} languages · "
        f"svg {'updated' if svg_changed else 'unchanged'} · "
        f"readme {'updated' if readme_changed else 'unchanged'} · "
        f"data {'updated' if data_changed else 'unchanged'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
