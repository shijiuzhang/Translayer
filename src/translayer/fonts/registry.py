from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_FONT_EXTENSIONS = ("*.ttf", "*.ttc", "*.otf")
_SEARCH_ROOTS = (
    Path("/usr/share/fonts"),
    Path.home() / ".fonts",
    Path.home() / ".local/share/fonts",
    Path("C:/Windows/Fonts"),
    Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
)

# Confirmed on the milestone environment via fc-list: Noto Sans CJK SC lives here.
_PRIMARY_CJK_CANDIDATES = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simsun.ttc"),
    Path("C:/Windows/Fonts/Deng.ttf"),
)
_PRIMARY_LATIN_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
)
_CJK_LANG_PREFIXES = ("zh", "ja", "ko")


class FontRegistry:
    """Find and load real font files for rendered in-image translations."""

    def font_for_lang(self, lang: str) -> str:
        lang_key = (lang or "").casefold()
        if lang_key.startswith(_CJK_LANG_PREFIXES):
            return str(self._first_existing(_PRIMARY_CJK_CANDIDATES) or self._discover_cjk_font() or self._fallback_font())
        if lang_key.startswith(("en", "de")):
            return str(self._first_existing(_PRIMARY_LATIN_CANDIDATES) or self._discover_latin_font() or self._fallback_font())
        return str(self._discover_latin_font() or self._discover_cjk_font() or self._fallback_font())

    def load(self, lang: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self.font_for_lang(lang), size=max(1, int(size)))

    @staticmethod
    def _first_existing(paths: tuple[Path, ...]) -> Path | None:
        return next((path for path in paths if path.exists()), None)

    def _discover_cjk_font(self) -> Path | None:
        candidates = self._font_files()
        preferred_names = (
            "notosanscjksc",
            "noto sans cjk sc",
            "notosanscjk",
            "noto sans cjk",
            "msyh",
            "microsoft yahei",
            "simsun",
            "nsimsun",
            "deng",
            "wqy",
            "wenquanyi",
        )
        return self._first_name_match(candidates, preferred_names)

    def _discover_latin_font(self) -> Path | None:
        candidates = self._font_files()
        preferred_names = (
            "dejavusans.ttf",
            "dejavu sans",
            "dejavusans",
            "arial.ttf",
            "segoeui.ttf",
        )
        return self._first_name_match(candidates, preferred_names)

    @staticmethod
    def _first_name_match(candidates: tuple[Path, ...], names: tuple[str, ...]) -> Path | None:
        for name in names:
            needle = name.casefold()
            for path in candidates:
                haystack = f"{path.name} {path}".casefold()
                if needle in haystack and path.exists():
                    return path
        return None

    @staticmethod
    @lru_cache(maxsize=1)
    def _font_files() -> tuple[Path, ...]:
        fonts: list[Path] = []
        for root in _SEARCH_ROOTS:
            if not root.exists():
                continue
            for extension in _FONT_EXTENSIONS:
                fonts.extend(path for path in root.glob(f"**/{extension}") if path.is_file())
        return tuple(sorted(set(fonts)))

    @staticmethod
    @lru_cache(maxsize=1)
    def _fallback_font() -> Path:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", size=12)
            path = Path(str(font.path))
            if path.exists():
                return path
        except OSError:
            pass

        pil_dir = Path(ImageFont.__file__).resolve().parent
        for candidate in (
            pil_dir / "fonts" / "DejaVuSans.ttf",
            pil_dir / "DejaVuSans.ttf",
        ):
            if candidate.exists():
                return candidate

        discovered = FontRegistry._first_name_match(FontRegistry._font_files(), ("dejavusans",))
        if discovered is not None:
            return discovered
        raise FileNotFoundError("No usable TrueType/OpenType font found")


_default_registry = FontRegistry()


def font_for_lang(lang: str) -> str:
    return _default_registry.font_for_lang(lang)


def load(lang: str, size: int) -> ImageFont.FreeTypeFont:
    return _default_registry.load(lang, size)
