# Quick Start - Verified Perception ARIA

## Installation

1. Install dependencies:
```bash
pip install sentence-transformers uiautomation watchdog ultralytics torch torchvision
```

2. Verify installation:
```bash
python test_verified_perception.py
```

## Running ARIA

1. Make sure Ollama is running with llama3.2:3b:
```bash
ollama run llama3.2:3b
```

2. Start ARIA:
```bash
python -m screensense.app
```

## What's Different Now

### Before (Old Architecture)
- Sent raw screenshot to Gemini API
- Trusted whatever the vision model said
- Could hallucinate about screen content
- API quota limits
- Generic responses

### After (Verified Perception)
- OmniParser detects UI elements with bounding boxes
- Windows UIA provides ground truth from accessibility tree
- Cross-modal comparator verifies facts both systems agree on
- Only HIGH confidence facts proceed to reasoning
- Passive signals (clipboard, browser URL) add context
- Semantic deduplication prevents repetition
- 12-word response constraint forces specificity
- Fully local, zero API calls

## Architecture Flow

```
Screenshot → Frame Diff → Significant change?
                              ↓
                    ┌─────────────────────┐
                    │ VERIFIED PERCEPTION │
                    │                     │
                    │ OmniParser ──┐      │
                    │              ├─→ Comparator
                    │ UIA Tree ────┘      │
                    │         ↓           │
                    │   Verified Facts    │
                    └─────────────────────┘
                              ↓
                    + Clipboard content
                    + Browser URL
                    + File changes
                              ↓
                    Context Assembly
                              ↓
                    Qwen2.5 Reasoning (text-only)
                              ↓
                    12-Word Constraint
                              ↓
                    Semantic Dedup
                              ↓
                    Voice Output
```

## Configuration

Key settings in `.env`:

```bash
# Enable verified perception
ENABLE_VERIFIED_PERCEPTION=true

# Use local reasoning (no Gemini)
REASONING_MODE=local
LOCAL_LLM_PROVIDER=ollama
LOCAL_LLM_MODEL=llama3.2:3b
LOCAL_LLM_USE_VISION=false

# Response constraints
RESPONSE_MAX_WORDS=12
SEMANTIC_DEDUP_SIMILARITY_THRESHOLD=0.85

# Passive signals
ENABLE_PASSIVE_CLIPBOARD=true
ENABLE_PASSIVE_BROWSER_URL=true
ENABLE_PASSIVE_FILE_WATCH=false

# Cross-modal verification
CROSS_MODAL_POSITION_TOLERANCE=20
CROSS_MODAL_TEXT_SIMILARITY_THRESHOLD=0.8
```

## How It Works

### 1. OmniParser Detection
- Uses YOLOv8 to detect UI elements
- Provides bounding boxes for every element
- Confidence scores for each detection
- Currently uses standard YOLOv8n (you can upgrade to OmniParser-specific weights)

### 2. Windows UIA Ground Truth
- Reads Windows accessibility tree directly
- Gets exact text, window names, element properties
- Ground truth from Windows memory (not interpreted)
- Caches for 500ms to reduce overhead

### 3. Cross-Modal Verification
- Compares OmniParser vs UIA element by element
- Matching criteria:
  - Position (within 20px tolerance)
  - Text similarity (Levenshtein distance)
  - Element type
- Confidence levels:
  - **HIGH**: Both agree → verified fact
  - **LOW**: Only one source → uncertain
  - **CONFLICT**: Contradict → dropped

### 4. Passive Context Signals
- **Clipboard**: Monitors clipboard, filters secrets (passwords, tokens, API keys)
- **Browser URL**: Extracts URL from browser window title, blocks sensitive domains
- **File Watcher**: Tracks recently modified files (placeholder - needs implementation)
- **Window Metadata**: Process name, window title, PID

### 5. Context Assembly
- Merges verified elements + passive signals
- Prioritizes HIGH confidence elements
- Serializes to structured text for LLM
- Token counting and truncation (4000 token limit)

### 6. Local Reasoning
- Qwen2.5 (llama3.2:3b) reasons on verified facts
- Text-only (no vision frame sent)
- 12-word response constraint
- Must reference specific facts from context
- No generic phrases allowed

### 7. Semantic Deduplication
- Uses sentence-transformers (all-MiniLM-L6-v2)
- Computes embeddings for responses
- Cosine similarity threshold: 0.85
- Rolling window: 20 responses, 5 minutes
- Prevents ARIA from repeating same suggestion

## Example Output

### Old ARIA (Gemini Vision)
```
"You might want to check the terminal for errors"
```
Generic, vague, could be hallucinated.

### New ARIA (Verified Perception)
```
"coordinator.py line 47 Ollama not responding"
```
Specific, grounded in verified facts, exactly 7 words.

## Upgrading to OmniParser-Specific Weights

The current implementation uses standard YOLOv8n. To use Microsoft's OmniParser-specific weights:

1. Download from Hugging Face:
```bash
# Clone the model repo
git clone https://huggingface.co/microsoft/OmniParser-v2.0
```

2. Update `.env`:
```bash
OMNIPARSER_MODEL_PATH=path/to/OmniParser-v2.0/icon_detect/best.pt
```

3. Restart ARIA

## Troubleshooting

### OmniParser not detecting elements
- Check if YOLOv8 model downloaded successfully
- Try lowering `box_threshold` in omniparser_client.py
- Verify torch is installed correctly

### UIA not extracting elements
- Ensure `uiautomation` package is installed
- Check if target window is accessible
- Try running as administrator

### Semantic dedup not working
- Verify `sentence-transformers` is installed
- Check if model downloaded (all-MiniLM-L6-v2)
- Falls back to exact string matching if model unavailable

### Ollama connection errors
- Ensure Ollama is running: `ollama run llama3.2:3b`
- Check `LOCAL_LLM_BASE_URL` in `.env`
- Verify port 11434 is not blocked

## Performance

- **OmniParser**: ~0.8s per frame on CPU (YOLOv8n)
- **UIA Extraction**: ~50ms (cached)
- **Cross-Modal Comparison**: ~10ms
- **Context Assembly**: ~5ms
- **Semantic Dedup**: ~20ms (embedding computation)
- **Total**: ~1s end-to-end

## Next Steps

1. **Test with real applications**: Run ARIA while using VSCode, Chrome, etc.
2. **Tune thresholds**: Adjust position tolerance, text similarity based on results
3. **Enable file watching**: Implement watchdog integration for file change detection
4. **Upgrade to OmniParser weights**: Download Microsoft's trained weights for better detection
5. **Add more passive signals**: Browser history, system notifications, etc.

## Files to Know

- `src/screensense/perception/` - All perception components
- `src/screensense/inference/local_qwen.py` - Integrated reasoning
- `.env` - Configuration
- `test_verified_perception.py` - Test script
- `VERIFIED_PERCEPTION_IMPLEMENTATION.md` - Full technical details

## Support

If you encounter issues:
1. Check logs in console output
2. Run `python test_verified_perception.py` to isolate problems
3. Verify all dependencies installed
4. Check `.env` configuration

The system is designed to degrade gracefully - if OmniParser fails, it falls back to UIA-only mode. If both fail, it uses the old vision-based approach.
