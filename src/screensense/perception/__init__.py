"""Verified Perception Layer

Two-system cross-verification architecture:
- OmniParser: Vision-based UI element detection
- Windows UIA: Ground truth from accessibility tree
- Cross-modal comparison: Only facts both agree on proceed to reasoning
"""

from .context_assembler import ContextAssembler, RichContext
from .cross_modal_comparator import (
    ConfidenceLevel,
    CrossModalComparator,
    VerifiedElement,
)
from .omniparser_client import BoundingBox, DetectedElement, OmniParserClient
from .passive_signals import PassiveContextCollector, PassiveSignals, WindowMetadata
from .semantic_dedup import SemanticDeduplicator
from .windows_uia import Rectangle, UIAElement, WindowsUIAAdapter

__all__ = [
    # OmniParser
    "OmniParserClient",
    "DetectedElement",
    "BoundingBox",
    # Windows UIA
    "WindowsUIAAdapter",
    "UIAElement",
    "Rectangle",
    # Cross-modal comparison
    "CrossModalComparator",
    "VerifiedElement",
    "ConfidenceLevel",
    # Context assembly
    "ContextAssembler",
    "RichContext",
    # Passive signals
    "PassiveContextCollector",
    "PassiveSignals",
    "WindowMetadata",
    # Semantic dedup
    "SemanticDeduplicator",
]
