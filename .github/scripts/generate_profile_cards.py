from __future__ import annotations

import html
import json
import math
import os
import re
import urllib.request
from datetime import date, datetime, timedelta
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
    contribution_days, year_total = fetch_contribution_days(USERNAME, date(now.year, 1, 1), now.date())
    contribution_stats = compute_contribution_stats(contribution_days, now.date(), year_total)
    os.makedirs(DIST_DIR, exist_ok=True)

    hero_svg = generate_hero_svg(contribution_stats)
    snapshot_svg = generate_snapshot_svg(user, now)
    year_svg = generate_year_progress_svg(now)

    with open(os.path.join(DIST_DIR, "hero-banner.svg"), "w", encoding="utf-8") as file:
        file.write(hero_svg)
    with open(os.path.join(DIST_DIR, "profile-stable-card.svg"), "w", encoding="utf-8") as file:
        file.write(snapshot_svg)
    with open(os.path.join(DIST_DIR, "year-progress.svg"), "w", encoding="utf-8") as file:
        file.write(year_svg)

    print("Generated dist/hero-banner.svg, dist/profile-stable-card.svg and dist/year-progress.svg")


if __name__ == "__main__":
    main()
