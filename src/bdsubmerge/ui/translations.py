"""Runtime JSON translation catalog for UI-owned text."""

from __future__ import annotations

import json
from importlib.resources import files


class TranslationCatalog:
    SUPPORTED = ("zh_CN", "en_US")

    def __init__(self, locale: str = "zh_CN") -> None:
        self._locale = locale if locale in self.SUPPORTED else "zh_CN"
        self._messages = self._load(self._locale)

    @property
    def locale(self) -> str:
        return self._locale

    def set_locale(self, locale: str) -> None:
        if locale not in self.SUPPORTED:
            raise ValueError(f"unsupported UI locale: {locale}")
        self._locale = locale
        self._messages = self._load(locale)

    def text(self, key: str, **values: object) -> str:
        template = self._messages.get(key, key)
        return template.format_map(values) if values else template

    @staticmethod
    def _load(locale: str) -> dict[str, str]:
        resource = files("bdsubmerge.resources").joinpath("i18n", f"{locale}.json")
        parsed = json.loads(resource.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
        ):
            raise ValueError(f"invalid translation catalog: {locale}")
        return parsed
