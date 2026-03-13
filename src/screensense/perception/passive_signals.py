"""Passive Context Signals Collector

Collects context signals without requiring vision inference:
- Clipboard monitoring
- Browser URL extraction
- File system watching
- Window/process metadata
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import pyperclip
except ImportError:
    pyperclip = None  # type: ignore


@dataclass
class WindowMetadata:
    """Active window and process metadata"""
    process_name: str
    window_title: str
    pid: int
    timestamp: float


@dataclass
class PassiveSignals:
    """Collection of passive context signals"""
    clipboard_content: str | None
    browser_url: str | None
    recent_files: list[str]
    window_metadata: WindowMetadata
    timestamp: float


class PassiveContextCollector:
    """Collects passive context signals without vision inference"""
    
    # Patterns that indicate sensitive data in clipboard
    SECRET_PATTERNS = [
        r'password[:\s]*\S+',
        r'token[:\s]*\S+',
        r'api[_-]?key[:\s]*\S+',
        r'secret[:\s]*\S+',
        r'\b[A-Za-z0-9]{32,}\b',  # Long alphanumeric strings (likely tokens)
    ]
    
    # Sensitive domains to exclude from URL extraction
    SENSITIVE_DOMAINS = [
        'bank', 'paypal', 'stripe', 'healthcare', 'medical',
        'password', 'login', 'auth', 'signin'
    ]
    
    def __init__(
        self,
        *,
        enable_clipboard: bool = True,
        enable_browser_url: bool = True,
        enable_file_watch: bool = True,
        clipboard_max_chars: int = 500,
    ):
        self._enable_clipboard = enable_clipboard
        self._enable_browser_url = enable_browser_url
        self._enable_file_watch = enable_file_watch
        self._clipboard_max_chars = clipboard_max_chars
        self._last_clipboard = ""
        self._recent_files: list[tuple[str, float]] = []
    
    def collect(self, window_metadata: WindowMetadata) -> PassiveSignals:
        """Collect all passive signals"""
        return PassiveSignals(
            clipboard_content=self.get_clipboard_content() if self._enable_clipboard else None,
            browser_url=self.get_browser_url(window_metadata) if self._enable_browser_url else None,
            recent_files=self.get_recent_files() if self._enable_file_watch else [],
            window_metadata=window_metadata,
            timestamp=time.time(),
        )
    
    def get_clipboard_content(self) -> str | None:
        """Get clipboard text content with security filtering"""
        if pyperclip is None:
            return None
        
        try:
            content = pyperclip.paste()
            if not content or content == self._last_clipboard:
                return None
            
            self._last_clipboard = content
            
            # Filter sensitive patterns
            if self._contains_secrets(content):
                return None
            
            # Truncate to max length
            if len(content) > self._clipboard_max_chars:
                content = content[:self._clipboard_max_chars] + "..."
            
            return content
        except Exception:
            return None
    
    def get_browser_url(self, window_metadata: WindowMetadata) -> str | None:
        """Extract URL from browser window title"""
        title = window_metadata.window_title.lower()
        process = window_metadata.process_name.lower()
        
        # Check if it's a browser
        if not any(browser in process for browser in ['chrome', 'firefox', 'edge', 'brave', 'opera']):
            return None
        
        # Extract URL from title (browsers often show URL in title)
        # Format: "Page Title - URL - Browser Name"
        url_match = re.search(r'https?://[^\s]+', window_metadata.window_title)
        if url_match:
            url = url_match.group(0)
            
            # Check for sensitive domains
            if any(domain in url.lower() for domain in self.SENSITIVE_DOMAINS):
                return None
            
            return url
        
        return None
    
    def get_recent_files(self, window_seconds: int = 60, max_files: int = 10) -> list[str]:
        """Get list of recently modified files (placeholder - needs watchdog integration)"""
        # TODO: Implement with watchdog file system monitoring
        # For now, return empty list
        return []
    
    def _contains_secrets(self, text: str) -> bool:
        """Check if text contains sensitive patterns"""
        text_lower = text.lower()
        for pattern in self.SECRET_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False
