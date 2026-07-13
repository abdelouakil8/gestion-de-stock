"""Design tokens — single source of truth for the hand-built QSS design system.

app.qss contains `$token` placeholders; render_qss() substitutes them at load
time so the stylesheet never hardcodes magic values.

A THEME is three things, all stored per-store in Réglages:
  - mode   : "light" | "dark" — the base palette.
  - accent : the primary color (hover, subtle, focus ring… all derived here).
  - overrides : optional per-role structural colors (background / surface /
    text / border); NULL means "use the mode default".

Everything (the QSS tokens AND a complete QPalette) is derived from that one
theme, so the whole UI re-themes from one setting with no restart — and the OS
theme can never bleed through (that was the black-dialog bug).

The neutral scale is theme-aware: NEUTRAL["500"] returns a mid grey in light
mode and its inverted counterpart in dark mode, so hand-drawn charts and icon
colors adapt automatically without touching every call site.

Sized for old, low-resolution screens: compact spacing, readable 14px base
font, no effects that need a GPU.
"""

from collections.abc import Mapping
from pathlib import Path
from string import Template

# ------------------------------------------------------------------ color

# Neutral slate (light reference). In dark mode the ramp is inverted so that
# "900" (the darkest ink) becomes the lightest text, and "50" becomes the
# darkest surface — code keeps using the same keys and adapts to the mode.
_LIGHT_SLATE = {
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
_SLATE_KEYS = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900"]
_DARK_SLATE = {
    _SLATE_KEYS[i]: _LIGHT_SLATE[_SLATE_KEYS[len(_SLATE_KEYS) - 1 - i]]
    for i in range(len(_SLATE_KEYS))
}

# The active mode, updated by render_qss(); read by the NEUTRAL proxy so that
# every tokens.NEUTRAL["…"] lookup reflects the current theme.
CURRENT_MODE = "light"


class _Slate(Mapping):
    """Theme-aware neutral scale: light ramp or its inverted dark ramp."""

    def __getitem__(self, key: str) -> str:
        base = _DARK_SLATE if CURRENT_MODE == "dark" else _LIGHT_SLATE
        return base[key]

    def __iter__(self):
        return iter(_SLATE_KEYS)

    def __len__(self) -> int:
        return len(_SLATE_KEYS)


NEUTRAL = _Slate()

DEFAULT_ACCENT = "#2563EB"

# Semantic colors — meaning, not decoration. The base hues are fixed across
# modes (they read on both light and dark surfaces); the *subtle* and *text*
# variants are mode-aware: light tints/dark inks in light mode, dark tints/
# light inks in dark mode — otherwise badges and banners glare on dark.
_SEMANTIC_LIGHT = {
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
_SEMANTIC_DARK = {
    **_SEMANTIC_LIGHT,
    "success_subtle": "#173B26",
    "success_text": "#6EE7A0",
    "warning_subtle": "#3B2F14",
    "warning_text": "#FBBF24",
    "danger_subtle": "#3F1D1D",
    "danger_text": "#F87171",
}


class _Semantic(Mapping):
    """Theme-aware semantic scale — same keys, values follow CURRENT_MODE."""

    def __getitem__(self, key: str) -> str:
        base = _SEMANTIC_DARK if CURRENT_MODE == "dark" else _SEMANTIC_LIGHT
        return base[key]

    def __iter__(self):
        return iter(_SEMANTIC_LIGHT)

    def __len__(self) -> int:
        return len(_SEMANTIC_LIGHT)


SEMANTIC = _Semantic()

# Chrome that stays dark in BOTH modes (tooltips, toasts) and the receipt
# paper mock, which is always white paper with dark ink.
_CHROME = {
    "chrome_bg": "#1E293B",
    "chrome_border": "#475569",
    "paper_ink": "#1E293B",
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


def _wcag_luminance(color: str) -> float:
    """WCAG 2.x relative luminance (gamma-corrected sRGB)."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _hex_to_rgb(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(color_a: str, color_b: str) -> float:
    """WCAG contrast ratio between two colors (1..21)."""
    la, lb = _wcag_luminance(color_a), _wcag_luminance(color_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def readable_on(color: str) -> str:
    """White or slate text — whichever has the HIGHER real WCAG contrast.

    Safeguard for the owner-chosen accent (QColorDialog accepts anything):
    actual ratio comparison always yields the strongest available contrast."""
    white, slate = "#FFFFFF", _LIGHT_SLATE["900"]
    if contrast_ratio(color, white) >= contrast_ratio(color, slate):
        return white
    return slate


def is_valid_accent(color: str) -> bool:
    if not (isinstance(color, str) and len(color) == 7 and color.startswith("#")):
        return False
    try:
        _hex_to_rgb(color)
    except ValueError:
        return False
    return True


# --------------------------------------------------- structural roles

# Named structural roles per mode. The four overridable roles (background,
# surface, text, border) can be replaced by the owner in Réglages.
_LIGHT_SEMANTIC = {
    "background": "#F1F5F9",
    "surface": "#FFFFFF",
    "surface_sunken": "#F8FAFC",
    "text": "#0F172A",
    "text_secondary": "#475569",
    "text_muted": "#64748B",
    "text_disabled": "#94A3B8",
    "border": "#CBD5E1",
    "border_light": "#E2E8F0",
    "border_strong": "#94A3B8",
    "sidebar": "#0F172A",
    "sidebar_hover": "#1E293B",
    "row_alt": "#F8FAFC",
    "row_hover": "#F1F5F9",
}
_DARK_SEMANTIC = {
    "background": "#0F172A",
    "surface": "#1E293B",
    "surface_sunken": "#161F2E",
    "text": "#F1F5F9",
    "text_secondary": "#CBD5E1",
    "text_muted": "#94A3B8",
    "text_disabled": "#64748B",
    "border": "#334155",
    "border_light": "#273244",
    "border_strong": "#475569",
    "sidebar": "#0B1120",
    "sidebar_hover": "#1E293B",
    "row_alt": "#1B2536",
    "row_hover": "#24314B",
}
# Roles the owner may override; keys map 1:1 to the settings fields
# theme_{bg,surface,text,border}.
OVERRIDABLE_ROLES = ("background", "surface", "text", "border")


def accent_palette(accent: str, mode: str = "light") -> dict[str, str]:
    """Every accent-derived token, from one hex value + the mode.

    In dark mode the subtle tints blend toward the dark surface (not white)
    and hover states brighten instead of darkening, so accented controls read
    correctly on a dark background."""
    if not is_valid_accent(accent):
        accent = DEFAULT_ACCENT
    if mode == "dark":
        surface_ref = _DARK_SEMANTIC["surface"]
        return {
            "primary": accent,
            "primary_hover": lighten(accent, 0.12),
            "primary_pressed": lighten(accent, 0.24),
            "primary_subtle": mix(accent, surface_ref, 0.82),
            "primary_subtle_hover": mix(accent, surface_ref, 0.70),
            "primary_text_subtle": lighten(accent, 0.35),
            "on_primary": readable_on(accent),
            "focus_ring": lighten(accent, 0.15),
            "sidebar_active": accent,
            "selection_bg": mix(accent, surface_ref, 0.62),
        }
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

# Typography hierarchy — sizes with intended weights (weights are applied in
# QSS / widget code; listed here as the documented scale).
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

THUMB_SIZES = {"list": 44, "cart": 34, "table": 30, "preview": 96, "detail": 128}

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


# ----------------------------------------------------------- resolution

# The live theme, updated by render_qss(); widgets that paint by hand (charts)
# read CURRENT_ACCENT / CURRENT_SURFACE directly.
CURRENT_ACCENT = DEFAULT_ACCENT
CURRENT_OVERRIDES: dict[str, str] = {}
CURRENT_SURFACE = _LIGHT_SEMANTIC["surface"]


def semantic_defaults(mode: str) -> dict[str, str]:
    """The default structural role colors for a mode (no overrides).

    Used by Réglages to show the current color of a role when the owner has
    not overridden it."""
    return dict(_DARK_SEMANTIC if mode == "dark" else _LIGHT_SEMANTIC)


def _resolve_semantic(mode: str, overrides: dict[str, str]) -> dict[str, str]:
    """Structural roles for the mode, with valid overrides applied."""
    base = dict(_DARK_SEMANTIC if mode == "dark" else _LIGHT_SEMANTIC)
    for role in OVERRIDABLE_ROLES:
        value = (overrides or {}).get(role)
        if value and is_valid_accent(value):
            base[role] = value
    return base


def _flat_tokens(accent: str, mode: str, overrides: dict[str, str]) -> dict[str, str]:
    slate = _DARK_SLATE if mode == "dark" else _LIGHT_SLATE
    tokens: dict[str, str] = {}
    tokens.update(accent_palette(accent, mode))
    tokens.update(_SEMANTIC_DARK if mode == "dark" else _SEMANTIC_LIGHT)
    tokens.update({f"neutral_{k}": slate[k] for k in _SLATE_KEYS})
    tokens.update(_resolve_semantic(mode, overrides))
    tokens.update(_CHROME)
    tokens.update(
        {
            # Sidebar text stays light in both modes (the sidebar is always
            # dark), so it is not derived from the invertible neutral ramp.
            "text_on_dark": "#E2E8F0",
            "text_on_dark_muted": "#94A3B8",
        }
    )
    tokens.update({f"space_{k}": f"{v}px" for k, v in SPACING.items()})
    tokens.update({f"font_{k}": f"{v}px" for k, v in FONT_SIZES.items()})
    tokens.update({f"radius_{k}": f"{v}px" for k, v in RADIUS.items()})
    # QSS url() wants forward slashes, absolute.
    assets = (Path(__file__).resolve().parent / "assets").as_posix()
    tokens["assets"] = assets
    return tokens


def build_palette():
    """A complete QPalette derived from the current theme.

    Applying this to the QApplication makes the stylesheet the single source
    of truth on every machine: the OS light/dark palette can never show
    through a widget the QSS doesn't explicitly paint (the black-dialog bug)."""
    from PySide6.QtGui import QColor, QPalette

    semantic = _resolve_semantic(CURRENT_MODE, CURRENT_OVERRIDES)
    surface = QColor(semantic["surface"])
    background = QColor(semantic["background"])
    text = QColor(semantic["text"])
    sunken = QColor(semantic["surface_sunken"])
    muted = QColor(semantic["text_muted"])
    disabled = QColor(semantic["text_disabled"])
    accent_hex = CURRENT_ACCENT if is_valid_accent(CURRENT_ACCENT) else DEFAULT_ACCENT
    accent = QColor(accent_hex)
    on_accent = QColor(readable_on(accent_hex))
    white = QColor("#FFFFFF")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, surface)
    palette.setColor(QPalette.ColorRole.AlternateBase, sunken)
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(_CHROME["chrome_bg"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#E2E8F0"))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, surface)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, on_accent)
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.BrightText, white)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return palette


def render_qss(
    accent: str | None = None,
    mode: str | None = None,
    overrides: dict[str, str] | None = None,
) -> str:
    """Load app.qss and substitute every $token placeholder for the theme.

    Also updates the live-theme globals (CURRENT_MODE / CURRENT_ACCENT /
    CURRENT_OVERRIDES / CURRENT_SURFACE) so build_palette() and the hand-drawn
    widgets stay in sync. Invalid/missing values fall back to the defaults.
    """
    global CURRENT_ACCENT, CURRENT_MODE, CURRENT_OVERRIDES, CURRENT_SURFACE
    CURRENT_ACCENT = accent if accent and is_valid_accent(accent) else DEFAULT_ACCENT
    CURRENT_MODE = mode if mode in ("light", "dark") else "light"
    CURRENT_OVERRIDES = {
        role: value
        for role, value in (overrides or {}).items()
        if role in OVERRIDABLE_ROLES and value and is_valid_accent(value)
    }
    CURRENT_SURFACE = _resolve_semantic(CURRENT_MODE, CURRENT_OVERRIDES)["surface"]

    qss_path = Path(__file__).resolve().parent / "app.qss"
    template = Template(qss_path.read_text(encoding="utf-8"))
    return template.substitute(
        _flat_tokens(CURRENT_ACCENT, CURRENT_MODE, CURRENT_OVERRIDES)
    )
