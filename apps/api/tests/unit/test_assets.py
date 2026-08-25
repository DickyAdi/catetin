"""The shared-asset paths are only useful if they actually resolve.

`ASSETS_DIR` is derived by walking up from `__file__`, so a move of this package
inside the monorepo would silently point it at the wrong directory. These tests
fail loudly if that happens.
"""

from catetin import assets


def test_repo_root_is_the_workspace_root() -> None:
    assert (assets.REPO_ROOT / "pyproject.toml").is_file()
    assert (assets.REPO_ROOT / "uv.lock").is_file()
    assert (assets.REPO_ROOT / "apps" / "api").is_dir()


def test_assets_dir_exists() -> None:
    assert assets.ASSETS_DIR.is_dir()
    assert assets.ASSETS_DIR == assets.REPO_ROOT / "packages" / "assets"


def test_all_five_brand_svgs_are_present() -> None:
    svgs = [
        assets.LOGO_LIGHT,
        assets.APP_ICON_LIGHT,
        assets.APP_ICON_DARK,
        assets.LOGO_MONOCHROME,
        assets.LOGO_DARK,
    ]
    missing = [path.name for path in svgs if not path.is_file()]
    assert not missing, f"missing brand SVGs: {missing}"

    assert sorted(p.name for p in assets.ASSETS_DIR.glob("*.svg")) == sorted(
        p.name for p in svgs
    )


def test_fonts_dir_holds_the_bundled_font() -> None:
    assert assets.FONTS_DIR.is_dir()
    assert assets.PLUS_JAKARTA_SANS_EXTRABOLD.is_file()


def test_favicons_are_present() -> None:
    assert assets.FAVICON_32.is_file()
    assert assets.APPLE_TOUCH_ICON.is_file()
