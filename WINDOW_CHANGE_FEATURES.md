# Window Change Auto-Analysis & Manual Analyze Button

## Features Implemented

### 1. ✅ Auto-Analysis on Window Change
**What it does**: When you switch windows/apps, ARIA waits 6 seconds then automatically analyzes the new screen and gives voice output.

**How it works**:
- Detects when window title or active app changes
- Starts 6-second timer
- After 6 seconds, forces analysis with verified perception
- Speaks the analysis result

**Console output**:
```
[ScreenSense] Window changed to: chrome.exe - Google Chrome
[ScreenSense] Auto-analyzing after window change (6.1s)
[LocalQwen] OmniParser detected 15 elements
[LocalQwen] UIA extracted 23 elements
[LocalQwen] Verified 18 elements (HIGH: 12, LOW: 6)
```

### 2. ✅ Manual Analyze Button
**What it does**: Blue button below the orb that triggers immediate analysis on demand.

**Location**: Below the ARIA orb in bottom-right corner

**Appearance**:
- Blue button with 🔍 icon
- Text: "Analyze"
- Hover effect (lighter blue)
- Click feedback (darker blue)

**Behavior**:
- Click button → Triggers immediate analysis
- Button changes to "⏳ Analyzing..." and disables
- After 3 seconds, re-enables as "🔍 Analyze"
- Analysis runs through full verified perception pipeline
- Voice output with results

## Technical Details

### Coordinator Changes (`src/screensense/core/coordinator.py`)

**Added tracking variables**:
```python
self._last_window_title = ""
self._last_active_app = ""
self._window_change_ts = 0.0
self._window_change_delay = 6.0  # 6 seconds
self._manual_analyze_requested = False
```

**Window change detection in _tick()**:
```python
window_changed = (
    current_window != self._last_window_title or 
    current_app != self._last_active_app
)

if window_changed:
    self._window_change_ts = time.time()
    print(f"[ScreenSense] Window changed to: {current_app} - {current_window}")
```

**Auto-analysis trigger**:
```python
if elapsed_since_change >= self._window_change_delay:
    force_window_analysis = True
    print(f"[ScreenSense] Auto-analyzing after window change ({elapsed_since_change:.1f}s)")
```

**IPC command handler**:
```python
elif msg_type == "manual_analyze":
    self._manual_analyze_requested = True
    await websocket.send(json.dumps({"type": "analyze_triggered"}))
```

### UI Changes (`src/screensense/ui/orb_overlay.py`)

**Analyze button**:
```python
self.analyze_btn = QPushButton("🔍 Analyze", self)
self.analyze_btn.setGeometry(25, self.size + 5, 150, 40)
self.analyze_btn.clicked.connect(self._trigger_analyze)
```

**Trigger method**:
```python
def _trigger_analyze(self):
    self._ws_thread.send_json({"type": "manual_analyze"})
    self.analyze_btn.setText("⏳ Analyzing...")
    self.analyze_btn.setEnabled(False)
    QTimer.singleShot(3000, lambda: (
        self.analyze_btn.setText("🔍 Analyze"),
        self.analyze_btn.setEnabled(True)
    ))
```

## Usage

### Auto-Analysis
1. Switch to a new window/app
2. Wait 6 seconds
3. ARIA automatically analyzes and speaks

### Manual Analysis
1. Click the "🔍 Analyze" button below the orb
2. Button shows "⏳ Analyzing..."
3. ARIA analyzes current screen immediately
4. Voice output with results
5. Button re-enables after 3 seconds

## Configuration

You can adjust the delay in `.env`:
```bash
# Not yet exposed, but you can modify in code:
# src/screensense/core/coordinator.py line ~268
self._window_change_delay = 6.0  # Change to 5.0 or 7.0
```

## What Gets Analyzed

Both features use the full verified perception pipeline:
1. OmniParser detects UI elements
2. Windows UIA extracts ground truth
3. Cross-modal comparator verifies facts
4. Passive signals (clipboard, browser URL)
5. Context assembly
6. Qwen2.5 reasoning
7. Voice output

## Example Scenarios

**Scenario 1: Switch to VSCode**
```
[ScreenSense] Window changed to: Code.exe - coordinator.py
[ScreenSense] Auto-analyzing after window change (6.0s)
[LocalQwen] Verified 25 elements (HIGH: 18, LOW: 7)
ARIA: "You're editing coordinator.py in VSCode. I notice there's a syntax error on line 47 - missing closing parenthesis. The terminal shows a Python traceback."
```

**Scenario 2: Click Analyze Button**
```
[ScreenSense] Manual analyze requested
[LocalQwen] Verified 12 elements (HIGH: 9, LOW: 3)
ARIA: "Chrome is showing Google Search results for 'OmniParser'. You have 5 tabs open. The clipboard contains a GitHub URL."
```

## Benefits

1. **Proactive**: ARIA automatically understands new contexts
2. **On-Demand**: Manual button for immediate analysis
3. **Verified**: Uses full cross-modal verification
4. **Voice Feedback**: Always speaks the analysis
5. **Non-Intrusive**: 6-second delay prevents spam

## Testing

Run ARIA and try:
1. Switch between apps (VSCode → Chrome → Terminal)
2. Wait 6 seconds after each switch
3. Listen for voice output
4. Click the Analyze button for immediate feedback

You should see the blue button below the orb and hear ARIA speak after window changes!
