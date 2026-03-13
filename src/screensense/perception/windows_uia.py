"""Windows UI Automation Adapter

Interfaces with Windows UI Automation API to extract accessibility tree ground truth.
Provides element hierarchy, properties, and positions from Windows memory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

try:
    import uiautomation as auto
except ImportError:
    auto = None  # type: ignore


@dataclass
class Rectangle:
    """Rectangle coordinates"""
    x: int
    y: int
    width: int
    height: int


@dataclass
class UIAElement:
    """UI element from Windows UI Automation"""
    control_type: str  # UIA control type
    name: str
    automation_id: str
    rect: Rectangle
    is_enabled: bool
    is_offscreen: bool
    properties: dict[str, Any]


class WindowsUIAAdapter:
    """Adapter for Windows UI Automation API"""
    
    # UIA control type mappings
    CONTROL_TYPE_MAP = {
        'ButtonControl': 'button',
        'EditControl': 'input',
        'TextControl': 'text',
        'HyperlinkControl': 'link',
        'ImageControl': 'image',
        'CheckBoxControl': 'checkbox',
        'RadioButtonControl': 'radio',
        'ComboBoxControl': 'dropdown',
        'MenuControl': 'menu',
        'MenuItemControl': 'menuitem',
    }
    
    def __init__(
        self,
        *,
        cache_ttl_seconds: float = 0.5,
        max_depth: int = 10,
    ):
        """
        Initialize UIA adapter.
        
        Args:
            cache_ttl_seconds: Cache TTL for accessibility tree
            max_depth: Maximum tree depth to traverse
        """
        self._cache_ttl = cache_ttl_seconds
        self._max_depth = max_depth
        self._cache: list[UIAElement] | None = None
        self._cache_ts: float = 0.0
        self._last_window_title: str = ""
    
    def get_accessibility_tree(self, window_title: str | None = None) -> list[UIAElement]:
        """
        Extract accessibility tree from active window.
        
        Args:
            window_title: Window title to extract from (None = active window)
        
        Returns:
            List of UIA elements with properties and positions
        """
        if auto is None:
            return []
        
        # Check cache
        now = time.time()
        if (
            self._cache is not None
            and now - self._cache_ts < self._cache_ttl
            and window_title == self._last_window_title
        ):
            return self._cache
        
        try:
            # Get active window or specific window
            if window_title:
                window = auto.WindowControl(searchDepth=1, Name=window_title)
            else:
                window = auto.GetForegroundControl()
            
            if not window or not window.Exists(0, 0):
                return []
            
            # Extract elements with timeout protection
            elements = []
            try:
                elements = self._extract_elements(window, depth=0)
            except Exception as e:
                print(f"[UIA] Extraction error: {e}")
                return []
            
            # Limit to reasonable number
            if len(elements) > 100:
                elements = elements[:100]
            
            # Update cache
            self._cache = elements
            self._cache_ts = now
            self._last_window_title = window_title or ""
            
            return elements
        except Exception as e:
            print(f"[UIA] Failed to extract tree: {e}")
            return []
    
    def get_element_at_point(self, x: int, y: int) -> UIAElement | None:
        """
        Get UIA element at specific screen coordinates.
        
        Args:
            x: Screen x coordinate
            y: Screen y coordinate
        
        Returns:
            UIAElement if found, None otherwise
        """
        if auto is None:
            return None
        
        try:
            control = auto.ControlFromPoint(x, y)
            if not control or not control.Exists(0):
                return None
            
            return self._control_to_element(control)
        except Exception:
            return None
    
    def _extract_elements(
        self,
        control: Any,
        depth: int,
    ) -> list[UIAElement]:
        """Recursively extract elements from control tree"""
        elements: list[UIAElement] = []
        
        try:
            # Add current control
            element = self._control_to_element(control)
            if element:
                elements.append(element)
            
            # Stop if we've reached max depth
            if depth >= self._max_depth:
                return elements
            
            # Recursively process children with better error handling
            try:
                # Try multiple methods to get children
                children = []
                try:
                    children = control.GetChildren()
                except Exception:
                    # Fallback: try GetFirstChildControl and iterate siblings
                    try:
                        child = control.GetFirstChildControl()
                        while child and child.Exists(0, 0):
                            children.append(child)
                            try:
                                child = child.GetNextSiblingControl()
                            except Exception:
                                break
                    except Exception:
                        pass
                
                # Process each child
                for child in children:
                    if child and child.Exists(0, 0):
                        try:
                            child_elements = self._extract_elements(child, depth + 1)
                            elements.extend(child_elements)
                        except Exception:
                            # Continue with next child even if one fails
                            continue
            except Exception:
                pass
        except Exception:
            pass
        
        return elements
    
    def _control_to_element(self, control: Any) -> UIAElement | None:
        """Convert UIA control to UIAElement"""
        try:
            # Get bounding rectangle
            try:
                rect = control.BoundingRectangle
                # Allow elements with zero size (they might be containers)
                if not rect:
                    return None
            except Exception:
                return None
            
            # Get control type
            try:
                control_type = control.ControlTypeName
            except Exception:
                control_type = "Unknown"
            
            # Filter password fields
            try:
                if 'Password' in control_type or control.IsPassword:
                    return None
            except Exception:
                pass
            
            # Get name
            try:
                name = control.Name or ""
            except Exception:
                name = ""
            
            # Get automation ID
            try:
                automation_id = control.AutomationId or ""
            except Exception:
                automation_id = ""
            
            # Get enabled state
            try:
                is_enabled = control.IsEnabled
            except Exception:
                is_enabled = True
            
            # Get offscreen state
            try:
                is_offscreen = control.IsOffscreen
            except Exception:
                is_offscreen = False
            
            # Don't skip offscreen elements - they might still be useful
            # Just mark them as offscreen
            
            # Get properties
            properties = {}
            try:
                properties['class_name'] = control.ClassName or ""
            except Exception:
                pass
            
            try:
                value_pattern = control.GetValuePattern()
                if value_pattern:
                    properties['value'] = value_pattern.Value
            except Exception:
                pass
            
            # Create rectangle with safe defaults
            try:
                x = rect.left if hasattr(rect, 'left') else 0
                y = rect.top if hasattr(rect, 'top') else 0
                width = rect.width() if hasattr(rect, 'width') else 0
                height = rect.height() if hasattr(rect, 'height') else 0
            except Exception:
                x, y, width, height = 0, 0, 0, 0
            
            return UIAElement(
                control_type=control_type,
                name=name,
                automation_id=automation_id,
                rect=Rectangle(
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                ),
                is_enabled=is_enabled,
                is_offscreen=is_offscreen,
                properties=properties,
            )
        except Exception as e:
            return None
    
    def invalidate_cache(self) -> None:
        """Invalidate cached accessibility tree"""
        self._cache = None
        self._cache_ts = 0.0
