"""Context Assembler

Merges verified perception facts with passive signals into rich context object.
Serializes context for LLM consumption with token limits.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .cross_modal_comparator import ConfidenceLevel, VerifiedElement
from .passive_signals import PassiveSignals


@dataclass
class RichContext:
    """Complete context object for LLM reasoning"""
    verified_elements: list[VerifiedElement]
    passive_signals: PassiveSignals
    session_goal: str | None
    user_name: str | None
    project_name: str | None
    timestamp: float
    
    def high_confidence_count(self) -> int:
        """Count of high-confidence verified elements"""
        return sum(
            1 for elem in self.verified_elements
            if elem.confidence == ConfidenceLevel.HIGH
        )
    
    def low_confidence_count(self) -> int:
        """Count of low-confidence elements"""
        return sum(
            1 for elem in self.verified_elements
            if elem.confidence == ConfidenceLevel.LOW
        )


class ContextAssembler:
    """Assembles verified facts and passive signals into rich context"""
    
    def __init__(
        self,
        *,
        max_tokens: int = 4000,
        prioritize_high_confidence: bool = True,
    ):
        """
        Initialize context assembler.
        
        Args:
            max_tokens: Maximum token count for serialized context
            prioritize_high_confidence: Prioritize high-confidence elements
        """
        self._max_tokens = max_tokens
        self._prioritize_high_confidence = prioritize_high_confidence
    
    def assemble_context(
        self,
        verified_elements: list[VerifiedElement],
        passive_signals: PassiveSignals,
        *,
        session_goal: str | None = None,
        user_name: str | None = None,
        project_name: str | None = None,
    ) -> RichContext:
        """
        Assemble complete context from verified elements and passive signals.
        
        Args:
            verified_elements: Elements verified by cross-modal comparison
            passive_signals: Passive context signals
            session_goal: Current user goal/task
            user_name: User name for personalization
            project_name: Current project name
        
        Returns:
            Rich context object ready for LLM
        """
        # Sort elements by confidence if prioritization enabled
        if self._prioritize_high_confidence:
            verified_elements = sorted(
                verified_elements,
                key=lambda e: (
                    e.confidence == ConfidenceLevel.HIGH,
                    e.omniparser_confidence,
                ),
                reverse=True,
            )
        
        return RichContext(
            verified_elements=verified_elements,
            passive_signals=passive_signals,
            session_goal=session_goal,
            user_name=user_name,
            project_name=project_name,
            timestamp=time.time(),
        )
    
    def serialize_for_llm(self, context: RichContext) -> str:
        """
        Serialize context to text format for LLM consumption.
        
        Args:
            context: Rich context object
        
        Returns:
            Formatted text context (truncated to max_tokens)
        """
        lines: list[str] = []
        
        # Header
        lines.append("=== VERIFIED SCREEN CONTEXT ===")
        lines.append(f"Timestamp: {time.strftime('%H:%M:%S', time.localtime(context.timestamp))}")
        
        if context.user_name:
            lines.append(f"User: {context.user_name}")
        if context.project_name:
            lines.append(f"Project: {context.project_name}")
        if context.session_goal:
            lines.append(f"Goal: {context.session_goal}")
        
        lines.append("")
        
        # Window metadata
        wm = context.passive_signals.window_metadata
        lines.append(f"Active Window: {wm.window_title}")
        lines.append(f"Process: {wm.process_name} (PID: {wm.pid})")
        lines.append("")
        
        # Verified elements (HIGH confidence first)
        high_conf = [e for e in context.verified_elements if e.confidence == ConfidenceLevel.HIGH]
        low_conf = [e for e in context.verified_elements if e.confidence == ConfidenceLevel.LOW]
        
        if high_conf:
            lines.append("=== HIGH CONFIDENCE ELEMENTS (both OmniParser + UIA agree) ===")
            for elem in high_conf[:20]:  # Limit to top 20
                lines.append(
                    f"- {elem.element_type}: \"{elem.text}\" "
                    f"at ({elem.bbox.x}, {elem.bbox.y}) "
                    f"[{elem.bbox.width}x{elem.bbox.height}]"
                )
            lines.append("")
        
        if low_conf:
            lines.append("=== LOW CONFIDENCE ELEMENTS (single source only) ===")
            for elem in low_conf[:10]:  # Limit to top 10
                source = "OmniParser" if elem.omniparser_source else "UIA"
                lines.append(
                    f"- {elem.element_type}: \"{elem.text}\" "
                    f"at ({elem.bbox.x}, {elem.bbox.y}) [{source}]"
                )
            lines.append("")
        
        # Passive signals
        lines.append("=== PASSIVE CONTEXT SIGNALS ===")
        
        if context.passive_signals.clipboard_content:
            lines.append(f"Clipboard: {context.passive_signals.clipboard_content}")
        
        if context.passive_signals.browser_url:
            lines.append(f"Browser URL: {context.passive_signals.browser_url}")
        
        if context.passive_signals.recent_files:
            lines.append("Recent Files:")
            for filepath in context.passive_signals.recent_files[:5]:
                lines.append(f"  - {filepath}")
        
        lines.append("")
        lines.append("=== END CONTEXT ===")
        
        # Join and truncate to max tokens (rough estimate: 4 chars per token)
        text = "\n".join(lines)
        max_chars = self._max_tokens * 4
        
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [truncated]"
        
        return text
    
    def count_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)"""
        # Rough estimate: 1 token ≈ 4 characters
        return len(text) // 4
