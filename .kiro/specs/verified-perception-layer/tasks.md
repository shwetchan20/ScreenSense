# Tasks: Verified Perception Layer

## Phase 1: Core Perception Components

### 1.1 OmniParser Model Integration
- [ ] 1.1.1 Research OmniParser model architecture and inference requirements
- [ ] 1.1.2 Create `src/screensense/perception/omniparser_client.py` module
- [ ] 1.1.3 Implement model loading and initialization
- [ ] 1.1.4 Implement `detect_elements()` method with frame preprocessing
- [ ] 1.1.5 Implement `get_bounding_box()` method for element lookup
- [ ] 1.1.6 Add error handling for model load failures
- [ ] 1.1.7 Write unit tests for OmniParser client
- [ ] 1.1.8 Benchmark inference latency on CPU and GPU

### 1.2 Windows UI Automation Adapter
- [ ] 1.2.1 Create `src/screensense/perception/windows_uia.py` module
- [ ] 1.2.2 Implement `get_accessibility_tree()` method using comtypes/pywinauto
- [ ] 1.2.3 Implement `get_element_at_point()` method for coordinate lookup
- [ ] 1.2.4 Add UIA element property extraction (type, name, rect, state)
- [ ] 1.2.5 Add error handling for UIA API exceptions
- [ ] 1.2.6 Implement tree depth limiting (max 5 levels)
- [ ] 1.2.7 Add caching layer (500ms TTL, invalidate on window change)
- [ ] 1.2.8 Write unit tests with mocked UIA API
- [ ] 1.2.9 Benchmark tree extraction latency

### 1.3 Cross-modal Comparator
- [ ] 1.3.1 Create `src/screensense/perception/cross_modal_comparator.py` module
- [ ] 1.3.2 Implement `compare_elements()` method
- [ ] 1.3.3 Implement `match_by_position()` with configurable tolerance
- [ ] 1.3.4 Implement `match_by_text()` with fuzzy string matching
- [ ] 1.3.5 Implement `match_by_type()` with type mapping
- [ ] 1.3.6 Implement confidence level assignment (HIGH/LOW/CONFLICT)
- [ ] 1.3.7 Add spatial indexing (R-tree) for position matching optimization
- [ ] 1.3.8 Write unit tests with synthetic element pairs
- [ ] 1.3.9 Write property-based tests for matching symmetry and transitivity
- [ ] 1.3.10 Benchmark comparison latency for various element counts

## Phase 2: Passive Context Signals

### 2.1 Clipboard Monitoring
- [ ] 2.1.1 Create `src/screensense/perception/passive_signals.py` module
- [ ] 2.1.2 Implement `get_clipboard_content()` using pyperclip
- [ ] 2.1.3 Add clipboard content truncation (500 chars)
- [ ] 2.1.4 Implement secret pattern filtering (passwords, tokens, API keys)
- [ ] 2.1.5 Add error handling for clipboard access denied
- [ ] 2.1.6 Add opt-out configuration flag
- [ ] 2.1.7 Write unit tests with mocked clipboard

### 2.2 Browser URL Extraction
- [ ] 2.2.1 Implement `get_browser_url()` method
- [ ] 2.2.2 Add URL extraction from window title (Chrome, Edge, Firefox)
- [ ] 2.2.3 Add URL extraction from browser automation APIs (optional)
- [ ] 2.2.4 Implement URL hashing for audit logging
- [ ] 2.2.5 Add sensitive domain blocklist (banking, health, etc.)
- [ ] 2.2.6 Add opt-out configuration flag
- [ ] 2.2.7 Write unit tests with mocked window titles

### 2.3 File System Watching
- [ ] 2.3.1 Implement `get_recent_files()` using watchdog
- [ ] 2.3.2 Add file modification tracking (60-second window)
- [ ] 2.3.3 Limit results to 10 most recent files
- [ ] 2.3.4 Add directory allowlist configuration
- [ ] 2.3.5 Exclude system directories and hidden files
- [ ] 2.3.6 Add error handling for permission errors
- [ ] 2.3.7 Add opt-out configuration flag
- [ ] 2.3.8 Write unit tests with temporary file fixtures

### 2.4 Window Metadata Collection
- [ ] 2.4.1 Implement `get_window_metadata()` method
- [ ] 2.4.2 Extract active window title, process name, PID
- [ ] 2.4.3 Add window state (maximized, minimized, focused)
- [ ] 2.4.4 Add timestamp to metadata
- [ ] 2.4.5 Write unit tests with mocked window APIs

## Phase 3: Context Assembly and Reasoning

### 3.1 Context Assembler
- [ ] 3.1.1 Create `src/screensense/perception/context_assembler.py` module
- [ ] 3.1.2 Implement `assemble_context()` method
- [ ] 3.1.3 Merge verified elements prioritized by confidence level
- [ ] 3.1.4 Integrate passive signals into context
- [ ] 3.1.5 Add session goal, user name, project name fields
- [ ] 3.1.6 Implement `serialize_for_llm()` method
- [ ] 3.1.7 Add token counting and truncation (4000 token limit)
- [ ] 3.1.8 Write unit tests for context merging logic
- [ ] 3.1.9 Write property-based tests for assembly idempotence

### 3.2 Qwen2.5 7B Integration
- [ ] 3.2.1 Update `src/screensense/inference/local_qwen.py` for text-only mode
- [ ] 3.2.2 Remove vision frame encoding for Qwen2.5
- [ ] 3.2.3 Update prompt template to consume rich context object
- [ ] 3.2.4 Add 12-word response constraint enforcement
- [ ] 3.2.5 Add fallback handling for Ollama unavailable
- [ ] 3.2.6 Update model configuration in .env.example
- [ ] 3.2.7 Write unit tests with mocked Ollama API
- [ ] 3.2.8 Benchmark inference latency with rich context

### 3.3 Semantic Deduplication
- [ ] 3.3.1 Create `src/screensense/perception/semantic_dedup.py` module
- [ ] 3.3.2 Implement `SemanticDeduplicator` class with sentence-transformers
- [ ] 3.3.3 Implement `is_duplicate()` method with cosine similarity
- [ ] 3.3.4 Implement `add_to_history()` with rolling window (20 responses)
- [ ] 3.3.5 Add configurable similarity threshold (default 0.85)
- [ ] 3.3.6 Add fallback to exact string matching if model fails
- [ ] 3.3.7 Write unit tests with sample responses
- [ ] 3.3.8 Write property-based tests for consistency
- [ ] 3.3.9 Benchmark embedding computation latency

## Phase 4: Action Execution Enhancement

### 4.1 Bounding Box Action Targeting
- [ ] 4.1.1 Update `src/screensense/core/action_executor.py` to accept bounding boxes
- [ ] 4.1.2 Implement bounding box retrieval from verified elements
- [ ] 4.1.3 Add bounding box validation (within screen bounds)
- [ ] 4.1.4 Update click action to use bounding box center point
- [ ] 4.1.5 Update type action to use bounding box for element focus
- [ ] 4.1.6 Add fallback to existing targeting if bounding box unavailable
- [ ] 4.1.7 Update action verification to confirm correct coordinates
- [ ] 4.1.8 Write unit tests for bounding box targeting
- [ ] 4.1.9 Write integration tests with real UI elements

## Phase 5: Coordinator Integration

### 5.1 Perception Pipeline Integration
- [ ] 5.1.1 Update `src/screensense/core/coordinator.py` to use verified perception
- [ ] 5.1.2 Replace Gemini vision calls with OmniParser + UIA + Comparator
- [ ] 5.1.3 Integrate passive signals collector into perception loop
- [ ] 5.1.4 Integrate context assembler into reasoning flow
- [ ] 5.1.5 Integrate semantic deduplicator into response pipeline
- [ ] 5.1.6 Add degradation mode handling (OmniParser-only, UIA-only, passive-only)
- [ ] 5.1.7 Update audit logging to include perception metadata
- [ ] 5.1.8 Write integration tests for full perception cycle

### 5.2 Configuration Management
- [ ] 5.2.1 Add OmniParser configuration keys to .env.example
- [ ] 5.2.2 Add UIA configuration keys (cache TTL, depth limit)
- [ ] 5.2.3 Add passive signals configuration keys (opt-out flags)
- [ ] 5.2.4 Add semantic dedup configuration keys (threshold, history size)
- [ ] 5.2.5 Add degradation mode configuration flags
- [ ] 5.2.6 Update `src/screensense/config.py` with new settings
- [ ] 5.2.7 Update README.md with configuration documentation
- [ ] 5.2.8 Create migration guide for existing .env files

### 5.3 Dependency Management
- [ ] 5.3.1 Add omniparser to pyproject.toml dependencies
- [ ] 5.3.2 Add sentence-transformers to pyproject.toml
- [ ] 5.3.3 Add watchdog to pyproject.toml
- [ ] 5.3.4 Add pyperclip to pyproject.toml
- [ ] 5.3.5 Add comtypes or pywinauto to pyproject.toml
- [ ] 5.3.6 Remove google-generativeai from dependencies
- [ ] 5.3.7 Update installation instructions in README.md
- [ ] 5.3.8 Create model download script for OmniParser and sentence-transformers

## Phase 6: Testing and Validation

### 6.1 Unit Test Coverage
- [ ] 6.1.1 Achieve 85% line coverage for OmniParser client
- [ ] 6.1.2 Achieve 85% line coverage for UIA adapter
- [ ] 6.1.3 Achieve 85% line coverage for cross-modal comparator
- [ ] 6.1.4 Achieve 85% line coverage for passive signals collector
- [ ] 6.1.5 Achieve 85% line coverage for context assembler
- [ ] 6.1.6 Achieve 85% line coverage for semantic deduplicator
- [ ] 6.1.7 Run full test suite and verify all tests pass

### 6.2 Property-Based Testing
- [ ] 6.2.1 Write property test for cross-modal comparator symmetry
- [ ] 6.2.2 Write property test for bounding box overlap transitivity
- [ ] 6.2.3 Write property test for confidence level monotonicity
- [ ] 6.2.4 Write property test for context assembly idempotence
- [ ] 6.2.5 Write property test for semantic deduplication consistency
- [ ] 6.2.6 Run property tests with 1000+ generated examples

### 6.3 Integration Testing
- [ ] 6.3.1 Write end-to-end test for perception pipeline
- [ ] 6.3.2 Write end-to-end test for context assembly
- [ ] 6.3.3 Write end-to-end test for action execution with bounding boxes
- [ ] 6.3.4 Write end-to-end test for degradation modes
- [ ] 6.3.5 Write end-to-end test for full perception cycle latency
- [ ] 6.3.6 Run integration tests on real Windows environment

### 6.4 Performance Benchmarking
- [ ] 6.4.1 Benchmark OmniParser inference latency (CPU and GPU)
- [ ] 6.4.2 Benchmark UIA tree extraction latency
- [ ] 6.4.3 Benchmark cross-modal comparison latency
- [ ] 6.4.4 Benchmark context assembly latency
- [ ] 6.4.5 Benchmark semantic deduplication latency
- [ ] 6.4.6 Benchmark end-to-end perception cycle latency
- [ ] 6.4.7 Verify all latency targets are met (< 1s end-to-end)

### 6.5 Security Validation
- [ ] 6.5.1 Verify clipboard secret filtering works correctly
- [ ] 6.5.2 Verify browser URL hashing works correctly
- [ ] 6.5.3 Verify UIA password field redaction works correctly
- [ ] 6.5.4 Verify file path filtering excludes system directories
- [ ] 6.5.5 Verify zero API calls during perception and reasoning
- [ ] 6.5.6 Run security audit on new components

## Phase 7: Documentation and Deployment

### 7.1 Documentation
- [ ] 7.1.1 Update docs/ARCHITECTURE.md with verified perception layer
- [ ] 7.1.2 Update docs/ARIA_ARCHITECTURE.md with new components
- [ ] 7.1.3 Create docs/VERIFIED_PERCEPTION.md with detailed design
- [ ] 7.1.4 Update README.md with new features and configuration
- [ ] 7.1.5 Create migration guide for existing users
- [ ] 7.1.6 Create troubleshooting guide for common issues
- [ ] 7.1.7 Update API documentation for new interfaces

### 7.2 Deployment Preparation
- [ ] 7.2.1 Create model download and setup script
- [ ] 7.2.2 Update installation instructions for new dependencies
- [ ] 7.2.3 Create system requirements validation script
- [ ] 7.2.4 Update .env.example with all new configuration keys
- [ ] 7.2.5 Create quick start guide for verified perception layer
- [ ] 7.2.6 Test installation on clean Windows 10 and Windows 11 systems

### 7.3 Backward Compatibility Verification
- [ ] 7.3.1 Verify existing action types continue to work
- [ ] 7.3.2 Verify existing memory and persona systems unaffected
- [ ] 7.3.3 Verify existing voice output continues to function
- [ ] 7.3.4 Verify existing audit logging format preserved
- [ ] 7.3.5 Run existing test suite and verify all tests pass
- [ ] 7.3.6 Test with existing .env configurations

## Phase 8: Optimization and Polish

### 8.1 Performance Optimization
- [ ] 8.1.1 Optimize OmniParser frame preprocessing (downsampling, caching)
- [ ] 8.1.2 Optimize UIA tree caching strategy
- [ ] 8.1.3 Optimize cross-modal comparison with spatial indexing
- [ ] 8.1.4 Optimize context serialization for token efficiency
- [ ] 8.1.5 Optimize semantic dedup embedding computation (batching)
- [ ] 8.1.6 Profile memory usage and fix any leaks
- [ ] 8.1.7 Verify 24-hour continuous operation stability

### 8.2 Error Handling and Logging
- [ ] 8.2.1 Add comprehensive error logging for all components
- [ ] 8.2.2 Add degradation mode logging to audit trail
- [ ] 8.2.3 Add performance metrics logging (latency, throughput)
- [ ] 8.2.4 Add model load success/failure logging
- [ ] 8.2.5 Add perception confidence distribution logging
- [ ] 8.2.6 Create diagnostic script for troubleshooting

### 8.3 User Experience
- [ ] 8.3.1 Add startup validation for required models
- [ ] 8.3.2 Add helpful error messages for common issues
- [ ] 8.3.3 Add progress indicators for model downloads
- [ ] 8.3.4 Add configuration validation with clear error messages
- [ ] 8.3.5 Add opt-out flags for privacy-sensitive features
- [ ] 8.3.6 Create user-friendly setup wizard (optional)

## Summary

Total tasks: 150+
Estimated effort: 8-10 weeks for full implementation
Critical path: Phase 1 → Phase 3 → Phase 5 → Phase 6
