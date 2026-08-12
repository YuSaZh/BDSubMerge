"""Built-in output target strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from string import Formatter

from .models import CollisionPolicy, OutputContext, OutputPreset

_TEMPLATE_FIELDS = frozenset(
    {"disc_name", "playlist", "playlist_stem", "index_stem", "language", "format", "volume"}
)


@dataclass(frozen=True, slots=True)
class OutputTarget(ABC):
    """Destination policy; resolving paths never writes to the filesystem."""

    target_id: str
    collision_policy: CollisionPolicy = CollisionPolicy.ABORT
    encoding: str = "utf-8-sig"

    def __post_init__(self) -> None:
        if not self.target_id:
            raise ValueError("output target id cannot be empty")
        if not self.encoding:
            raise ValueError("output encoding cannot be empty")

    @property
    @abstractmethod
    def preset(self) -> OutputPreset:
        raise NotImplementedError

    @abstractmethod
    def resolve_path(self, context: OutputContext) -> Path:
        raise NotImplementedError

    def validate(self, context: OutputContext) -> tuple[str, ...]:
        del context
        return ()

    def describe(self, context: OutputContext) -> str:
        return str(self.resolve_path(context))


@dataclass(frozen=True, slots=True)
class JRiverOutputTarget(OutputTarget):
    @property
    def preset(self) -> OutputPreset:
        return OutputPreset.JRIVER

    def resolve_path(self, context: OutputContext) -> Path:
        if context.index_bdmv_path is None:
            raise ValueError("JRiver output requires the discovered index.bdmv path")
        return context.index_bdmv_path.with_suffix(f".{context.extension}")

    def validate(self, context: OutputContext) -> tuple[str, ...]:
        errors: list[str] = []
        if self.collision_policy is CollisionPolicy.AUTO_RENAME:
            errors.append("JRiver output cannot use automatic renaming")
        if context.index_bdmv_path is None:
            errors.append("JRiver output requires the discovered index.bdmv path")
        elif _portable_name(context.index_bdmv_path).casefold() != "index.bdmv":
            errors.append("JRiver source path must identify index.bdmv")
        return tuple(errors)


@dataclass(frozen=True, slots=True)
class PlaylistOutputTarget(OutputTarget):
    language_suffix: bool = False

    @property
    def preset(self) -> OutputPreset:
        return OutputPreset.PLAYLIST

    def resolve_path(self, context: OutputContext) -> Path:
        if context.playlist_path is None:
            raise ValueError("playlist output requires an MPLS path")
        language = f".{context.language}" if self.language_suffix and context.language else ""
        return context.playlist_path.parent / (
            f"{context.playlist_path.stem}{language}.{context.extension}"
        )


@dataclass(frozen=True, slots=True)
class DiscNameOutputTarget(OutputTarget):
    directory: Path | None = None

    @property
    def preset(self) -> OutputPreset:
        return OutputPreset.DISC_NAME

    def resolve_path(self, context: OutputContext) -> Path:
        if context.disc_container_path is None:
            raise ValueError("disc-name output requires the disc container path")
        directory = self.directory or context.disc_container_path.parent
        return directory / f"{context.disc_container_path.name}.{context.extension}"


@dataclass(frozen=True, slots=True)
class TemplateOutputTarget(OutputTarget):
    directory: Path = field(default_factory=lambda: Path("."))
    template: str = "{disc_name}_{playlist_stem}_{language}.{format}"

    @property
    def preset(self) -> OutputPreset:
        return OutputPreset.CUSTOM

    def resolve_path(self, context: OutputContext) -> Path:
        if not self.template:
            raise ValueError("output template cannot be empty")
        parsed = tuple(Formatter().parse(self.template))
        unknown = {
            field_name
            for _, field_name, _, _ in parsed
            if field_name is not None and field_name not in _TEMPLATE_FIELDS
        }
        if unknown:
            raise ValueError(f"unknown output template variables: {', '.join(sorted(unknown))}")
        if any(format_spec or conversion for _, _, format_spec, conversion in parsed):
            raise ValueError("output template does not allow format specs or conversions")
        rendered = self.template.format_map(context.variables)
        rendered_path = Path(rendered)
        if rendered_path.is_absolute() or rendered_path.name != rendered:
            raise ValueError("output template must render a single file name")
        return self.directory / rendered


@dataclass(frozen=True, slots=True)
class FullPathOutputTarget(OutputTarget):
    path: Path = field(default_factory=lambda: Path("output.ass"))

    @property
    def preset(self) -> OutputPreset:
        return OutputPreset.FULL_PATH

    def resolve_path(self, context: OutputContext) -> Path:
        del context
        return self.path


def _portable_name(path: Path) -> str:
    native_name = path.name
    if "\\" in native_name:
        return PureWindowsPath(str(path)).name
    return native_name
