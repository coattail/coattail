from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime
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
    os.makedirs(DIST_DIR, exist_ok=True)

    snapshot_svg = generate_snapshot_svg(user, now)
    year_svg = generate_year_progress_svg(now)

    with open(os.path.join(DIST_DIR, "profile-stable-card.svg"), "w", encoding="utf-8") as file:
        file.write(snapshot_svg)
    with open(os.path.join(DIST_DIR, "year-progress.svg"), "w", encoding="utf-8") as file:
        file.write(year_svg)

    print("Generated dist/profile-stable-card.svg and dist/year-progress.svg")


if __name__ == "__main__":
    main()
