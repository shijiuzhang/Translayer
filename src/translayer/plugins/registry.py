"""Plugin registry.

Plugins register via the ``@register(kind, key)`` decorator. Third-party
plugins are auto-discovered through ``importlib.metadata`` entry points in the
``translayer.plugins`` group, enabling community-sourced long-tail formats and
engines without modifying the core.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

# kind -> key -> factory/instance
_REGISTRY: dict[str, dict[str, Any]] = {
    "parser": {},
    "renderer": {},
    "enricher": {},
    "translation": {},
    "ocr": {},
    "inpaint": {},
    "image_localization": {},
}

_VALID_KINDS = set(_REGISTRY.keys())


def register(kind: str, key: str) -> Callable[[type], type]:
    """Class decorator to register a plugin under ``kind``/``key``."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unknown plugin kind {kind!r}; valid: {sorted(_VALID_KINDS)}")

    def _decorator(cls: type) -> type:
        _REGISTRY[kind][key] = cls
        return cls

    return _decorator


def get(kind: str, key: str, **kwargs: Any) -> Any:
    """Instantiate a registered plugin."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unknown plugin kind {kind!r}")
    if key not in _REGISTRY[kind]:
        raise KeyError(
            f"No {kind} plugin registered for {key!r}. "
            f"Available: {sorted(_REGISTRY[kind])}"
        )
    return _REGISTRY[kind][key](**kwargs)


def available(kind: str) -> list[str]:
    return sorted(_REGISTRY.get(kind, {}))


def find_parser(fmt: str) -> Any:
    return get("parser", fmt)


def find_renderer(fmt: str) -> Any:
    return get("renderer", fmt)


_discovered = False


def discover() -> None:
    """Load built-in plugins and entry-point plugins (idempotent)."""
    global _discovered
    if _discovered:
        return
    # Import built-ins so their @register decorators run.
    from translayer import parsers as _parsers  # noqa: F401
    from translayer import renderers as _renderers  # noqa: F401
    from translayer.engines import image as _image  # noqa: F401
    from translayer.engines import inpaint as _inpaint  # noqa: F401
    from translayer.engines import ocr as _ocr  # noqa: F401
    from translayer.engines import translation as _translation  # noqa: F401

    try:
        eps = entry_points(group="translayer.plugins")
    except TypeError:  # pragma: no cover - older API
        eps = entry_points().get("translayer.plugins", [])  # type: ignore[attr-defined]
    for ep in eps:
        ep.load()  # importing the module triggers registration

    _discovered = True
