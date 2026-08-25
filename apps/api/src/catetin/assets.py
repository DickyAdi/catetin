"""Filesystem locations of the shared CatetIn brand assets.

`packages/assets/` is the canonical home for the logos and the bundled font;
the copies under `apps/web/public/assets/` exist only so Vite can serve them
statically and are not what backend code should reach for.

This module lives inside the `catetin` package rather than in a `packages/`
workspace member on purpose: it exposes paths, not code, so there is nothing to
install and no uv workspace wiring to add. The PDF renderer (M4) will import
`ASSETS_DIR` to stamp the logo on reports — that wiring is not done yet.

Note for deployment: `apps/api/Dockerfile` copies `packages/` into the image so
these paths resolve at runtime too.
"""

from pathlib import Path

# This file is <repo>/apps/api/src/catetin/assets.py, so the repo root is four
# levels up: catetin -> src -> api -> apps -> <repo>.
REPO_ROOT: Path = Path(__file__).resolve().parents[4]

ASSETS_DIR: Path = REPO_ROOT / "packages" / "assets"
FONTS_DIR: Path = ASSETS_DIR / "fonts"

LOGO_LIGHT: Path = ASSETS_DIR / "1_CatetIn_Light_Logo_Transparent.svg"
APP_ICON_LIGHT: Path = ASSETS_DIR / "2_CatetIn_Light_App_Icon_Transparent.svg"
APP_ICON_DARK: Path = ASSETS_DIR / "3_CatetIn_Dark_App_Icon_Transparent.svg"
LOGO_MONOCHROME: Path = ASSETS_DIR / "4_CatetIn_Monochrome_Logo_Transparent.svg"
LOGO_DARK: Path = ASSETS_DIR / "5_CatetIn_Dark_Logo_Transparent.svg"

FAVICON_32: Path = ASSETS_DIR / "favicon-32x32.png"
APPLE_TOUCH_ICON: Path = ASSETS_DIR / "apple-touch-icon.png"

PLUS_JAKARTA_SANS_EXTRABOLD: Path = FONTS_DIR / "PlusJakartaSans-ExtraBold.woff2"

__all__ = [
    "APPLE_TOUCH_ICON",
    "APP_ICON_DARK",
    "APP_ICON_LIGHT",
    "ASSETS_DIR",
    "FAVICON_32",
    "FONTS_DIR",
    "LOGO_DARK",
    "LOGO_LIGHT",
    "LOGO_MONOCHROME",
    "PLUS_JAKARTA_SANS_EXTRABOLD",
    "REPO_ROOT",
]
