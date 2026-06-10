# -*- coding: utf-8 -*-
"""Fluent Design 主题配置 - Catppuccin Mocha 配色"""

# Catppuccin Mocha 色板
BASE = "#1e1e2e"
MANTLE = "#181825"
CRUST = "#11111b"
SURFACE0 = "#313244"
SURFACE1 = "#45475a"
SURFACE2 = "#585b70"
OVERLAY0 = "#6c7086"
OVERLAY1 = "#7f849c"
TEXT = "#cdd6f4"
SUBTEXT0 = "#a6adc8"
SUBTEXT1 = "#bac2de"
BLUE = "#89b4fa"
LAVENDER = "#b4befe"
SAPPHIRE = "#74c7ec"
SKY = "#89dceb"
TEAL = "#94e2d5"
GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
PEACH = "#fab387"
MAROON = "#eba0ac"
RED = "#f38ba8"
MAUVE = "#cba6f7"
PINK = "#f5c2e7"
FLAMINGO = "#f2cdcd"
ROSEWATER = "#f5e0dc"

# 暗底（用于按钮背景等）
BLUE_DIM = "#2a3a5c"
GREEN_DIM = "#2a3a2c"
RED_DIM = "#3a2a2a"

# 语义色
BG_PRIMARY = BASE
BG_SECONDARY = MANTLE
BG_CARD = SURFACE0
BG_HOVER = SURFACE1
FG_PRIMARY = TEXT
FG_SECONDARY = SUBTEXT0
ACCENT = BLUE
SUCCESS = GREEN
WARNING = YELLOW
DANGER = RED
INFO = SAPPHIRE

# 间距
PADDING = 12
PADDING_SM = 8
PADDING_LG = 16
RADIUS = 8
RADIUS_LG = 12


def apply_global_stylesheet(app):
    """应用全局 QSS 样式"""
    app.setStyleSheet(f"""
        QWidget {{
            background-color: {BG_PRIMARY};
            color: {FG_PRIMARY};
            font-family: "Microsoft YaHei UI", "Segoe UI Variable", sans-serif;
            font-size: 13px;
        }}
        QScrollBar:vertical {{
            background: {BG_SECONDARY};
            width: 8px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {SURFACE1};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {OVERLAY0};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: {BG_SECONDARY};
            height: 8px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: {SURFACE1};
            border-radius: 4px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {OVERLAY0};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QToolTip {{
            background: {SURFACE0};
            color: {TEXT};
            border: 1px solid {SURFACE1};
            padding: 4px 8px;
            border-radius: 4px;
        }}
        QTextEdit, QPlainTextEdit {{
            background-color: {CRUST};
            color: {TEXT};
            border: 1px solid {SURFACE1};
            border-radius: 6px;
            padding: 6px;
            selection-background-color: {SURFACE1};
        }}
        QLineEdit {{
            background-color: {SURFACE0};
            color: {TEXT};
            border: 1px solid {SURFACE1};
            border-radius: 6px;
            padding: 6px 10px;
            selection-background-color: {BLUE};
        }}
        QLineEdit:focus {{
            border: 1px solid {BLUE};
        }}
        QListWidget {{
            background-color: {CRUST};
            color: {TEXT};
            border: none;
            outline: none;
        }}
        QListWidget::item {{
            padding: 6px 10px;
            border-radius: 4px;
        }}
        QListWidget::item:selected {{
            background-color: {BLUE_DIM};
            color: {BLUE};
        }}
        QListWidget::item:hover {{
            background-color: {SURFACE0};
        }}
    """)
