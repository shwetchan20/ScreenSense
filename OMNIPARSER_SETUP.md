# OmniParser Setup Guide

## Current Status

OmniParser is using **YOLOv8n** (general object detection) which works but isn't trained specifically for UI elements.

## Why It Still Works

- **Windows UIA** provides the ground truth (text, buttons, inputs)
- **YOLOv8n** can detect some visual elements (icons, images)
- **Cross-modal verification** ensures accuracy
- System works well with **UIA-only mode**

## Performance

### With YOLOv8n (Current)
```
[LocalQwen] OmniParser detected 0-5 elements  # General objects
[LocalQwen] UIA extracted 25 elements          # UI ground truth
[LocalQwen] Verified 25 elements (HIGH: 0, LOW: 25)
```

### With OmniParser Weights (Ideal)
```
[LocalQwen] OmniParser detected 15-30 elements  # UI-specific
[LocalQwen] UIA extracted 25 elements
[LocalQwen] Verified 35 elements (HIGH: 20, LOW: 15)
```

## How to Get OmniParser Weights

### Option 1: Manual Download (Recommended)

1. **Visit the Hugging Face Space**:
   https://huggingface.co/spaces/microsoft/OmniParser

2. **Clone the repository**:
   ```bash
   git lfs install
   git clone https://huggingface.co/spaces/microsoft/OmniParser
   ```

3. **Copy the weights**:
   ```bash
   mkdir -p weights/omniparser
   cp OmniParser/weights/icon_detect/best.pt weights/omniparser/
   ```

4. **Update .env**:
   ```bash
   OMNIPARSER_MODEL_PATH=weights/omniparser/best.pt
   ```

5. **Restart ARIA**:
   ```bash
   python -m screensense.app
   ```

### Option 2: Use GitHub Repository

1. **Clone OmniParser GitHub**:
   ```bash
   git clone https://github.com/microsoft/OmniParser
   cd OmniParser
   ```

2. **Follow their setup instructions** to download weights

3. **Copy to your project**:
   ```bash
   cp weights/icon_detect/best.pt /path/to/screensense/weights/omniparser/
   ```

### Option 3: Keep Using YOLOv8n (Current)

The system works fine with YOLOv8n + UIA. You get:
- ✅ Accurate UI element detection (via UIA)
- ✅ Text extraction
- ✅ Bounding boxes
- ✅ Cross-modal verification
- ⚠️ Less visual icon detection

## What You're Missing Without OmniParser Weights

- **Icon detection**: Toolbar icons, status icons
- **Visual elements**: Images, graphics, charts
- **Custom UI**: Non-standard controls

## What You Still Get (UIA Alone)

- ✅ All text content
- ✅ Buttons, inputs, dropdowns
- ✅ Links, checkboxes, radio buttons
- ✅ Window titles, labels
- ✅ Exact bounding boxes
- ✅ Element states (enabled/disabled)

## Recommendation

**For now, keep using YOLOv8n + UIA**. The system works well and provides accurate context. If you need better icon detection later, follow Option 1 to get the trained weights.

## Testing

Run ARIA and check the logs:
```bash
python -m screensense.app
```

Look for:
```
[OmniParser] Initialized successfully
[LocalQwen] UIA extracted 25 elements  ← This is what matters most
[LocalQwen] Verified 25 elements
```

If UIA is extracting elements (> 0), the system is working! 🎉

## License Note

OmniParser icon_detect model is under **AGPL license**. Make sure you comply with the license terms if you download and use the trained weights.
