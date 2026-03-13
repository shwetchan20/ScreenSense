"""Cross-Modal Comparator

Compares OmniParser vision detections with Windows UIA ground truth.
Only facts both systems agree on are treated as verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .omniparser_client import BoundingBox, DetectedElement
from .windows_uia import Rectangle, UIAElement


class ConfidenceLevel(Enum):
    """Verification confidence levels"""
    HIGH = "high"  # Both sources agree
    LOW = "low"  # Only one source found it
    CONFLICT = "conflict"  # Sources contradict


@dataclass
class VerifiedElement:
    """UI element verified by cross-modal comparison"""
    element_type: str
    text: str
    bbox: BoundingBox
    confidence: ConfidenceLevel
    omniparser_confidence: float
    uia_source: bool
    omniparser_source: bool
    attributes: dict


class CrossModalComparator:
    """Compares OmniParser and UIA outputs for verification"""
    
    def __init__(
        self,
        *,
        position_tolerance: int = 20,
        text_similarity_threshold: float = 0.8,
    ):
        """
        Initialize comparator.
        
        Args:
            position_tolerance: Pixel tolerance for position matching
            text_similarity_threshold: Threshold for fuzzy text matching
        """
        self._position_tolerance = position_tolerance
        self._text_threshold = text_similarity_threshold
    
    def compare_elements(
        self,
        omni_elements: list[DetectedElement],
        uia_elements: list[UIAElement],
    ) -> list[VerifiedElement]:
        """
        Compare OmniParser and UIA elements, return verified facts.
        
        Args:
            omni_elements: Elements detected by OmniParser
            uia_elements: Elements from Windows UIA
        
        Returns:
            List of verified elements with confidence levels
        """
        verified: list[VerifiedElement] = []
        matched_uia: set[int] = set()
        matched_omni: set[int] = set()
        
        # Match OmniParser elements with UIA elements
        for i, omni_elem in enumerate(omni_elements):
            best_match_idx = -1
            best_match_score = 0.0
            
            for j, uia_elem in enumerate(uia_elements):
                if j in matched_uia:
                    continue
                
                score = self._match_score(omni_elem, uia_elem)
                if score > best_match_score and score > 0.5:
                    best_match_score = score
                    best_match_idx = j
            
            if best_match_idx >= 0:
                # HIGH confidence: both sources agree
                uia_elem = uia_elements[best_match_idx]
                verified.append(
                    VerifiedElement(
                        element_type=omni_elem.element_type,
                        text=omni_elem.text_label or uia_elem.name,
                        bbox=omni_elem.bbox,
                        confidence=ConfidenceLevel.HIGH,
                        omniparser_confidence=omni_elem.confidence,
                        uia_source=True,
                        omniparser_source=True,
                        attributes={**omni_elem.attributes, **uia_elem.properties},
                    )
                )
                matched_uia.add(best_match_idx)
                matched_omni.add(i)
        
        # Add unmatched OmniParser elements as LOW confidence
        for i, omni_elem in enumerate(omni_elements):
            if i not in matched_omni:
                verified.append(
                    VerifiedElement(
                        element_type=omni_elem.element_type,
                        text=omni_elem.text_label,
                        bbox=omni_elem.bbox,
                        confidence=ConfidenceLevel.LOW,
                        omniparser_confidence=omni_elem.confidence,
                        uia_source=False,
                        omniparser_source=True,
                        attributes=omni_elem.attributes,
                    )
                )
        
        # Add unmatched UIA elements as LOW confidence
        for j, uia_elem in enumerate(uia_elements):
            if j not in matched_uia and not uia_elem.is_offscreen:
                verified.append(
                    VerifiedElement(
                        element_type=self._map_uia_type(uia_elem.control_type),
                        text=uia_elem.name,
                        bbox=BoundingBox(
                            x=uia_elem.rect.x,
                            y=uia_elem.rect.y,
                            width=uia_elem.rect.width,
                            height=uia_elem.rect.height,
                        ),
                        confidence=ConfidenceLevel.LOW,
                        omniparser_confidence=0.0,
                        uia_source=True,
                        omniparser_source=False,
                        attributes=uia_elem.properties,
                    )
                )
        
        return verified
    
    def _match_score(self, omni: DetectedElement, uia: UIAElement) -> float:
        """Calculate match score between OmniParser and UIA elements"""
        score = 0.0
        
        # Position matching (40% weight)
        if self._match_by_position(omni.bbox, uia.rect):
            score += 0.4
        
        # Text matching (40% weight)
        text_sim = self._text_similarity(omni.text_label, uia.name)
        score += 0.4 * text_sim
        
        # Type matching (20% weight)
        if self._match_by_type(omni.element_type, uia.control_type):
            score += 0.2
        
        return score
    
    def _match_by_position(self, bbox: BoundingBox, rect: Rectangle) -> bool:
        """Check if bounding box and rectangle overlap within tolerance"""
        # Convert Rectangle to BoundingBox for comparison
        uia_bbox = BoundingBox(
            x=rect.x,
            y=rect.y,
            width=rect.width,
            height=rect.height,
        )
        return bbox.overlaps(uia_bbox, tolerance=self._position_tolerance)
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate fuzzy text similarity (simple Levenshtein-based)"""
        if not text1 or not text2:
            return 0.0
        
        text1 = text1.lower().strip()
        text2 = text2.lower().strip()
        
        if text1 == text2:
            return 1.0
        
        # Simple containment check
        if text1 in text2 or text2 in text1:
            return 0.8
        
        # Levenshtein distance (simplified)
        distance = self._levenshtein(text1, text2)
        max_len = max(len(text1), len(text2))
        return 1.0 - (distance / max_len) if max_len > 0 else 0.0
    
    def _match_by_type(self, omni_type: str, uia_type: str) -> bool:
        """Check if element types match"""
        from .windows_uia import WindowsUIAAdapter
        
        mapped_uia_type = WindowsUIAAdapter.CONTROL_TYPE_MAP.get(uia_type, "")
        return omni_type.lower() == mapped_uia_type.lower()
    
    def _map_uia_type(self, uia_type: str) -> str:
        """Map UIA control type to generic element type"""
        from .windows_uia import WindowsUIAAdapter
        
        return WindowsUIAAdapter.CONTROL_TYPE_MAP.get(uia_type, "unknown")
    
    @staticmethod
    def _levenshtein(s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return CrossModalComparator._levenshtein(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
