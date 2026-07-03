"""Design tokens — single source of truth for the hand-built QSS design system.

app.qss contains `$token` placeholders; render_qss() substitutes them at
load time so the stylesheet never hardcodes magic values.

The accent (primary) color is DYNAMIC: it comes from the store's
theme_accent setting at startup (and live when changed in Réglages).
Every accent variant (hover, pressed, subtle background, focus ring) is
derived here from that single hex value, so the whole UI re-themes from
one setting.

Sized for old, low-resolution screens: compact spacing, readable 14px
base font, no effects that need a GPU.
"""

from pathlib import Path
from string import Template

# ------------------------------------------------------------------ color

# Neutral scale (slate) — chrome, text, borders. Fixed, never themed.
NEUTRAL = {
    "50": "#F8FAFC",
    "100": "#F1F5F9",
    "200": "#E2E8F0",
    "300": "#CBD5E1",
    "400": "#94A3B8",
    "500": "#64748B",
    "600": "#475569",
    "700": "#334155",
    "800": "#1E293B",
    "900": "#0F172A",
}

DEFAULT_ACCENT = "#2563EB"

# Semantic colors — meaning, not decoration. Each has hover + subtle
# (tinted background for badges/rows) variants.
SEMANTIC = {
    "success": "#16A34A",
    "success_hover": "#15803D",
    "success_subtle": "#DCFCE7",
    "success_text": "#166534",
    "warning": "#D97706",
    "warning_hover": "#B45309",
    "warning_subtle": "#FEF3C7",
    "warning_text": "#92400E",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    "danger_pressed": "#991B1B",
    "danger_subtle": "#FEE2E2",
    "danger_text": "#991B1B",
}


def _clamp(value: float) -> int:
    return max(0, min(255, round(value)))


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(color: str, other: str, amount: float) -> str:
    """Blend `color` toward `other` by amount in [0, 1]."""
    r1, g1, b1 = _hex_to_rgb(color)
    r2, g2, b2 = _hex_to_rgb(other)
    return _rgb_to_hex(
        _clamp(r1 + (r2 - r1) * amount),
        _clamp(g1 + (g2 - g1) * amount),
        _clamp(b1 + (b2 - b1) * amount),
    )


def darken(color: str, amount: float) -> str:
    return mix(color, "#000000", amount)


def lighten(color: str, amount: float) -> str:
    return mix(color, "#FFFFFF", amount)


def readable_on(color: str) -> str:
    """Black or white text, whichever reads better on `color` (WCAG-ish)."""
    r, g, b = _hex_to_rgb(color)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#0F172A" if luminance > 0.62 else "#FFFFFF"


def is_valid_accent(color: str) -> bool:
    if not (isinstance(color, str) and len(color) == 7 and color.startswith("#")):
        return False
    try:
        _hex_to_rgb(color)
    except ValueError:
        return False
    return True


def accent_palette(accent: str) -> dict[str, str]:
    """Every accent-derived token, from one hex value."""
    if not is_valid_accent(accent):
        accent = DEFAULT_ACCENT
    return {
        "primary": accent,
        "primary_hover": darken(accent, 0.12),
        "primary_pressed": darken(accent, 0.24),
        "primary_subtle": lighten(accent, 0.88),
        "primary_subtle_hover": lighten(accent, 0.80),
        "primary_text_subtle": darken(accent, 0.30),
        "on_primary": readable_on(accent),
        "focus_ring": accent,
        "sidebar_active": accent,
        "selection_bg": lighten(accent, 0.82),
    }


# ------------------------------------------------------------ scales

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}

# Typography hierarchy — sizes with intended weights (weights are applied
# in QSS / widget code; listed here as the documented scale).
FONT_SIZES = {
    "caption": 11,  # weight 500 — table headers, hints, badges
    "sm": 12,  # weight 400 — secondary text
    "base": 14,  # weight 400 — body
    "md": 16,  # weight 600 — emphasized rows, nav
    "lg": 18,  # weight 600 — section titles
    "title": 22,  # weight 700 — screen titles
    "display": 28,  # weight 800 — big money amounts
}

RADIUS = {"sm": 4, "md": 6, "lg": 10, "pill": 999}

ICON_SIZES = {"sm": 14, "md": 18, "lg": 22}

THUMB_SIZES = {"list": 28, "cart": 34, "table": 30, "preview": 96, "detail": 128}

# Preset accent swatches offered in Réglages (any hex is accepted too).
ACCENT_PRESETS = [
    "#2563EB",  # bleu
    "#0D9488",  # sarcelle
    "#16A34A",  # vert
    "#D97706",  # ambre
    "#DC2626",  # rouge
    "#7C3AED",  # violet
    "#DB2777",  # rose
    "#0F172A",  # ardoise
]


def _flat_tokens(accent: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    tokens.update(accent_palette(accent))
    tokens.update(SEMANTIC)
    tokens.update({f"neutral_{k}": v for k, v in NEUTRAL.items()})
    tokens.update(
        {
            # Semantic aliases used throughout the QSS.
            "background": NEUTRAL["100"],
            "surface": "#FFFFFF",
            "surface_sunken": NEUTRAL["50"],
            "text": NEUTRAL["900"],
            "text_secondary": NEUTRAL["600"],
            "text_muted": NEUTRAL["500"],
            "text_disabled": NEUTRAL["400"],
            "text_on_dark": NEUTRAL["200"],
            "text_on_dark_muted": NEUTRAL["400"],
            "border": NEUTRAL["300"],
            "border_light": NEUTRAL["200"],
            "border_strong": NEUTRAL["400"],
            "sidebar": NEUTRAL["900"],
            "sidebar_hover": NEUTRAL["800"],
            "row_alt": NEUTRAL["50"],
            "row_hover": NEUTRAL["100"],
        }
    )
    tokens.update({f"space_{k}": f"{v}px" for k, v in SPACING.items()})
    tokens.update({f"font_{k}": f"{v}px" for k, v in FONT_SIZES.items()})
    tokens.update({f"radius_{k}": f"{v}px" for k, v in RADIUS.items()})
    # QSS url() wants forward slashes, absolute.
    assets = (Path(__file__).resolve().parent / "assets").as_posix()
    tokens["assets"] = assets
    return tokens


CURRENT_ACCENT = DEFAULT_ACCENT  # updated by render_qss(); widgets may read it


def render_qss(accent: str | None = None) -> str:
    """Load app.qss and substitute every $token placeholder.

    `accent` comes from the store settings (theme_accent); invalid or
    missing values fall back to the default blue.
    """
    global CURRENT_ACCENT
    CURRENT_ACCENT = accent if accent and is_valid_accent(accent) else DEFAULT_ACCENT
    qss_path = Path(__file__).resolve().parent / "app.qss"
    template = Template(qss_path.read_text(encoding="utf-8"))
    return template.substitute(_flat_tokens(CURRENT_ACCENT))
