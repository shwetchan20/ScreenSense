import sys
import json
import asyncio
import ctypes
import threading
from PySide6.QtCore import (
    Qt,
    QTimer,
    QThread,
    Signal,
    QPropertyAnimation,
    QRect,
    Property,
    QEasingCurve,
    QPointF,
    QAbstractNativeEventFilter,
)
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QRadialGradient, QConicalGradient, QIcon, QAction, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QSystemTrayIcon,
    QMenu,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QFrame,
)
import websockets

from screensense.config import load_settings
from screensense.integrations.voice import VoiceInput

class WsThread(QThread):
    state_changed = Signal(str, str) # status, text
    chat_context = Signal(dict, list)
    chat_chunk = Signal(str)
    chat_done = Signal(str)
    chat_error = Signal(str)
    
    def __init__(self, uri="ws://localhost:8765"):
        super().__init__()
        self.uri = uri
        self._loop = None
        self._send_queue = None
        
    def run(self):
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.listen())
        
    async def listen(self):
        while True:
            try:
                async with websockets.connect(self.uri) as ws:
                    self.state_changed.emit("Connected", "")
                    self._send_queue = asyncio.Queue()
                    sender = asyncio.create_task(self._sender(ws))
                    async for message in ws:
                        data = json.loads(message)
                        msg_type = str(data.get("type") or "")
                        if msg_type == "chat_context":
                            self.chat_context.emit(data.get("context", {}), data.get("history", []))
                        elif msg_type == "chat_chunk":
                            self.chat_chunk.emit(str(data.get("delta", "")))
                        elif msg_type == "chat_done":
                            self.chat_done.emit(str(data.get("response", "")))
                        elif msg_type == "chat_error":
                            self.chat_error.emit(str(data.get("error", "")))
                        elif "status" in data:
                            self.state_changed.emit(data.get("status", "Idle"), data.get("text", ""))
                    sender.cancel()
            except Exception:
                self.state_changed.emit("Disconnected", "Waiting for ScreenSense...")
                await asyncio.sleep(2)

    async def _sender(self, ws):
        if self._send_queue is None:
            return
        while True:
            payload = await self._send_queue.get()
            await ws.send(payload)

    def send_json(self, payload: dict):
        if self._loop is None or self._send_queue is None:
            return
        message = json.dumps(payload)
        self._loop.call_soon_threadsafe(self._send_queue.put_nowait, message)


class ChatPanel(QWidget):
    def __init__(self, ws_thread: WsThread, voice_input: VoiceInput):
        super().__init__()
        self._ws = ws_thread
        self._voice_input = voice_input
        self._history: list[dict[str, str]] = []
        self._stream_buffer = ""

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen().availableGeometry()
        width = 420
        height = 520
        self.setGeometry(screen.width() - width - 60, screen.height() - height - 120, width, height)

        container = QFrame(self)
        container.setStyleSheet(
            "QFrame { background: rgba(8, 13, 26, 230); border: 1px solid rgba(0,200,255,60);"
            " border-radius: 14px; }"
        )
        container.setGeometry(0, 0, width, height)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_label = QLabel("ARIA Chat")
        header_label.setStyleSheet("color: rgba(224,247,255,0.9); font-size: 12px;")
        header_row.addWidget(header_label)
        header_row.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.05); color: rgba(224,247,255,0.7); "
            "border: 1px solid rgba(0,200,255,40); border-radius: 12px; }"
            "QPushButton:hover { background: rgba(255,59,59,0.15); color: #ff6b6b; "
            "border-color: rgba(255,59,59,120); }"
        )
        close_btn.clicked.connect(self.close_panel)
        header_row.addWidget(close_btn)
        layout.addLayout(header_row)

        self.context_label = QLabel("Context: waiting...")
        self.context_label.setStyleSheet("color: rgba(224,247,255,0.6); font-size: 11px;")
        self.context_label.setWordWrap(True)
        layout.addWidget(self.context_label)

        self.history_view = QTextEdit()
        self.history_view.setReadOnly(True)
        self.history_view.setStyleSheet(
            "QTextEdit { background: rgba(5, 10, 20, 160); color: #e0f7ff; "
            "border: 1px solid rgba(0,200,255,40); border-radius: 10px; padding: 8px; }"
        )
        layout.addWidget(self.history_view, 1)

        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask ARIA...")
        self.input.setStyleSheet(
            "QLineEdit { background: rgba(5, 10, 20, 180); color: #e0f7ff; "
            "border: 1px solid rgba(0,200,255,60); border-radius: 10px; padding: 8px; }"
        )
        self.input.returnPressed.connect(self._send_question)
        input_row.addWidget(self.input, 1)

        self.mic_button = QPushButton("Mic")
        self.mic_button.setStyleSheet(
            "QPushButton { background: rgba(0,200,255,40); color: #e0f7ff; "
            "border: 1px solid rgba(0,200,255,80); border-radius: 8px; padding: 6px 10px; }"
        )
        self.mic_button.clicked.connect(self._listen_voice)
        input_row.addWidget(self.mic_button)

        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet(
            "QPushButton { background: rgba(0,200,255,70); color: #e0f7ff; "
            "border: 1px solid rgba(0,200,255,120); border-radius: 8px; padding: 6px 12px; }"
        )
        self.send_button.clicked.connect(self._send_question)
        input_row.addWidget(self.send_button)

        layout.addLayout(input_row)

    def open_panel(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self._ws.send_json({"type": "chat_open"})

    def close_panel(self):
        self.hide()
        self._ws.send_json({"type": "chat_close"})

    def toggle_panel(self):
        if self.isVisible():
            self.close_panel()
        else:
            self.open_panel()

    def set_context(self, context: dict, history: list):
        title = context.get("window_title") or "Unknown"
        app = context.get("active_app") or "Unknown app"
        goal = context.get("goal") or "No goal set"
        excerpt = context.get("ui_text_excerpt") or ""
        context_text = f"App: {app} | Title: {title}\nGoal: {goal}\nScreen: {excerpt}"
        self.context_label.setText(context_text)
        self._history = [
            {"role": item.get("role", ""), "content": item.get("content", "")}
            for item in history[-10:]
        ]
        self._render_history()

    def append_stream_chunk(self, delta: str):
        if not delta:
            return
        if not self._stream_buffer:
            self._history.append({"role": "assistant", "content": ""})
        self._stream_buffer += delta
        self._history[-1]["content"] = self._stream_buffer
        self._trim_history()
        self._render_history()

    def finalize_stream(self, full: str):
        if self._stream_buffer:
            self._history[-1]["content"] = full
        else:
            self._history.append({"role": "assistant", "content": full})
        self._stream_buffer = ""
        self._trim_history()
        self._render_history()
        self.input.setEnabled(True)
        self.send_button.setEnabled(True)

    def show_error(self, error: str):
        self._history.append({"role": "system", "content": f"Error: {error}"})
        self._trim_history()
        self._render_history()
        self.input.setEnabled(True)
        self.send_button.setEnabled(True)

    def _send_question(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._history.append({"role": "user", "content": text})
        self._trim_history()
        self._render_history()
        self._stream_buffer = ""
        self.input.setEnabled(False)
        self.send_button.setEnabled(False)
        self._ws.send_json({"type": "chat_request", "question": text})

    def _listen_voice(self):
        if not self._voice_input.available:
            self.show_error("Voice input not available.")
            return
        self.input.setText("Listening...")
        self.repaint()
        text = self._voice_input.listen_text()
        self.input.clear()
        if text:
            self.input.setText(text)
            self._send_question()

    def _trim_history(self):
        if len(self._history) > 10:
            self._history = self._history[-10:]

    def _render_history(self):
        lines = []
        for item in self._history:
            role = item.get("role", "")
            content = item.get("content", "")
            if role == "user":
                lines.append(f"You: {content}")
            elif role == "assistant":
                lines.append(f"ARIA: {content}")
            else:
                lines.append(content)
        self.history_view.setPlainText("\n\n".join(lines))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_panel()
            event.accept()
            return
        super().keyPressEvent(event)


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, eventType, message):
        if eventType != "windows_generic_MSG":
            return False, 0
        msg = ctypes.wintypes.MSG.from_address(message.__int__())
        if msg.message == 0x0312 and msg.wParam == 1:
            self._callback()
            return True, 0
        return False, 0

class OrbWidget(QWidget):
    def __init__(self, chat_panel: ChatPanel, ws_thread: WsThread):
        super().__init__()
        self._chat_panel = chat_panel
        self._ws_thread = ws_thread
        self._focus_mode = False
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.state = "Disconnected"
        
        # Position in the bottom right corner as requested
        screen = QApplication.primaryScreen().availableGeometry()
        self.size = 200
        self.setGeometry(screen.width() - self.size - 50, screen.height() - self.size - 100, self.size, self.size + 50)
        
        self._pulse_scale = 1.0
        self._rotation_angle = 0.0
        
        # Create analyze button below orb
        self.analyze_btn = QPushButton("🔍 Analyze", self)
        self.analyze_btn.setGeometry(25, self.size + 5, 150, 40)
        self.analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 100, 255, 180);
                color: white;
                border: 2px solid rgba(150, 150, 255, 200);
                border-radius: 20px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: rgba(120, 120, 255, 220);
                border: 2px solid rgba(180, 180, 255, 255);
            }
            QPushButton:pressed {
                background-color: rgba(80, 80, 200, 200);
            }
        """)
        self.analyze_btn.clicked.connect(self._trigger_analyze)
        self.analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Animation for pulsing
        self.pulse_anim = QPropertyAnimation(self, b"pulseScale")
        self.pulse_anim.setLoopCount(-1)
        self.pulse_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        # Continuous rotation timer for the conical gradient
        self.rotation_timer = QTimer(self)
        self.rotation_timer.timeout.connect(self.update_rotation)
        self.rotation_speed = 2.0
        self.rotation_timer.start(16)
        
        # WS is managed by caller
        self._ws_thread.state_changed.connect(self.update_state)
        
        # Kick off default animation
        self.update_state("Idle", "")

    def get_pulse_scale(self):
        return self._pulse_scale

    def set_pulse_scale(self, scale):
        self._pulse_scale = scale
        self.update()

    pulseScale = Property(float, get_pulse_scale, set_pulse_scale)

    def update_rotation(self):
        self._rotation_angle = (self._rotation_angle + self.rotation_speed) % 360
        self.update()

    def update_state(self, status, text):
        if self.state != status or self.pulse_anim.state() != QPropertyAnimation.State.Running:
            self.state = status
            self.pulse_anim.stop()
            
            if status == "Idle" or status == "Connected":
                self.pulse_anim.setStartValue(0.95)
                self.pulse_anim.setEndValue(1.03)
                self.pulse_anim.setDuration(2500)
                self.rotation_speed = 1.5
            elif status == "Analyzing":
                self.pulse_anim.setStartValue(0.9)
                self.pulse_anim.setEndValue(1.15)
                self.pulse_anim.setDuration(800)
                self.rotation_speed = 6.0
            elif status == "Speaking":
                # Quick jump pulse
                self.pulse_anim.setStartValue(0.85)
                self.pulse_anim.setEndValue(1.25)
                self.pulse_anim.setDuration(400)
                self.rotation_speed = 4.0
            else:
                self.pulse_anim.setStartValue(1.0)
                self.pulse_anim.setEndValue(1.0)
                self.pulse_anim.setDuration(1000)
                self.rotation_speed = 0.5
                
            self.pulse_anim.start()

    def get_colors_for_state(self):
        # A mix of colors to resemble Astra UI
        if self.state == "Idle" or self.state == "Connected":
            # Glassy blue/purple
            return (
                QColor(10, 15, 30, 160), 
                QColor(66, 133, 244, 255),  # Blue
                QColor(165, 114, 223, 255), # Purple
                QColor(66, 133, 244, 180) 
            )
        elif self.state == "Analyzing":
            # Fast orange/pink processing
            return (
                QColor(30, 10, 10, 180), 
                QColor(255, 100, 50, 255),
                QColor(255, 50, 150, 255),
                QColor(255, 150, 50, 180)
            )
        elif self.state == "Speaking":
            # Vivid green/cyan
            return (
                QColor(10, 30, 25, 180), 
                QColor(50, 255, 150, 255),
                QColor(50, 150, 255, 255),
                QColor(100, 255, 200, 180)
            )
        else: # Disconnected
            return (
                QColor(30, 30, 30, 100),
                QColor(100, 100, 100, 100),
                QColor(150, 150, 150, 100),
                QColor(80, 80, 80, 50)
            )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center = QPointF(self.width() / 2, self.height() / 2)
        base_radius = 45
        animated_radius = base_radius * self._pulse_scale
        
        core_c, edge1_c, edge2_c, edge3_c = self.get_colors_for_state()
        
        # Outer soft ambient glow
        glow_radius = animated_radius * 1.8
        glow_grad = QRadialGradient(center, glow_radius)
        glow_grad.setColorAt(0, QColor(edge1_c.red(), edge1_c.green(), edge1_c.blue(), 100))
        glow_grad.setColorAt(0.5, QColor(edge1_c.red(), edge1_c.green(), edge1_c.blue(), 30))
        glow_grad.setColorAt(1, QColor(0, 0, 0, 0))
        
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, glow_radius, glow_radius)
        
        # Rotating Conical Bezel (The shiny, animated ring)
        ring_thickness = 10 * self._pulse_scale
        outer_radius = animated_radius + ring_thickness
        inner_radius = animated_radius
        
        conical_grad = QConicalGradient(center, self._rotation_angle)
        conical_grad.setColorAt(0.0, edge1_c)
        conical_grad.setColorAt(0.3, edge2_c)
        conical_grad.setColorAt(0.5, edge1_c)
        conical_grad.setColorAt(0.8, edge3_c)
        conical_grad.setColorAt(1.0, edge1_c)
        
        painter.setBrush(QBrush(conical_grad))
        painter.drawEllipse(center, outer_radius, outer_radius)
        
        # Re-cover the inner area to create a "donut" or glassy center
        core_grad = QRadialGradient(center, inner_radius)
        core_grad.setColorAt(0, core_c)
        core_grad.setColorAt(0.85, QColor(core_c.red(), core_c.green(), core_c.blue(), 230))
        core_grad.setColorAt(1.0, QColor(255, 255, 255, 80)) # inner glass reflection rim
        
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(center, inner_radius, inner_radius)

    def mousePressEvent(self, event):
        self.oldPos = event.globalPosition().toPoint()
        self._dragged = False

    def mouseMoveEvent(self, event):
        delta = event.globalPosition().toPoint() - self.oldPos
        if delta.manhattanLength() > 4:
            self._dragged = True
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if not getattr(self, "_dragged", False):
            if event.button() == Qt.MouseButton.LeftButton:
                self._chat_panel.toggle_panel()

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        close_chat = QAction("Close chat")
        close_chat.triggered.connect(self._chat_panel.close_panel)
        menu.addAction(close_chat)

        focus_mode = QAction("Focus mode")
        focus_mode.setCheckable(True)
        focus_mode.setChecked(self._focus_mode)

        def _toggle_focus():
            self._focus_mode = not self._focus_mode
            self._ws_thread.send_json({"type": "focus_mode", "enabled": self._focus_mode})

        focus_mode.triggered.connect(_toggle_focus)
        menu.addAction(focus_mode)

        settings_action = QAction("Settings")
        settings_action.triggered.connect(lambda: None)
        menu.addAction(settings_action)

        exit_action = QAction("Exit ARIA")

        def _exit():
            self._ws_thread.send_json({"type": "app_shutdown"})

        exit_action.triggered.connect(_exit)
        menu.addAction(exit_action)

        menu.exec(event.globalPos())
    
    def _trigger_analyze(self):
        """Trigger manual analysis"""
        self._ws_thread.send_json({"type": "manual_analyze"})
        self.analyze_btn.setText("⏳ Analyzing...")
        self.analyze_btn.setEnabled(False)
        # Re-enable after 3 seconds
        QTimer.singleShot(3000, lambda: (
            self.analyze_btn.setText("🔍 Analyze"),
            self.analyze_btn.setEnabled(True)
        ))

def run_overlay(shutdown_event: threading.Event | None = None) -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    settings = load_settings()
    voice_input = VoiceInput(enabled=settings.enable_voice_input)

    ws_thread = WsThread()
    ws_thread.start()

    chat_panel = ChatPanel(ws_thread, voice_input)
    ws_thread.chat_context.connect(chat_panel.set_context)
    ws_thread.chat_chunk.connect(chat_panel.append_stream_chunk)
    ws_thread.chat_done.connect(chat_panel.finalize_stream)
    ws_thread.chat_error.connect(chat_panel.show_error)

    orb = OrbWidget(chat_panel, ws_thread)
    
    tray_icon = QSystemTrayIcon(app)
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    tray_icon.setIcon(QIcon(pixmap))
    
    menu = QMenu()
    quit_action = QAction("Quit ScreenSense UI")
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray_icon.setContextMenu(menu)
    tray_icon.show()

    user32 = ctypes.windll.user32
    MOD_CONTROL = 0x0002
    VK_SPACE = 0x20
    user32.RegisterHotKey(None, 1, MOD_CONTROL, VK_SPACE)
    hotkey_filter = HotkeyFilter(chat_panel.toggle_panel)
    app.installNativeEventFilter(hotkey_filter)
    app.aboutToQuit.connect(lambda: user32.UnregisterHotKey(None, 1))

    if shutdown_event is not None:
        def _poll_shutdown():
            if shutdown_event.is_set():
                app.quit()

        shutdown_timer = QTimer()
        shutdown_timer.timeout.connect(_poll_shutdown)
        shutdown_timer.start(200)
    
    orb.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_overlay()
