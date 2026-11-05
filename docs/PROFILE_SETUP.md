# Profile README Operations & Design Guide

This repository (`salman-cc/salman-cc`) powers the public GitHub profile rendered at [github.com/salman-cc](https://github.com/salman-cc).

## Visual & Technical Architecture

The profile uses a minimalist, dark-surface engineering aesthetic (`#090C12` / `#101520`) accented with Signal Orange (`#FF6B35`), inspired by Linear, Vercel, and modern hardware-systems documentation. Every visual component is a crisp, repository-hosted SVG so the profile loads instantaneously without relying on rate-limited external widget servers.

```text
salman-cc/
├── README.md                        # Public GitHub profile document
├── assets/                          # Self-hosted vector design system (#FF6B35 accent)
│   ├── hero-banner.svg              # 880x312 hero banner + hardware-firmware schematic
│   ├── system-architecture.svg      # 880x236 4-layer silicon-to-autonomy diagram
│   ├── github-telemetry.svg         # 880x356 auto-generated stats, heatmap & languages
│   ├── section-divider.svg          # Precision hairline divider with orange node
│   └── link-*.svg                   # Minimalist dark action pills for verified links
├── data/                            # Generated Shields.io endpoint JSON payloads
│   └── repos.json, stars.json, forks.json, followers.json, languages.json, updated.json
├── .github/
│   └── scripts/
│       ├── profile_common.py        # Dependency-free GitHub REST + GraphQL client
│       ├── update_repos.py          # Generates assets/github-telemetry.svg + counters
│       ├── update_activity.py       # Refreshes recent public GitHub events block
│       ├── check_readme.py          # Structural, XML, link, and style validator
│       └── featured.json            # Curated flagship repository list
├── scripts/
│   └── enable-automation.sh         # Copies workflow templates into .github/workflows/
└── docs/
    ├── PROFILE_SETUP.md             # Maintenance and automation documentation
    └── workflow-templates/          # Scheduled GitHub Actions workflow templates
```

## Enabling Scheduled Automation

Because GitHub blocks automated apps from writing directly under `.github/workflows/`, workflows live in `docs/workflow-templates/`. Install them once from a local clone:

```bash
bash scripts/enable-automation.sh
git add .github/workflows
git commit -m "ci: enable profile telemetry workflows"
git push
```

Then configure **Settings -> Actions -> General -> Workflow permissions -> Read and write permissions**.

| Workflow | Schedule (UTC) | Purpose |
| :-- | :-- | :-- |
| `update-repos.yml` | Mondays `04:23` | Rebuilds `assets/github-telemetry.svg`, `<!-- COUNTERS -->`, and `data/*.json` |
| `update-activity.yml` | Daily `02:17` | Updates `<!-- ACTIVITY -->` from public GitHub events |
| `profile-checks.yml` | Push / PR to `main` | Validates markers, SVG XML, relative links, and generator idempotency |

## Local Validation

All scripts run on Python 3 standard library with zero external package dependencies:

```bash
python3 -m compileall -q .github/scripts
python3 .github/scripts/update_repos.py
python3 .github/scripts/update_activity.py
python3 .github/scripts/check_readme.py
git diff --check
```
