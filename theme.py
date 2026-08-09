"""
Cardwright design tokens.

One place for colour, spacing, radius and type so every window looks like the
same product. The palette is a low-chroma graphite ramp (calm and tool-like,
think Linear/Figma) with a single warm accent that keeps the app's identity.

Every foreground/background pair below was checked against WCAG:
    text/bg 15.7:1 · secondary 8.2:1 · muted 5.3:1 · accent 7.9:1
    on-accent/accent 8.4:1 · success 6.6:1 · warning 8.2:1 · danger 5.3:1
Borders are UI elements, not text: BORDER is decorative, BORDER_STRONG is for
input outlines and clears the 3:1 non-text threshold.
"""

# ---------------------------------------------------------------- surfaces
BG            = "#0E1116"   # window background
SURFACE       = "#151A21"   # panels, cards, side bars
SURFACE_ALT   = "#1C222B"   # rows, list items, inputs on panels
SURFACE_HOVER = "#232A34"   # hover / pressed on a surface
BORDER        = "#2A323D"   # hairlines between regions
BORDER_STRONG = "#626C7A"   # input outlines, focus-visible rings

# -------------------------------------------------------------------- text
TEXT          = "#E6EAF0"   # primary
TEXT_DIM      = "#A8B2C1"   # secondary / labels
TEXT_MUTED    = "#848E9D"   # hints, captions (still AA at 11px)

# ------------------------------------------------------------------ accent
ACCENT        = "#E0A33E"   # single accent: primary actions, active state
ACCENT_HOVER  = "#C98D2E"
ACCENT_QUIET  = "#3A2E17"   # accent-tinted fill for selected rows
ON_ACCENT     = "#17130A"   # text/icons drawn on the accent

# ---------------------------------------------------------------- semantic
SUCCESS       = "#3FB27F"
WARNING       = "#E5A54B"
DANGER        = "#E5645C"

# ------------------------------------------------------- neutral controls
CONTROL       = "#232A34"   # secondary buttons
CONTROL_HOVER = "#2E3743"

# ----------------------------------------------------------------- spacing
# 4pt rhythm, dense end of the scale - this is a tool, not a landing page.
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32}

# ------------------------------------------------------------------ radius
RADIUS_SM = 6     # inputs, small buttons
RADIUS_MD = 8     # cards, rows
RADIUS_LG = 12    # panels, dialogs

# -------------------------------------------------------------------- type
# Segoe UI Variable ships with Windows 11 and falls back cleanly on 10.
FONT = "Segoe UI Variable Text"
FONT_FALLBACK = "Segoe UI"

def font(size=13, weight="normal"):
    return (FONT, size, weight)

TYPE = {
    "display": 22,   # window title
    "title":   16,   # section / dialog heading
    "subtitle": 14,
    "body":    13,
    "small":   12,
    "caption": 11,
}

# ------------------------------------------------------------------ sizing
H_INPUT   = 34    # entries and option menus
H_BUTTON  = 34
H_BUTTON_LG = 40  # primary actions
