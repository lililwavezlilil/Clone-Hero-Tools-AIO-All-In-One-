import sys
import os
import traceback
import builtins
import io
import re
import multiprocessing

# ==========================================
# 0. GLOBAL SETTINGS (CHANGE THESE)
# ==========================================
ENABLE_DIRECTORY_SCROLL = True  # Set to False to disable scrolling
DIRECTORY_CHAR_LIMIT = 40       # Triggers scroll if path is longer than this limit
DIRECTORY_SCROLL_SPEED = 0.5    # Scroll speed multiplier (e.g. 0.5 is slower, 2.0 is faster)

# ==========================================
# 0. EARLY CRASH CATCHER & STREAM REPAIR
# ==========================================
def global_exception_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    
    with open("crash_log.txt", "w", encoding="utf-8") as f:
        f.write(err_msg)
        
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance():
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Fatal Error in GUI")
            msg.setText("An unexpected error occurred and the application must close:")
            msg.setDetailedText(err_msg)
            msg.exec()
    except Exception:
        pass

sys.excepthook = global_exception_handler

if sys.stdin is None:
    sys.stdin = io.StringIO()
    builtins.input = lambda *args, **kwargs: "" 

if sys.stdout is None:
    try:
        sys.stdout = open(1, 'w', encoding='utf-8', closefd=False)
    except Exception:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
        
if sys.stderr is None:
    try:
        sys.stderr = open(2, 'w', encoding='utf-8', closefd=False)
    except Exception:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# ==========================================
# 1. STANDARD IMPORTS
# ==========================================
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QWidget, QTextEdit, QLabel, QStyleOptionButton, 
                             QStyle, QSizePolicy, QToolTip, QDialog, QListWidget,
                             QFileDialog, QMessageBox, QStyleOption)
from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import (QFont, QPainter, QColor, QPen, QPainterPath, QTextCursor, 
                         QTextBlockFormat, QFontMetrics, QCursor, QIcon)

# ==========================================
# 2. BUNDLE IMPORTS
# ==========================================
import CloneHeroUniversalSongMatcher
import CloneHeroNoPartDeleter
import CloneHeroMidi2Chart
import CloneHeroDifficultyCreator
try:
    import CloneHeroChart2Midi
except ImportError:
    pass

# ==========================================
# 3. CUSTOM UI COMPONENTS
# ==========================================
class MarqueeLabel(QWidget):
    """A pixel-perfect, 60fps scrolling label that anchors the prefix text."""
    def __init__(self, parent=None, char_limit=25, enable_scroll=True):
        super().__init__(parent)
        self.char_limit = char_limit
        self.enable_scroll = enable_scroll
        self.static_prefix = "Current Directory: "
        self.path_text = "Not Set"
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #000000; color: #ffffff; border-radius: 4px; border: 1px solid #333;")
        
        self.custom_font = QFont("Arial", 9, QFont.Weight.Bold)
        self.setFont(self.custom_font)
        
        fm = QFontMetrics(self.custom_font)
        self.setFixedHeight(fm.height() + 12)
        
        self.scroll_pos = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_scroll)
        self.set_directory("Not Set")
        
    def set_directory(self, path):
        self.path_text = path
        fm = QFontMetrics(self.custom_font)
        static_width = fm.horizontalAdvance(self.static_prefix)
        
        # 1. Calculate actual pixel width of the path
        path_width = fm.horizontalAdvance(self.path_text)
        
        # 2. Calculate a realistic max width (using a standard character width instead of "W")
        max_dynamic_width = fm.horizontalAdvance("x" * self.char_limit)
        
        # 3. ONLY scroll if the text physically exceeds the max allowed width
        if not self.enable_scroll or path_width <= max_dynamic_width:
            self.timer.stop()
            self.scroll_pos = 0.0
            
            # Shrink the box to perfectly fit the short text
            self.setFixedWidth(static_width + path_width + 20) 
        else:
            self.scroll_pos = 0.0
            self.timer.start(16) # 16ms = ~60 FPS
            
            # Lock the box to the maximum allowed width
            self.setFixedWidth(static_width + max_dynamic_width + 20) 
            
        self.update() # Force repaint
            
    def update_scroll(self):
        self.scroll_pos += DIRECTORY_SCROLL_SPEED 
        
        fm = QFontMetrics(self.custom_font)
        path_width = fm.horizontalAdvance(self.path_text)
        spacing = 50 # Pixel gap between the end of text and start of the seamless loop
        
        if self.scroll_pos > path_width + spacing:
            self.scroll_pos = 0.0
            
        self.update()

    def paintEvent(self, event):
        # 1. Background rendering via stylesheet
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)
        
        # 2. Text Setup
        painter.setFont(self.custom_font)
        painter.setPen(QColor("#ffffff"))
        
        fm = QFontMetrics(self.custom_font)
        rect = self.rect()
        y = rect.y() + (rect.height() + fm.ascent() - fm.descent()) // 2
        
        # Explicit margins so text never touches the walls
        left_padding = 10
        right_padding = 10
        
        # 3. Draw the STATIC prefix with the left margin applied
        static_width = fm.horizontalAdvance(self.static_prefix)
        painter.drawText(rect.x() + left_padding, y, self.static_prefix)
        
        # 4. Create a clipping region so the scrolling path never overlaps the static text or the right edge
        scroll_rect = rect.adjusted(left_padding + static_width, 0, -right_padding, 0)
        painter.setClipRect(scroll_rect)
        
        path_width = fm.horizontalAdvance(self.path_text)
        
        # 5. Draw the DYNAMIC path text inside the clipped area
        if not self.timer.isActive():
            painter.drawText(scroll_rect.x(), y, self.path_text)
        else:
            # Shift the text left based on the scroll position
            x = scroll_rect.x() - int(self.scroll_pos)
            painter.drawText(x, y, self.path_text)
            
            # Draw the looping text trailing behind it
            spacing = 50
            second_x = x + path_width + spacing
            if second_x < scroll_rect.x() + scroll_rect.width():
                painter.drawText(second_x, y, self.path_text)
                
        painter.end()


class OutlinedButton(QPushButton):
    def __init__(self, text, stroke_width=2, parent=None):
        super().__init__(text, parent)
        self.stroke_width = stroke_width
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        self.setMouseTracking(True)
        
        self._tooltip_text = ""
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.show_custom_tooltip)

    def setToolTip(self, text):
        self._tooltip_text = text

    def show_custom_tooltip(self):
        if self._tooltip_text:
            QToolTip.showText(QCursor.pos(), self._tooltip_text, self)

    def enterEvent(self, event):
        if self._tooltip_text:
            self.hover_timer.start(1000)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_timer.stop()
        QToolTip.hideText()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        if self._tooltip_text:
            self.hover_timer.start(1000) 
        QToolTip.hideText() 
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        
        opt.text = "" 
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, painter, self)

        text = self.text()
        rect = self.contentsRect()
        
        font = self.font()
        pixel_size = max(10, int(rect.height() * 0.35))
        font.setPixelSize(pixel_size)
        fm = QFontMetrics(font)
        
        while fm.boundingRect(text).width() > rect.width() - 20 and pixel_size > 8:
            pixel_size -= 1
            font.setPixelSize(pixel_size)
            fm = QFontMetrics(font)
            
        text_rect = fm.boundingRect(text)
        
        x = rect.x() + (rect.width() - text_rect.width()) / 2
        y = rect.y() + (rect.height() + text_rect.height()) / 2 - fm.descent()
        
        path = QPainterPath()
        path.addText(x, y, font, text)
        
        if not self.isEnabled():
            outline_color = QColor("#252525")
            fill_color = QColor("#777777")
        else:
            outline_color = QColor("black")
            fill_color = QColor("white")

        painter.setPen(QPen(outline_color, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(outline_color)
        painter.drawPath(path)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_color)
        painter.drawPath(path)
            
        painter.end()


class HelpDialog(QDialog):
    def __init__(self, topic_name, text_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{topic_name} - Help")
        self.resize(800, 600) 
        self.setMinimumSize(400, 300) 
        
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | 
                            Qt.WindowType.WindowCloseButtonHint | 
                            Qt.WindowType.WindowMinimizeButtonHint | 
                            Qt.WindowType.WindowMaximizeButtonHint)
                            
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        
        layout = QVBoxLayout(self)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(text_content)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #0c0c0c;
                color: #cccccc;
                border: 1px solid #333333;
                padding: 10px;
            }
        """)
        layout.addWidget(self.text_edit)
        
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { 
                background-color: #388e3c; 
                border-radius: 3px; 
                padding: 8px 20px; 
                font-weight: bold;
                color: white;
            }
            QPushButton:hover { background-color: #4caf50; }
        """)
        close_btn.clicked.connect(self.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)

    def resizeEvent(self, event):
        new_pixel_size = max(10, int(self.height() * 0.025))
        
        font = QFont("Consolas")
        font.setPixelSize(new_pixel_size)
        self.text_edit.setFont(font)
        
        super().resizeEvent(event)


# ==========================================
# 4. THE ROUTER 
# ==========================================
if len(sys.argv) > 1 and sys.argv[1] == "--run-script":
    script_name = sys.argv[2]
    
    if script_name == "CloneHeroUniversalSongMatcher":
        CloneHeroUniversalSongMatcher.run()
    elif script_name == "CloneHeroNoPartDeleter":
        CloneHeroNoPartDeleter.run()
    elif script_name == "CloneHeroMidi2Chart":
        CloneHeroMidi2Chart.run()
    elif script_name == "CloneHeroDifficultyCreator":
        CloneHeroDifficultyCreator.run()
    elif script_name == "CloneHeroChart2Midi":
        if 'CloneHeroChart2Midi' in sys.modules:
            sys.modules['CloneHeroChart2Midi'].run()
        
    sys.exit(0)

# ==========================================
# 5. THE GUI 
# ==========================================
class CloneHeroToolSuite(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clone Hero Tools AIO (All-In-One)")
        self.setGeometry(100, 100, 1000, 650) 
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")

        self.active_process = None
        self.is_closing = False 
        
        # Track our last known directory to avoid unnecessary GUI updates
        self.last_known_dir = "Not Set"

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # --- CUSTOM HEADER LAYOUT (Using Grid to force true centering) ---
        header_layout = QGridLayout()
        
        # Left Title
        title_layout = QVBoxLayout()
        title_label = QLabel("Clone Hero Tools AIO (All-In-One)")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff;")
        
        author_label = QLabel("by WAVEZ")
        author_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        author_label.setStyleSheet("color: #aaaaaa;")
        
        title_layout.addWidget(title_label)
        title_layout.addWidget(author_label)
        title_layout.setSpacing(0)
        
        # Center Directory Tool
        center_layout = QHBoxLayout()
        center_layout.setSpacing(10)
        
        # Change Directory Button
        self.btn_change_dir = OutlinedButton("Change Directory", stroke_width=2)
        self.btn_change_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_dir.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.btn_change_dir.setMinimumSize(180, 36)
        self.btn_change_dir.setMaximumSize(250, 42)
        self.btn_change_dir.setStyleSheet("""
            QPushButton { 
                background-color: #1e1e1e;
                border: 2px solid #444444;
                border-top-color: #666666;
                border-left-color: #666666;
                border-radius: 3px; 
            }
            QPushButton:hover { 
                border: 2px solid #0078d7; 
            }
            QPushButton:pressed { 
                background-color: #151515;
                border-top-color: #222222;
                border-left-color: #222222;
                border-bottom-color: #666666;
                border-right-color: #666666;
            }
        """)
        self.btn_change_dir.clicked.connect(self.prompt_change_directory)
        
        # Current Directory Box
        self.lbl_current_dir = MarqueeLabel(char_limit=DIRECTORY_CHAR_LIMIT, enable_scroll=ENABLE_DIRECTORY_SCROLL)
        
        # Added to layout
        center_layout.addWidget(self.btn_change_dir)
        center_layout.addWidget(self.lbl_current_dir)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignCenter)

        # Right Help & Version
        right_layout = QVBoxLayout()
        right_layout.setSpacing(0)
        
        version_label = QLabel("v1.0")
        version_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        version_label.setStyleSheet("color: #aaaaaa;")
        version_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.btn_help = QPushButton("Help?")
        self.btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_help.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                color: #3b8eea; 
                text-decoration: underline; 
                font-weight: bold; 
                border: none;
                text-align: right;
            }
            QPushButton:hover { color: #61afef; }
        """)
        self.btn_help.clicked.connect(self.show_help_menu)
        
        right_layout.addWidget(version_label)
        right_layout.addWidget(self.btn_help)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        
        # Assemble Header in Grid Layout
        header_layout.addLayout(title_layout, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        header_layout.addLayout(center_layout, 0, 1, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        header_layout.addLayout(right_layout, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        
        header_layout.setColumnStretch(0, 1)
        header_layout.setColumnStretch(1, 0)
        header_layout.setColumnStretch(2, 1)
        
        layout.addLayout(header_layout)

        # --- MAIN BUTTON ---
        self.btn_matcher = OutlinedButton("Clone Hero Universal Song Matcher", stroke_width=3)
        self.btn_matcher.setMinimumHeight(70)
        self.btn_matcher.setMaximumHeight(100)
        self.btn_matcher.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        self.btn_matcher.setToolTip("Automatically track your songs with syncing, highlighting, and labeling to: RhythmVerse, Chorus Encore, and Custom Song Central")
        self.btn_matcher.setStyleSheet("""
            QPushButton { background-color: #388e3c; border-radius: 5px; padding: 10px; }
            QPushButton:hover { background-color: #4caf50; }
        """)
        self.btn_matcher.clicked.connect(lambda: self.run_script("CloneHeroUniversalSongMatcher"))
        layout.addWidget(self.btn_matcher)

        # --- TOOLS LAYOUT ---
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(10) 
        
        tool_font = QFont("Arial", 12, QFont.Weight.Bold)
        tool_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        
        self.btn_midi2chart = OutlinedButton("Clone Hero Midi 2 Chart", stroke_width=1.5)
        self.btn_midi2chart.setMinimumHeight(40)
        self.btn_midi2chart.setMaximumHeight(65)
        self.btn_midi2chart.setFont(tool_font)
        self.btn_midi2chart.setToolTip("Automatically converts all .mid/midi chart files into notes.chart files")
        self.btn_midi2chart.setStyleSheet("""
            QPushButton { background-color: #d32f2f; border-radius: 3px; padding: 10px; }
            QPushButton:hover { background-color: #f44336; }
        """)
        self.btn_midi2chart.clicked.connect(lambda: self.run_script("CloneHeroMidi2Chart", lock_action="unlock"))
        tools_layout.addWidget(self.btn_midi2chart)

        self.btn_deleter = OutlinedButton("Clone Hero No Part Deleter", stroke_width=1.5)
        self.btn_deleter.setMinimumHeight(40)
        self.btn_deleter.setMaximumHeight(65)
        self.btn_deleter.setEnabled(False)
        self.btn_deleter.setFont(tool_font)
        self.btn_deleter.setToolTip("LOCKED: Please run Midi 2 Chart to UNLOCK")
        self.btn_deleter.setStyleSheet("""
            QPushButton { background-color: #fbc02d; border-radius: 3px; padding: 10px; }
            QPushButton:hover { background-color: #fdd835; }
            QPushButton:disabled { background-color: #3c3c3c; }
        """)
        self.btn_deleter.clicked.connect(lambda: self.run_script("CloneHeroNoPartDeleter"))
        tools_layout.addWidget(self.btn_deleter)

        self.btn_diffcreator = OutlinedButton("Clone Hero Difficulty Creator", stroke_width=1.5)
        self.btn_diffcreator.setMinimumHeight(40)
        self.btn_diffcreator.setMaximumHeight(65)
        self.btn_diffcreator.setEnabled(False)
        self.btn_diffcreator.setFont(tool_font)
        self.btn_diffcreator.setToolTip("LOCKED: Please run Midi 2 Chart to UNLOCK")
        self.btn_diffcreator.setStyleSheet("""
            QPushButton { background-color: #1976d2; border-radius: 3px; padding: 10px; }
            QPushButton:hover { background-color: #2196f3; }
            QPushButton:disabled { background-color: #3c3c3c; }
        """)
        self.btn_diffcreator.clicked.connect(lambda: self.run_script("CloneHeroDifficultyCreator"))
        tools_layout.addWidget(self.btn_diffcreator)

        self.btn_chart2midi = OutlinedButton("Clone Hero Chart 2 Midi", stroke_width=1.5)
        self.btn_chart2midi.setMinimumHeight(40)
        self.btn_chart2midi.setMaximumHeight(65)
        self.btn_chart2midi.setFont(tool_font)
        self.btn_chart2midi.setToolTip("Automatically converts all notes.chart files to .mid/midi files")
        self.btn_chart2midi.setStyleSheet("""
            QPushButton { background-color: #f57c00; border-radius: 3px; padding: 10px; }
            QPushButton:hover { background-color: #ff9800; }
        """)
        self.btn_chart2midi.clicked.connect(lambda: self.run_script("CloneHeroChart2Midi", lock_action="lock"))
        tools_layout.addWidget(self.btn_chart2midi)

        layout.addLayout(tools_layout)

        # --- TERMINAL ---
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("Consolas", 10))
        self.terminal.setStyleSheet("""
            QTextEdit {
                background-color: #0c0c0c;
                color: #cccccc;
                border: 1px solid #333333;
                margin-top: 10px;
            }
        """)
        self.terminal.document().setDocumentMargin(0)
        layout.addWidget(self.terminal)

        # --- Trigger directory check 100ms after app loads ---
        QTimer.singleShot(100, self.check_and_setup_directory)
        
        # --- Background file monitor for out-of-GUI updates ---
        self.settings_monitor = QTimer(self)
        self.settings_monitor.timeout.connect(self.poll_settings_file)
        self.settings_monitor.start(1000) # Scan every 1 second

    def poll_settings_file(self):
        config_file = "CH_Settings.txt"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    lines = [line for line in f if line.strip() and not line.strip().startswith('#')]
                    if lines:
                        songs_directory = lines[0].strip()
                        # If a tool updated the file in the background, we capture the GUI update silently
                        if os.path.isdir(songs_directory) and songs_directory != self.last_known_dir:
                            self.last_known_dir = songs_directory
                            self.lbl_current_dir.set_directory(songs_directory)
            except Exception:
                pass

    def _save_directory(self, config_file, songs_directory):
        config_template = (
            "# Clone Hero Configuration\n"
            "# You can safely edit the path below using Notepad.\n"
            "# Just make sure it points to your actual Clone Hero Songs directory.\n\n"
            f"{songs_directory}\n"
        )
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_template)

    def prompt_change_directory(self):
        selected_dir = QFileDialog.getExistingDirectory(self, "Please select your Clone Hero songs folder")
        if selected_dir:
            songs_directory = os.path.normpath(selected_dir)
            self._save_directory("CH_Settings.txt", songs_directory)
            self.lbl_current_dir.set_directory(songs_directory)
            self.last_known_dir = songs_directory

    def check_and_setup_directory(self):
        config_file = "CH_Settings.txt"
        songs_directory = None

        # Check if the config file already exists
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                lines = [line for line in f if line.strip() and not line.strip().startswith('#')]
                if lines:
                    songs_directory = lines[0].strip()

        is_valid_dir = songs_directory and os.path.isdir(songs_directory)

        # Prompt the user if the directory is missing or invalid
        if not is_valid_dir:
            msg = QMessageBox(self)
            msg.setWindowTitle("First Time Setup")
            msg.setText("Please select your Clone Hero songs folder to initialize the tools")
            msg.setIcon(QMessageBox.Icon.Information)
            
            # Explicitly strip everything except the title bar to force the close button to disappear
            msg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
            msg.exec()
            
            # Open PyQt6 File Dialog
            selected_dir = QFileDialog.getExistingDirectory(self, "Please select your Clone Hero songs folder")

            if selected_dir:
                songs_directory = os.path.normpath(selected_dir)
                self._save_directory(config_file, songs_directory)
        
        if songs_directory and os.path.isdir(songs_directory):
            self.lbl_current_dir.set_directory(songs_directory)
            self.last_known_dir = songs_directory

        # Check if the user aborted the setup and path remains unset
        if self.lbl_current_dir.path_text == "Not Set":
            self.terminal.insertHtml('<span style="color: #f14c4c;">Please select your Clone Hero songs folder</span><br>')

    def show_help_menu(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Help Documentation")
        dialog.setStyleSheet("background-color: #1e1e1e; color: white;")
        
        # --- FIX 1: Explicitly lock the window size and remove the Windows stretch grip ---
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | 
                              Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        dialog.setFixedSize(300, 310)
        # ----------------------------------------------------------------------------------
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10) 
        layout.setSpacing(5)
        
        label = QLabel("Select a tool to open its guide:")
        label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(label)
        
        list_widget = QListWidget()
        list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # --- DISABLED SCROLLING ---
        list_widget.verticalScrollBar().setDisabled(True)
        list_widget.wheelEvent = lambda event: event.accept()
        list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # --------------------------
        
        help_topics = [
            "Clone Hero Universal Song Matcher",
            "Clone Hero Midi 2 Chart",
            "Clone Hero No Part Deleter",
            "Clone Hero Difficulty Creator",
            "Clone Hero Chart 2 Midi",
            "Tampermonkey"
        ]
        
        for topic in help_topics:
            list_widget.addItem(topic)
            
        list_widget.itemClicked.connect(lambda item: self.open_help_file(item.text()))
        list_widget.setStyleSheet("""
            QListWidget { 
                border: 1px solid #333333; 
                background-color: #0c0c0c; 
                outline: none;
            }
            QListWidget::item { 
                height: 40px; 
                padding-left: 10px; 
                border-bottom: 1px solid #222;
            }
            QListWidget::item:hover { 
                background-color: #388e3c; 
            }
            QListWidget::item:selected {
                background-color: #4caf50;
            }
        """)
        
        # --- FIX 2: Height is exactly 6 items * 40px + 6px (inner borders) + 2px (outer border) ---
        list_widget.setFixedHeight(248)
        # ------------------------------------------------------------------------------------------
        layout.addWidget(list_widget)
        
        dialog.exec()

    def get_resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)
        
    def open_help_file(self, topic_name):
        bundled_path = self.get_resource_path(f"{topic_name}.txt")
        
        if os.path.exists(bundled_path):
            try:
                with open(bundled_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                content = f"Error reading help file: {e}"
        else:
            content = f"--- Help Documentation for {topic_name} ---\n\nHelp file not found in the application bundle. Ensure the .txt file was included during the build process."
            
        self.show_help_text_window(topic_name, content)

    def show_help_text_window(self, topic_name, text_content):
        help_window = HelpDialog(topic_name, text_content, self)
        help_window.exec()

    def _reset_to_top(self):
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.terminal.setTextCursor(cursor)
        
        fmt = QTextBlockFormat()
        fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)
        fmt.setTopMargin(0)
        cursor.mergeBlockFormat(fmt)

    def closeEvent(self, event):
        self.is_closing = True
        self.kill_process()
        event.accept()

    def run_script(self, module_name, lock_action=None):
        self.kill_process()
        self.terminal.clear()
        
        self._reset_to_top()
        
        display_name = re.sub(r'(?<=[a-z])(?=[A-Z])|(?<=[a-zA-Z])(?=[0-9])|(?<=[0-9])(?=[a-zA-Z])', ' ', module_name)
        self.terminal.insertHtml(f'<span style="color: #ffffff;">--- Starting {display_name} ---</span><br><br>')
        
        self.active_process = QProcess(self)
        self.active_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.active_process.readyReadStandardOutput.connect(self.handle_stdout)
        
        self.active_process.finished.connect(lambda exitCode, exitStatus: self.process_finished(module_name, lock_action))
        self.active_process.start(sys.executable, ["--run-script", module_name])

    def handle_stdout(self):
        if not self.active_process or self.is_closing:
            return
            
        data_bytes = self.active_process.readAllStandardOutput().data()
        try:
            data = data_bytes.decode('utf-8', errors='replace')
        except Exception:
            data = data_bytes.decode('cp1252', errors='replace')
        
        if '\033[2J' in data or '\033[3J' in data:
            self.terminal.clear()
            self._reset_to_top()

        html_text = self.ansi_to_html(data)
        
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html_text)
        self.terminal.setTextCursor(cursor)
        
        self.terminal.ensureCursorVisible()
        self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())

    def ansi_to_html(self, text):
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        text = text.replace('\r', '')
        text = text.replace('\n', '<br>')
        text = text.replace('  ', '&nbsp;&nbsp;')
        
        color_map = {
            '30': '#000000', '31': '#cd3131', '32': '#0dbc79', '33': '#e5e510', 
            '34': '#2472c8', '35': '#bc3fbc', '36': '#11a8cd', '37': '#e5e5e5',
            '90': '#666666', '91': '#f14c4c', '92': '#23d18b', '93': '#f5f543', 
            '94': '#3b8eea', '95': '#d670d6', '96': '#29b8db', '97': '#e5e5e5'
        }
        
        html = ""
        parts = re.split(r'\x1B\[([\d;]+)m', text)
        
        html += parts[0]
        current_color = None
        
        for i in range(1, len(parts), 2):
            code_str = parts[i]
            text_part = parts[i+1]
            codes = code_str.split(';')
            
            if codes[0] == '0' or codes[0] == '':
                if current_color:
                    html += "</span>"
                    current_color = None
            elif codes[0] == '38' and len(codes) >= 5 and codes[1] == '2':
                if current_color:
                    html += "</span>"
                r, g, b = codes[2], codes[3], codes[4]
                current_color = f"rgb({r},{g},{b})"
                html += f'<span style="color: {current_color};">'
            elif codes[0] in color_map:
                if current_color:
                    html += "</span>"
                current_color = color_map[codes[0]]
                html += f'<span style="color: {current_color};">'
                
            html += text_part
            
        if current_color:
            html += "</span>"
            
        html = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', html)
        return html

    def process_finished(self, module_name, lock_action):
        if self.is_closing: return
        
        display_name = re.sub(r'(?<=[a-z])(?=[A-Z])|(?<=[a-zA-Z])(?=[0-9])|(?<=[0-9])(?=[a-zA-Z])', ' ', module_name)
        
        self.terminal.insertHtml(f'<br><span style="color: #ffffff;">--- {display_name} finished ---</span><br>')
        self.active_process = None

        if lock_action == "unlock":
            was_locked = not self.btn_deleter.isEnabled()
            
            self.btn_diffcreator.setEnabled(True)
            self.btn_deleter.setEnabled(True)
            self.btn_diffcreator.setToolTip("Automatically generate Easy, Medium, and Hard difficulties from an Expert chart to all songs (does not override already charted)")
            self.btn_deleter.setToolTip("Scan and delete all song folders missing playable instrument parts (Guitar, Bass, Rhythm, and/or Keys)")
            
            if was_locked:
                self.terminal.insertHtml('<span style="color: #23d18b;">Clone Hero No Part Deleter and Clone Hero Difficulty Creator are now UNLOCKED</span><br>')
                
        elif lock_action == "lock":
            self.btn_diffcreator.setEnabled(False)
            self.btn_deleter.setEnabled(False)
            self.btn_diffcreator.setToolTip("LOCKED: Please run Clone Hero Midi 2 Chart to UNLOCK")
            self.btn_deleter.setToolTip("LOCKED: Please run Clone Hero Midi 2 Chart to UNLOCK")
            self.terminal.insertHtml('<span style="color: #f14c4c;">Clone Hero No Part Deleter and Clone Hero Difficulty Creator are now LOCKED</span><br>')
            self.terminal.insertHtml('<span style="color: #f14c4c;">Please run Clone Hero Midi 2 Chart to UNLOCK</span><br>')

    def kill_process(self):
        if self.active_process and self.active_process.state() == QProcess.ProcessState.Running:
            self.active_process.kill()
            self.active_process.waitForFinished()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    import ctypes
    try:
        # Taskbar grouping fix for Windows
        myappid = 'wavez.cloneherotools.aio.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass
    
    app = QApplication(sys.argv)
    
    # --- BULLETPROOF ICON PATH RESOLUTION ---
    icon_filename = "Clone Hero Tools AIO (All-In-one) Icon 2.ico"
    icon_path = ""
    
    if getattr(sys, 'frozen', False):
        # We are running as a compiled .exe
        # PyInstaller extracts to sys._MEIPASS (which is the _internal folder in dir builds)
        internal_path = os.path.join(sys._MEIPASS, icon_filename)
        exe_path = os.path.join(os.path.dirname(sys.executable), icon_filename)
        
        if os.path.exists(internal_path):
            icon_path = internal_path
        elif os.path.exists(exe_path):
            icon_path = exe_path
        else:
            icon_path = icon_filename # Blind fallback
    else:
        # We are running as a raw .py script in the IDE
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), icon_filename)
        
    app.setWindowIcon(QIcon(icon_path))
    # -----------------------------------------
    
    window = CloneHeroToolSuite()
    window.show()
    sys.exit(app.exec())