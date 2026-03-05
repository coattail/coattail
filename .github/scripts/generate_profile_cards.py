from __future__ import annotations

import html
import json
import math
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


USERNAME = os.environ.get("GITHUB_USERNAME", "Sunny-1991")
TIMEZONE = os.environ.get("CARD_TIMEZONE", "Asia/Shanghai")
DIST_DIR = os.environ.get("DIST_DIR", "dist")


def esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fetch_user(login: str) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com/users/{login}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "sunny-profile-card-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_repositories(login: str) -> list[dict]:
    repos: list[dict] = []
    page = 1
    while True:
        req = urllib.request.Request(
            f"https://api.github.com/users/{login}/repos?per_page=100&page={page}&sort=pushed&type=owner",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "sunny-profile-card-generator",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            page_items = json.loads(response.read().decode("utf-8"))
        if not isinstance(page_items, list) or not page_items:
            break
        repos.extend(page_items)
        if len(page_items) < 100:
            break
        page += 1
    return repos


def parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def compact_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def shorten_text(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def summarize_portfolio(repos: list[dict], user: dict, now: datetime) -> dict:
    active_repos = [repo for repo in repos if not repo.get("fork")]
    if not active_repos:
        active_repos = repos

    total_stars = sum(int(repo.get("stargazers_count") or 0) for repo in active_repos)
    total_forks = sum(int(repo.get("forks_count") or 0) for repo in active_repos)
    open_issues = sum(int(repo.get("open_issues_count") or 0) for repo in active_repos)

    now_utc = now.astimezone(timezone.utc)
    active_30d = 0
    latest_push: datetime | None = None
    for repo in active_repos:
        pushed = parse_github_datetime(repo.get("pushed_at"))
        if pushed is None:
            continue
        if latest_push is None or pushed > latest_push:
            latest_push = pushed
        if (now_utc - pushed) <= timedelta(days=30):
            active_30d += 1

    top_repo = max(
        active_repos,
        key=lambda repo: (
            int(repo.get("stargazers_count") or 0),
            int(repo.get("forks_count") or 0),
            int(repo.get("size") or 0),
        ),
        default=None,
    )
    top_repo_name = str(top_repo.get("name") or "-") if top_repo else "-"
    top_repo_stars = int(top_repo.get("stargazers_count") or 0) if top_repo else 0

    language_weights: dict[str, int] = {}
    for repo in active_repos:
        language = repo.get("language")
        if not language:
            continue
        weight = int(repo.get("size") or 0)
        language_weights[str(language)] = language_weights.get(str(language), 0) + max(weight, 1)

    return {
        "public_repos": int(user.get("public_repos") or len(active_repos)),
        "total_stars": total_stars,
        "total_forks": total_forks,
        "open_issues": open_issues,
        "active_30d": active_30d,
        "latest_push_text": latest_push.astimezone(now.tzinfo).strftime("%Y-%m-%d")
        if latest_push
        else "N/A",
        "top_repo_name": top_repo_name,
        "top_repo_stars": top_repo_stars,
        "language_weights": language_weights,
    }


def fetch_contribution_days(
    login: str, start: date, end: date
) -> tuple[list[tuple[date, int]], int | None]:
    req = urllib.request.Request(
        f"https://github.com/users/{login}/contributions?from={start.isoformat()}&to={end.isoformat()}",
        headers={
            "Accept": "text/html",
            "User-Agent": "sunny-profile-card-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        body = response.read().decode("utf-8", errors="ignore")

    day_cells = re.findall(
        r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*id="([^"]+)"[^>]*data-level="(\d+)"[^>]*class="ContributionCalendar-day"',
        body,
    )
    if not day_cells:
        day_cells = [
            (date_text, cell_id, level_text)
            for cell_id, date_text, level_text in re.findall(
                r'id="([^"]+)"[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d+)"[^>]*class="ContributionCalendar-day"',
                body,
            )
        ]

    tooltip_count_by_id: dict[str, int] = {}
    tooltip_pairs = re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>(.*?)</tool-tip>', body, flags=re.DOTALL)
    for cell_id, tooltip_text in tooltip_pairs:
        plain_text = html.unescape(re.sub(r"<[^>]+>", " ", tooltip_text))
        plain_text = " ".join(plain_text.split())
        count_match = re.search(r"(\d+)\s+contributions?", plain_text)
        if count_match:
            tooltip_count_by_id[cell_id] = int(count_match.group(1))
            continue
        if "No contributions on" in plain_text:
            tooltip_count_by_id[cell_id] = 0

    day_count_map: dict[date, int] = {}
    for date_text, cell_id, level_text in day_cells:
        try:
            target_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue
        count = tooltip_count_by_id.get(cell_id)
        if count is None:
            count = 1 if int(level_text) > 0 else 0
        previous = day_count_map.get(target_date, 0)
        day_count_map[target_date] = max(previous, count)

    year_total: int | None = None
    summary_block_match = re.search(
        r'id="js-contribution-activity-description"[^>]*>(.*?)</h2>', body, flags=re.DOTALL
    )
    if summary_block_match:
        summary_text = html.unescape(re.sub(r"<[^>]+>", " ", summary_block_match.group(1)))
        summary_text = " ".join(summary_text.split())
        total_match = re.search(r"([0-9][0-9,]*)\s+contributions?", summary_text)
        if total_match:
            year_total = int(total_match.group(1).replace(",", ""))

    results = sorted(day_count_map.items(), key=lambda item: item[0])
    return results, year_total


def format_short_date(target: date) -> str:
    return f"{target.strftime('%b')} {target.day}"


def compute_contribution_stats(
    day_counts: list[tuple[date, int]], today: date, year_total_override: int | None = None
) -> dict[str, int | str | date | None]:
    count_map = {day: count for day, count in day_counts if day <= today}
    start_of_year = date(today.year, 1, 1)
    if year_total_override is None:
        year_total = sum(count for day, count in count_map.items() if start_of_year <= day <= today)
    else:
        year_total = year_total_override

    if count_map:
        start_day = min(count_map)
    else:
        start_day = start_of_year

    # Longest streak
    longest_len = 0
    longest_start: date | None = None
    longest_end: date | None = None
    run_len = 0
    run_start: date | None = None

    cursor = start_day
    while cursor <= today:
        value = count_map.get(cursor, 0)
        if value > 0:
            if run_len == 0:
                run_start = cursor
            run_len += 1
            if run_len > longest_len and run_start is not None:
                longest_len = run_len
                longest_start = run_start
                longest_end = cursor
        else:
            run_len = 0
            run_start = None
        cursor += timedelta(days=1)

    # Current streak (active until today)
    current_len = 0
    current_start: date | None = None
    cursor = today
    while cursor >= start_day and count_map.get(cursor, 0) > 0:
        current_len += 1
        current_start = cursor
        cursor -= timedelta(days=1)

    if current_len > 0 and current_start is not None:
        current_range = f"{format_short_date(current_start)} – Present"
    else:
        current_range = "No active streak"

    if longest_len > 0 and longest_start is not None and longest_end is not None:
        longest_range = f"{format_short_date(longest_start)} – {format_short_date(longest_end)}"
    else:
        longest_range = "No streak yet"

    return {
        "year_total": year_total,
        "current_streak": current_len,
        "current_range": current_range,
        "longest_streak": longest_len,
        "longest_range": longest_range,
    }


def is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def generate_snapshot_svg(user: dict, now: datetime) -> str:
    width = 900
    height = 300
    joined_at = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).astimezone(
        now.tzinfo
    )
    account_days = max((now.date() - joined_at.date()).days, 0)
    name = user.get("name") or user.get("login") or USERNAME
    repos = user.get("public_repos", 0)
    followers = user.get("followers", 0)
    following = user.get("following", 0)
    updated_text = now.strftime("%Y-%m-%d %H:%M")

    items = [
        ("Public Repos", repos),
        ("Followers", followers),
        ("Following", following),
        ("Account Days", account_days),
    ]

    card_x = [40, 250, 460, 670]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#0b1021"/><stop offset="100%" stop-color="#121b3a"/></linearGradient></defs>',
        '<rect x="0" y="0" width="900" height="300" rx="18" fill="url(#bg)"/>',
        f'<text x="42" y="54" fill="#8ab4ff" font-size="24" font-family="Segoe UI,Arial,sans-serif" font-weight="700">{esc(name)} · Daily Snapshot</text>',
        f'<text x="42" y="84" fill="#8b95b2" font-size="14" font-family="Segoe UI,Arial,sans-serif">Updated {esc(updated_text)} ({esc(TIMEZONE)})</text>',
    ]

    for index, (label, value) in enumerate(items):
        x = card_x[index]
        parts.extend(
            [
                f'<rect x="{x}" y="110" width="190" height="130" rx="14" fill="#0f1730" stroke="#243057"/>',
                f'<text x="{x + 18}" y="154" fill="#7ae7ff" font-size="34" font-family="Segoe UI,Arial,sans-serif" font-weight="800">{esc(value)}</text>',
                f'<text x="{x + 18}" y="194" fill="#9ea8c3" font-size="16" font-family="Segoe UI,Arial,sans-serif">{esc(label)}</text>',
            ]
        )

    parts.append("</svg>")
    return "".join(parts)


def generate_hero_svg(stats: dict[str, int | str | date | None]) -> str:
    width = 900
    height = 320
    current_streak = int(stats["current_streak"])
    longest_streak = int(stats["longest_streak"])
    year_total = int(stats["year_total"])
    current_range = str(stats["current_range"])
    longest_range = str(stats["longest_range"])

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><linearGradient id="hero-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#171c33"/><stop offset="100%" stop-color="#12162b"/></linearGradient><radialGradient id="ring-glow" cx="0.5" cy="0.38" r="0.45"><stop offset="0%" stop-color="#6ea6ff" stop-opacity="0.12"/><stop offset="100%" stop-color="#6ea6ff" stop-opacity="0"/></radialGradient></defs>',
        '<rect x="0" y="0" width="900" height="320" rx="18" fill="url(#hero-bg)"/>',
        '<rect x="300" y="38" width="2.2" height="244" rx="1" fill="#d8dbe5" fill-opacity="0.75"/>',
        '<rect x="600" y="38" width="2.2" height="244" rx="1" fill="#d8dbe5" fill-opacity="0.75"/>',
        '<circle cx="450" cy="118" r="78" fill="url(#ring-glow)"/>',
        '<path fill="#6ea6ff" fill-rule="evenodd" d="M450 20C438 30 431 42 431 56C431 75 446 90 464 90C483 90 499 76 499 56C499 44 494 33 483 25C484 35 479 45 470 50C467 40 460 31 450 20ZM471 51C473 58 470 66 463 69C456 65 454 57 458 51C461 47 462 43 462 38C467 41 469 46 471 51Z"/>',
        f'<text x="150" y="120" fill="#6ea6ff" font-size="70" font-family="Segoe UI,Arial,sans-serif" font-weight="700" text-anchor="middle">{year_total}</text>',
        '<text x="150" y="182" fill="#6ea6ff" font-size="30" font-family="Segoe UI,Arial,sans-serif" font-weight="500" text-anchor="middle">Total Contributions</text>',
        f'<text x="150" y="238" fill="#3bcacb" font-size="28" font-family="Segoe UI,Arial,sans-serif" text-anchor="middle">{esc(current_range if current_streak > 0 else "This year")}</text>',
        '<circle cx="450" cy="112" r="73" fill="none" stroke="#6ea6ff" stroke-width="11"/>',
        f'<text x="450" y="135" fill="#b593ff" font-size="74" font-family="Segoe UI,Arial,sans-serif" font-weight="700" text-anchor="middle">{current_streak}</text>',
        '<text x="450" y="222" fill="#b593ff" font-size="30" font-family="Segoe UI,Arial,sans-serif" font-weight="600" text-anchor="middle">Current Streak</text>',
        f'<text x="450" y="270" fill="#3bcacb" font-size="28" font-family="Segoe UI,Arial,sans-serif" text-anchor="middle">{esc(current_range)}</text>',
        f'<text x="750" y="120" fill="#6ea6ff" font-size="70" font-family="Segoe UI,Arial,sans-serif" font-weight="700" text-anchor="middle">{longest_streak}</text>',
        '<text x="750" y="182" fill="#6ea6ff" font-size="30" font-family="Segoe UI,Arial,sans-serif" font-weight="500" text-anchor="middle">Longest Streak</text>',
        f'<text x="750" y="238" fill="#3bcacb" font-size="28" font-family="Segoe UI,Arial,sans-serif" text-anchor="middle">{esc(longest_range)}</text>',
        "</svg>",
    ]
    return "".join(parts)


def polar_to_cartesian(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    theta = math.radians(angle - 90)
    return cx + radius * math.cos(theta), cy + radius * math.sin(theta)


def donut_segment_path(
    cx: float, cy: float, inner_radius: float, outer_radius: float, start_angle: float, end_angle: float
) -> str:
    outer_start = polar_to_cartesian(cx, cy, outer_radius, start_angle)
    outer_end = polar_to_cartesian(cx, cy, outer_radius, end_angle)
    inner_end = polar_to_cartesian(cx, cy, inner_radius, end_angle)
    inner_start = polar_to_cartesian(cx, cy, inner_radius, start_angle)
    large_arc = 1 if (end_angle - start_angle) > 180 else 0
    return (
        f"M {outer_start[0]:.3f} {outer_start[1]:.3f} "
        f"A {outer_radius:.3f} {outer_radius:.3f} 0 {large_arc} 1 {outer_end[0]:.3f} {outer_end[1]:.3f} "
        f"L {inner_end[0]:.3f} {inner_end[1]:.3f} "
        f"A {inner_radius:.3f} {inner_radius:.3f} 0 {large_arc} 0 {inner_start[0]:.3f} {inner_start[1]:.3f} Z"
    )


def generate_portfolio_overview_svg(stats: dict, now: datetime) -> str:
    width = 900
    height = 300
    top_repo_name = shorten_text(str(stats["top_repo_name"]), 24)
    top_repo_stars = compact_number(int(stats["top_repo_stars"]))
    latest_push_text = str(stats["latest_push_text"])
    updated_text = now.strftime("%Y-%m-%d %H:%M")

    metrics = [
        ("Public Repos", compact_number(int(stats["public_repos"]))),
        ("Total Stars", compact_number(int(stats["total_stars"]))),
        ("Total Forks", compact_number(int(stats["total_forks"]))),
        ("Active Repos (30d)", compact_number(int(stats["active_30d"]))),
    ]
    card_x = [40, 250, 460, 670]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><linearGradient id="portfolioBg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#0b1228"/><stop offset="100%" stop-color="#111f45"/></linearGradient></defs>',
        '<rect x="0" y="0" width="900" height="300" rx="18" fill="url(#portfolioBg)"/>',
        '<text x="42" y="54" fill="#8ec5ff" font-size="25" font-family="Segoe UI,Arial,sans-serif" font-weight="700">Portfolio Highlights</text>',
        f'<text x="42" y="82" fill="#93a0be" font-size="14" font-family="Segoe UI,Arial,sans-serif">Updated {esc(updated_text)} ({esc(TIMEZONE)})</text>',
    ]

    for index, (label, value) in enumerate(metrics):
        x = card_x[index]
        parts.extend(
            [
                f'<rect x="{x}" y="104" width="190" height="122" rx="14" fill="#0e1a38" stroke="#264179"/>',
                f'<text x="{x + 18}" y="150" fill="#77ddff" font-size="36" font-family="Segoe UI,Arial,sans-serif" font-weight="800">{esc(value)}</text>',
                f'<text x="{x + 18}" y="190" fill="#a6b2cf" font-size="16" font-family="Segoe UI,Arial,sans-serif">{esc(label)}</text>',
            ]
        )

    parts.extend(
        [
            '<rect x="40" y="242" width="820" height="34" rx="10" fill="#0e1a38" stroke="#264179"/>',
            f'<text x="58" y="266" fill="#8ec5ff" font-size="15" font-family="Segoe UI,Arial,sans-serif">Top Repo: {esc(top_repo_name)} ★{esc(top_repo_stars)} · Last Push: {esc(latest_push_text)}</text>',
        ]
    )

    parts.append("</svg>")
    return "".join(parts)


def generate_language_mix_svg(stats: dict) -> str:
    width = 900
    height = 320
    raw_weights = dict(stats.get("language_weights") or {})

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><linearGradient id="langBg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#080f20"/><stop offset="100%" stop-color="#111c3a"/></linearGradient></defs>',
        '<rect x="0" y="0" width="900" height="320" rx="18" fill="url(#langBg)"/>',
        '<text x="42" y="56" fill="#8ec5ff" font-size="25" font-family="Segoe UI,Arial,sans-serif" font-weight="700">Top Languages</text>',
        '<text x="42" y="84" fill="#93a0be" font-size="14" font-family="Segoe UI,Arial,sans-serif">By public repository size</text>',
    ]

    if not raw_weights:
        parts.extend(
            [
                '<circle cx="250" cy="178" r="96" fill="none" stroke="#28426d" stroke-width="24"/>',
                '<text x="250" y="172" fill="#8ec5ff" font-size="26" font-family="Segoe UI,Arial,sans-serif" font-weight="700" text-anchor="middle">No Language Data</text>',
                '<text x="250" y="204" fill="#93a0be" font-size="16" font-family="Segoe UI,Arial,sans-serif" text-anchor="middle">Push code to see language mix</text>',
            ]
        )
        parts.append("</svg>")
        return "".join(parts)

    ordered = sorted(raw_weights.items(), key=lambda item: item[1], reverse=True)
    if len(ordered) > 6:
        merged_other = sum(weight for _, weight in ordered[5:])
        ordered = ordered[:5] + [("Other", merged_other)]

    total_weight = max(sum(weight for _, weight in ordered), 1)
    palette = ["#6ea6ff", "#b593ff", "#3bcacb", "#ff9f68", "#a7ff5c", "#f6d365", "#ff7aa2"]

    cx = 250
    cy = 180
    inner_radius = 68
    outer_radius = 106
    start_angle = -90.0

    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{(inner_radius + outer_radius) / 2:.1f}" fill="none" stroke="#1f355d" stroke-width="{outer_radius - inner_radius:.1f}"/>')

    legend_y = 108
    for index, (language, weight) in enumerate(ordered):
        percent = (weight / total_weight) * 100
        sweep = max((weight / total_weight) * 360, 3)
        end_angle = start_angle + sweep
        color = palette[index % len(palette)]
        path_data = donut_segment_path(cx, cy, inner_radius, outer_radius, start_angle, end_angle)
        parts.append(f'<path d="{path_data}" fill="{color}"/>')

        y = legend_y + index * 34
        parts.extend(
            [
                f'<rect x="470" y="{y - 14}" width="16" height="16" rx="4" fill="{color}"/>',
                f'<text x="496" y="{y}" fill="#d6e4ff" font-size="20" font-family="Segoe UI,Arial,sans-serif">{esc(language)}</text>',
                f'<text x="852" y="{y}" fill="#7ce6ff" font-size="20" font-family="Segoe UI,Arial,sans-serif" text-anchor="end">{percent:.1f}%</text>',
            ]
        )
        start_angle = end_angle

    parts.extend(
        [
            '<text x="250" y="170" fill="#d6e4ff" font-size="22" font-family="Segoe UI,Arial,sans-serif" font-weight="700" text-anchor="middle">Language Mix</text>',
            f'<text x="250" y="198" fill="#93a0be" font-size="16" font-family="Segoe UI,Arial,sans-serif" text-anchor="middle">{len(raw_weights)} languages</text>',
        ]
    )

    parts.append("</svg>")
    return "".join(parts)


def generate_year_progress_svg(now: datetime) -> str:
    year = now.year
    days_total = 366 if is_leap_year(year) else 365
    day_of_year = now.timetuple().tm_yday
    days_left = days_total - day_of_year
    percent = (day_of_year / days_total) * 100

    cols = 31
    rows = math.ceil(days_total / cols)
    dot_radius = 6
    gap_x = 25
    gap_y = 25
    start_x = 62
    start_y = 120
    width = 900
    height = 420

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect x="0" y="0" width="900" height="420" rx="18" fill="#060b12"/>',
        f'<text x="54" y="60" fill="#ffffff" font-size="48" font-family="Segoe UI,Arial,sans-serif" font-weight="800">{year}</text>',
        f'<text x="410" y="60" fill="#ff4f4f" font-size="56" font-family="Segoe UI,Arial,sans-serif" font-weight="800" text-anchor="middle">{percent:.0f}%</text>',
        f'<text x="840" y="60" fill="#a7ff5c" font-size="48" font-family="Segoe UI,Arial,sans-serif" font-weight="800" text-anchor="end">{day_of_year}/{days_total}</text>',
        f'<text x="840" y="94" fill="#8b95b2" font-size="20" font-family="Segoe UI,Arial,sans-serif" text-anchor="end">Days left: {days_left}</text>',
    ]

    for index in range(days_total):
        row = index // cols
        col = index % cols
        cx = start_x + col * gap_x
        cy = start_y + row * gap_y
        is_done = index < day_of_year
        is_today = index == day_of_year - 1
        fill = "#66f2ef" if is_done else "#18464b"
        radius = dot_radius + 0.8 if is_today else dot_radius
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}"/>')

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    user = fetch_user(USERNAME)
    repos = fetch_repositories(USERNAME)
    portfolio_stats = summarize_portfolio(repos, user, now)
    contribution_days, year_total = fetch_contribution_days(USERNAME, date(now.year, 1, 1), now.date())
    contribution_stats = compute_contribution_stats(contribution_days, now.date(), year_total)
    os.makedirs(DIST_DIR, exist_ok=True)

    hero_svg = generate_hero_svg(contribution_stats)
    portfolio_svg = generate_portfolio_overview_svg(portfolio_stats, now)
    languages_svg = generate_language_mix_svg(portfolio_stats)
    snapshot_svg = generate_snapshot_svg(user, now)
    year_svg = generate_year_progress_svg(now)

    with open(os.path.join(DIST_DIR, "hero-banner.svg"), "w", encoding="utf-8") as file:
        file.write(hero_svg)
    with open(os.path.join(DIST_DIR, "portfolio-overview.svg"), "w", encoding="utf-8") as file:
        file.write(portfolio_svg)
    with open(os.path.join(DIST_DIR, "languages-mix.svg"), "w", encoding="utf-8") as file:
        file.write(languages_svg)
    with open(os.path.join(DIST_DIR, "profile-stable-card.svg"), "w", encoding="utf-8") as file:
        file.write(snapshot_svg)
    with open(os.path.join(DIST_DIR, "year-progress.svg"), "w", encoding="utf-8") as file:
        file.write(year_svg)

    print(
        "Generated dist/hero-banner.svg, dist/portfolio-overview.svg, dist/languages-mix.svg, "
        "dist/profile-stable-card.svg and dist/year-progress.svg"
    )


if __name__ == "__main__":
    main()
