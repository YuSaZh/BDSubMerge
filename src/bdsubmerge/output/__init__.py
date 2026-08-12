"""Output target resolution, preflight, and atomic writing."""

from .atomic_writer import WriteReceipt, write_outputs_atomically
from .models import (
    AtomicWriteError,
    CollisionPolicy,
    IssueSeverity,
    OutputContext,
    OutputPreflightError,
    OutputPreset,
    PreflightIssue,
    PreflightResult,
    ResolvedOutput,
)
from .preflight import preflight_outputs
from .targets import (
    DiscNameOutputTarget,
    FullPathOutputTarget,
    JRiverOutputTarget,
    OutputTarget,
    PlaylistOutputTarget,
    TemplateOutputTarget,
)

__all__ = [
    "AtomicWriteError",
    "CollisionPolicy",
    "DiscNameOutputTarget",
    "FullPathOutputTarget",
    "IssueSeverity",
    "JRiverOutputTarget",
    "OutputContext",
    "OutputPreflightError",
    "OutputPreset",
    "OutputTarget",
    "PlaylistOutputTarget",
    "PreflightIssue",
    "PreflightResult",
    "ResolvedOutput",
    "TemplateOutputTarget",
    "WriteReceipt",
    "preflight_outputs",
    "write_outputs_atomically",
]
