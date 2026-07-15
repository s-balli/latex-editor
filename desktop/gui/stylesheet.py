"""Merkezi stylesheet oluşturucu — tema sözlüğünden CSS üretir."""


def build_stylesheet(t: dict) -> str:
    return f"""
        /* === Genel === */
        * {{ background: {t["bg_primary"]}; color: {t["fg_primary"]}; }}
        QMainWindow {{ background: {t["bg_primary"]}; }}
        QWidget {{ background: {t["bg_primary"]}; color: {t["fg_primary"]}; }}

        /* === Menü Bar === */
        QMenuBar {{ background: {t["bg_toolbar"]}; color: {t["fg_primary"]}; border-bottom: 1px solid {t["border_subtle"]}; }}
        QMenuBar::item {{ padding: 4px 10px; }}
        QMenuBar::item:selected {{ background: {t["bg_button"]}; border-radius: 4px; }}
        QMenu {{ background: {t["bg_toolbar"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_separator"]}; padding: 4px; }}
        QMenu::item {{ padding: 5px 24px; border-radius: 3px; }}
        QMenu::item:selected {{ background: {t["bg_pressed"]}; }}
        QMenu::separator {{ height: 1px; background: {t["border_separator"]}; margin: 4px 8px; }}

        /* === Toolbar === */
        QToolBar {{
            background: {t["bg_toolbar"]}; border: none; border-bottom: 1px solid {t["border_mid"]};
            spacing: 2px; padding: 3px 6px;
        }}
        QToolBar QToolButton {{
            color: {t["fg_primary"]}; padding: 5px 10px; background: {t["bg_button"]};
            border: 1px solid {t["border_input"]}; border-radius: 4px; font-size: 12px;
        }}
        QToolBar QToolButton:hover {{
            background: {t["bg_button"]}; border: 1px solid {t["border_input"]};
        }}
        QToolBar QToolButton:pressed {{
            background: {t["bg_pressed"]}; border: 1px solid {t["accent"]};
        }}
        QToolBar::separator {{ width: 1px; background: {t["border_separator"]}; margin: 4px 6px; }}

        /* === Sekmeler === */
        QTabWidget::pane {{ border: 1px solid {t["border_normal"]}; background: {t["bg_primary"]}; }}
        QTabBar::tab {{
            background: {t["bg_toolbar"]}; color: {t["fg_muted"]}; padding: 7px 16px;
            border: 1px solid transparent; border-bottom: none;
            border-top-left-radius: 6px; border-top-right-radius: 6px;
            margin-right: 1px;
        }}
        QTabBar::tab:hover {{ background: {t["bg_hover_alt"]}; color: {t["fg_label"]}; }}
        QTabBar::tab:selected {{
            background: {t["bg_primary"]}; color: {t["fg_editor"]};
            border: 1px solid {t["border_normal"]}; border-bottom: 2px solid {t["tab_active_border"]};
        }}

        /* === Status Bar === */
        QStatusBar {{ background: {t["bg_statusbar"]}; color: {t["fg_primary"]}; font-size: 12px; }}
        QStatusBar QLabel {{ color: {t["fg_primary"]}; background: transparent; padding: 0 10px; }}
        QProgressBar {{
            background: {t["bg_statusbar_deep"]}; border: none; border-radius: 2px;
        }}
        QProgressBar::chunk {{
            background: {t["accent_progress"]}; border-radius: 2px;
        }}

        /* === Ortak Widget'lar === */
        QLabel {{ background: transparent; }}
        QComboBox {{
            background: {t["bg_button"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_input"]};
            padding: 4px 10px; border-radius: 4px; min-width: 90px;
        }}
        QComboBox:hover {{ border: 1px solid {t["accent"]}; }}
        QComboBox QAbstractItemView {{
            background: {t["bg_toolbar"]}; color: {t["fg_primary"]}; selection-background-color: {t["bg_pressed"]};
            border: 1px solid {t["border_mid"]};
        }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox::down-arrow {{ image: none; border: none; }}

        QPushButton {{
            background: {t["bg_button"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_input"]};
            padding: 4px 12px; border-radius: 4px;
        }}
        QPushButton:hover {{ background: {t["bg_hover"]}; border: 1px solid {t["accent"]}; }}
        QPushButton:pressed {{ background: {t["bg_pressed"]}; }}

        QLineEdit {{
            background: {t["bg_button"]}; color: {t["fg_primary"]}; border: 1px solid {t["border_input"]};
            padding: 4px 8px; border-radius: 4px;
        }}
        QLineEdit:focus {{ border: 1px solid {t["accent"]}; }}

        /* === Splitter === */
        QSplitter::handle {{ background: {t["border_normal"]}; }}
        QSplitter::handle:hover {{ background: {t["accent"]}; }}

        /* === Scrollbar === */
        QScrollArea {{ background: {t["bg_primary"]}; border: none; }}
        QScrollBar:vertical {{
            background: {t["bg_primary"]}; width: 10px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {t["scrollbar_handle"]}; border-radius: 4px; min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {t["accent"]}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

        /* === Dialog === */
        QFileDialog {{ background: {t["bg_primary"]}; color: {t["fg_primary"]}; }}
        QMessageBox {{ background: {t["bg_primary"]}; color: {t["fg_primary"]}; }}
    """
