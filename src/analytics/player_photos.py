"""Player portrait helpers — SVG avatars with Orange/Purple Cap styling."""

from __future__ import annotations

import base64
import hashlib
import re
from html import escape


ORANGE = "#e87a12"
PURPLE = "#6b3fa0"
ORANGE_BG = "#fff4e8"
PURPLE_BG = "#f3ecfb"


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _tone(name: str, accent: str) -> str:
    """Deterministic secondary tone from player name."""
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()
    # blend toward accent family
    if accent == "orange":
        palette = ["#c45c0a", "#d9782d", "#b45309", "#ea580c", "#9a3412"]
    else:
        palette = ["#5b21b6", "#6b3fa0", "#7c3aed", "#4c1d95", "#6d28d9"]
    return palette[int(digest[:2], 16) % len(palette)]


def avatar_svg(name: str, accent: str = "orange", size: int = 160) -> str:
    """Return inline SVG portrait with a cap badge."""
    initials = escape(_initials(name))
    cap = ORANGE if accent == "orange" else PURPLE
    face = _tone(name, accent)
    # simple portrait + cap shape
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 160 160">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{face}"/>
      <stop offset="100%" stop-color="#1f2937"/>
    </linearGradient>
  </defs>
  <rect width="160" height="160" rx="18" fill="url(#g)"/>
  <circle cx="80" cy="78" r="36" fill="#f8fafc" opacity="0.92"/>
  <text x="80" y="88" text-anchor="middle" font-family="Arial, sans-serif"
        font-size="28" font-weight="700" fill="#111827">{initials}</text>
  <!-- cap brim -->
  <ellipse cx="80" cy="48" rx="42" ry="10" fill="{cap}"/>
  <!-- cap crown -->
  <path d="M48 48 C48 28, 112 28, 112 48 L112 54 C112 54, 48 54, 48 54 Z" fill="{cap}"/>
  <rect x="70" y="34" width="20" height="8" rx="2" fill="#111827" opacity="0.25"/>
</svg>"""


def avatar_data_uri(name: str, accent: str = "orange") -> str:
    svg = avatar_svg(name, accent=accent)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def cap_card_html(
    *,
    season: int,
    player_name: str,
    accent: str,
    metric_label: str,
    metric_value,
    secondary: str = "",
) -> str:
    """HTML card for Orange/Purple Cap winner with portrait."""
    bg = ORANGE_BG if accent == "orange" else PURPLE_BG
    border = ORANGE if accent == "orange" else PURPLE
    title = "Orange Cap" if accent == "orange" else "Purple Cap"
    img = avatar_data_uri(player_name, accent=accent)
    sec = f"<div style='opacity:.75;font-size:.85rem;margin-top:.2rem'>{escape(secondary)}</div>" if secondary else ""
    return f"""
    <div style="
      background:{bg};
      border-left:6px solid {border};
      border-radius:10px;
      padding:14px 14px 16px;
      height:100%;
      box-sizing:border-box;
      font-family:'Source Sans 3', sans-serif;
      color:#10241c;
    ">
      <div style="font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;opacity:.7">{season} · {title}</div>
      <div style="display:flex;gap:12px;align-items:center;margin-top:10px">
        <img src="{img}" alt="{escape(player_name)}" width="72" height="72"
             style="border-radius:14px;border:2px solid {border};background:#fff"/>
        <div>
          <div style="font-family:'Bebas Neue', sans-serif;font-size:1.45rem;line-height:1.05;color:#10241c">
            {escape(player_name)}
          </div>
          <div style="margin-top:.35rem;font-weight:700;color:{border}">
            {escape(str(metric_label))}: {escape(str(metric_value))}
          </div>
          {sec}
        </div>
      </div>
    </div>
    """


def render_cap_gallery(rows: list[dict], accent: str, cols: int = 3) -> str:
    """Grid of cap cards from dict rows with season/player/metric fields."""
    cards = []
    for r in rows:
        cards.append(
            cap_card_html(
                season=int(r["season"]),
                player_name=str(r["player_name"]),
                accent=accent,
                metric_label=str(r["metric_label"]),
                metric_value=r["metric_value"],
                secondary=str(r.get("secondary") or ""),
            )
        )
    if not cards:
        return "<p>No cap winners found.</p>"
    # CSS grid
    return f"""
    <div style="display:grid;grid-template-columns:repeat({cols},minmax(0,1fr));gap:12px">
      {''.join(cards)}
    </div>
    """
