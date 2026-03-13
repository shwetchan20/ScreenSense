# Requirements Document: Verified Perception Layer

## 1. Functional Requirements

### 1.1 OmniParser Integration
The system SHALL integrate Microsoft's OmniParser model for local UI element detection.

**Acceptance Criteria**:
- OmniParser model loads successfully at startup
- Model detects interactive UI elements (buttons, inputs, links) from screen frames
- Each detected element includes bounding box coordinates (x, y, width, height)
- Each detected element includes element type classification
- Each detected element includes text label extraction
- Detection completes within 2 seconds per frame on CPU, 500ms on GPU

### 1.2 Windows UI Automation Integration
The system SHALL integrate Windows UI Automation API for accessibility tree extraction.

**Acceptance Criteria**:
- UIA adapter queries accessibility tree for active window
- UIA elements include control type, name, automation ID, and bounding rectangle
- UIA elements include enabled/disabled and offscreen states
- Tree extraction completes within 100ms per query
- UIA adapter handles API errors gracefully without crashing

### 1.3 Cross-modal Verification
The system SHALL verify OmniParser outputs against UIA ground truth before reasoning.

**Acceptance Criteria**:
- Comparator matches elements by position (bounding box overlap within 10px tolerance)
- Comparator matches elements by text content (fuzzy matching with 0.9 threshold)
- Comparator matches elements by type (button, input, etc.)
- Elements with all criteria matching are marked HIGH confidence
- Elements with partial matching are marked LOW confidence
- Elements with conflicting data are dropped (CONFLICT)
- Comparison completes within 50ms for typical element counts (10-50 elements)

### 1.4 Clipboard Monitoring
The system SHALL monitor clipboard content for passive context signals.

**Acceptance Criteria**:
- Clipboard content is retrieved on each perception cycle
- Clipboard text is truncated to 500 characters maximum
- Clipboard monitoring handles access denied errors gracefully
- Sensitive patterns (passwords, tokens) are filtered before use
- User can opt-out of clipboard monitoring via configuration

### 1.5 Browser URL Extraction
The system SHALL extract browser URLs from active browser windows.

**Acceptance Criteria**:
- URL is extracted from browser window title or browser API
- URL extraction works for Chrome, Edge, and Firefox
- URL extraction handles non-browser windows gracefully
- URLs are hashed before logging to audit trail
- User can opt-out of URL extraction via configuration

### 1.6 File System Watching
The system SHALL monitor recently modified files for context signals.

**Acceptance Criteria**:
- File watcher tracks files modified within last 60 seconds
- File watcher limits results to 10 most recent files
- File watcher only tracks user-approved directories
- File watcher excludes system directories and hidden files
- File watcher handles permission errors gracefully

### 1.7 Context Assembly
The system SHALL assemble rich context from verified facts and passive signals.

**Acceptance Criteria**:
- Context includes verified elements prioritized by confidence level
- Context includes passive signals (clipboard, URL, files, window metadata)
- Context includes session goal, user name, and project name
- Context is serialized to text format for LLM consumption
- Serialized context does not exceed 4000 tokens
- Context assembly completes within 2 seconds

### 1.8 Qwen2.5 7B Integration
The system SHALL use Qwen2.5 7B text-only model for local reasoning.

**Acceptance Criteria**:
- Qwen2.5 7B model is loaded via Ollama
- Model receives rich context object (no raw screenshots)
- Model generates responses constrained to 12 words maximum
- Model response includes action decision and confidence
- Inference completes within 5 seconds per request
- Model falls back gracefully if Ollama is unavailable

### 1.9 Semantic Deduplication
The system SHALL prevent paraphrased repeat responses using semantic similarity.

**Acceptance Criteria**:
- Deduplicator uses sentence-transformers model (all-MiniLM-L6-v2)
- Deduplicator computes embeddings for each response
- Deduplicator compares new response to 20 most recent responses
- Responses with similarity > 0.85 threshold are suppressed
- Deduplication completes within 100ms per response
- Deduplicator falls back to exact string matching if model fails

### 1.10 Precise Action Targeting
The system SHALL use OmniParser bounding boxes for precise element targeting.

**Acceptance Criteria**:
- Action executor retrieves bounding box from verified HIGH confidence elements
- Action executor uses pixel-perfect coordinates for click/type actions
- Action executor verifies bounding box is within screen bounds
- Action executor falls back to existing targeting if bounding box unavailable
- Action verification confirms action executed at correct coordinates

## 2. Non-Functional Requirements

### 2.1 Performance
The system SHALL complete full perception cycle within 1 second end-to-end.

**Acceptance Criteria**:
- Screen capture to context ready: < 1 second (p95)
- OmniParser inference: < 500ms on GPU, < 2s on CPU (p95)
- UIA tree extraction: < 100ms (p95)
- Cross-modal comparison: < 50ms (p95)
- Context assembly: < 2s (p95)
- Semantic deduplication: < 100ms (p95)

### 2.2 Reliability
The system SHALL operate with zero external API calls (fully local).

**Acceptance Criteria**:
- No network requests to external APIs during perception
- No network requests to external APIs during reasoning
- All models run locally (OmniParser, Qwen2.5, sentence-transformers)
- System continues operating when internet is unavailable
- System logs zero API call attempts in audit trail

### 2.3 Resource Usage
The system SHALL operate within reasonable resource constraints.

**Acceptance Criteria**:
- Peak memory usage < 8GB for models and inference
- CPU usage < 50% average during idle perception cycles
- GPU usage < 80% during OmniParser inference
- Disk space for models < 10GB total
- No memory leaks over 24-hour continuous operation

### 2.4 Degradation Handling
The system SHALL gracefully degrade when components fail.

**Acceptance Criteria**:
- If OmniParser fails, fall back to UIA-only mode with LOW confidence
- If UIA fails, fall back to OmniParser-only mode with LOW confidence
- If both fail, rely on passive signals only
- If semantic dedup fails, fall back to exact string matching
- If Qwen fails, fall back to silent monitoring mode
- All degradation modes are logged to audit trail

### 2.5 Security
The system SHALL protect sensitive user data during perception and reasoning.

**Acceptance Criteria**:
- Clipboard content is filtered for secret patterns before use
- Browser URLs are hashed before logging
- UIA password fields are redacted from context
- File paths exclude system and hidden directories
- No raw UIA tree is logged to audit trail
- All inference happens locally with zero data leaving machine

## 3. Integration Requirements

### 3.1 Existing ARIA Integration
The system SHALL integrate with existing ARIA coordinator and action executor.

**Acceptance Criteria**:
- Verified perception layer replaces existing Gemini vision calls
- Context assembler provides drop-in replacement for existing context extraction
- Action executor receives bounding boxes via existing action schema
- Semantic deduplicator integrates with existing response cleaner
- All existing audit logging continues to function

### 3.2 Configuration Compatibility
The system SHALL support configuration via existing .env file.

**Acceptance Criteria**:
- New config keys added for OmniParser, UIA, passive signals
- Existing config keys remain functional
- Degradation modes configurable via flags
- Opt-out flags for clipboard, URL, file watching
- Model paths and thresholds configurable

### 3.3 Backward Compatibility
The system SHALL maintain backward compatibility with existing features.

**Acceptance Criteria**:
- Existing action types continue to work
- Existing memory and persona systems unaffected
- Existing voice output continues to function
- Existing audit logging format preserved
- Existing test suite passes without modification

## 4. Acceptance Criteria Summary

The Verified Perception Layer feature is considered complete when:

1. All functional requirements (1.1-1.10) are implemented and tested
2. All non-functional requirements (2.1-2.5) are met and verified
3. All integration requirements (3.1-3.3) are satisfied
4. End-to-end perception cycle completes in < 1 second
5. Zero external API calls during normal operation
6. Graceful degradation works for all component failure modes
7. Security measures protect sensitive user data
8. All existing ARIA features continue to function
9. Test coverage reaches 85% for new components
10. Property-based tests pass for all correctness properties
