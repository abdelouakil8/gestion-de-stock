"""Design tokens — single source of truth for the hand-built QSS design system.

Placeholder values for now; the real palette and scale land with the first
visual design pass. Tokens get interpolated into app.qss at load time so the
stylesheet never contains hardcoded magic values.
"""

COLORS = {
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "background": "#F8FAFC",
    "surface": "#FFFFFF",
    "text": "#0F172A",
    "text_muted": "#64748B",
    "danger": "#DC2626",
    "success": "#16A34A",
    "warning": "#D97706",
    "border": "#E2E8F0",
}

# Pixel scale — old low-resolution screens are the baseline target.
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
FONT_SIZES = {"sm": 12, "base": 14, "lg": 16, "xl": 20, "title": 24}
RADIUS = {"sm": 4, "md": 6, "lg": 10}
