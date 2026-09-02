"""Merkezi tema tanımları — genişletilebilir renk şemaları."""

from PyQt6.QtCore import QObject, QSettings, pyqtSignal

from core.log import get_logger
from PyQt6.QtCore import QCoreApplication

_logger = get_logger("theme")
_ = lambda s: QCoreApplication.translate("ThemeManager", s)

# Yeni tema eklerken bu listedeki tüm anahtarları sağlamanız gerekir.
REQUIRED_KEYS = [
    "bg_primary", "bg_secondary", "bg_toolbar", "bg_button",
    "bg_hover", "bg_hover_alt", "bg_statusbar", "bg_statusbar_deep",
    "bg_pressed", "bg_math", "bg_item_hover", "bg_pdf_scroll",
    "bg_pdf_placeholder",
    "fg_primary", "fg_editor", "fg_bright", "fg_muted", "fg_dim",
    "fg_line_numbers", "fg_label",
    "border_subtle", "border_normal", "border_mid", "border_input",
    "border_separator",
    "accent", "accent_selection", "accent_progress", "scrollbar_handle",
    "tab_active_border", "tab_close_hover",
    "syn_default", "syn_command", "syn_cmd_arg", "syn_bracket",
    "syn_comment", "syn_math", "syn_math_cmd", "syn_env_arg",
    "sem_folder", "sem_compilable", "sem_error", "sem_warning",
    "sem_hint", "sem_suggestion",
    "outline_part", "outline_chapter", "outline_section",
    "outline_subsection", "outline_subsubsection",
    "outline_paragraph", "outline_subparagraph",
    "pdf_hl_bg", "pdf_hl_border",
    "pdf_sel_bg", "pdf_sel_border",
]


def _validate_themes():
    missing = {}
    for name, theme in THEMES.items():
        for key in REQUIRED_KEYS:
            if key not in theme:
                missing.setdefault(name, []).append(key)
    if missing:
        for name, keys in missing.items():
            _logger.warning("Tema '%s' eksik anahtarlar: %s", name, ", ".join(keys))

THEMES = {
    "dark": {
        # -- Yüzeyler --
        "bg_primary":         "#1e1e1e",
        "bg_secondary":       "#252526",
        "bg_toolbar":         "#2d2d2d",
        "bg_button":          "#3c3c3c",
        "bg_hover":           "#2a2d2e",
        "bg_hover_alt":       "#353535",
        "bg_statusbar":       "#1a3a5c",
        "bg_statusbar_deep":  "#0d2137",
        "bg_pressed":         "#094771",
        "bg_math":            "#2a1f3d",
        "bg_item_hover":      "#2a2a2a",
        "bg_pdf_scroll":      "#2d2d2d",
        "bg_pdf_placeholder": "#3c3c3c",

        # -- Yazılar --
        "fg_primary":         "#cccccc",
        "fg_editor":          "#d4d4d4",
        "fg_bright":          "#ffffff",
        "fg_muted":           "#949494",
        "fg_dim":             "#666666",
        "fg_line_numbers":    "#858585",
        "fg_label":           "#aaaaaa",

        # -- Kenarlıklar --
        "border_subtle":      "#222222",
        "border_normal":      "#333333",
        "border_mid":         "#3a3a3a",
        "border_input":       "#555555",
        "border_separator":   "#444444",

        # -- Vurgu --
        "accent":             "#3a6ea5",
        "accent_selection":   "#264f78",
        "accent_progress":    "#4ec9b0",
        "scrollbar_handle":   "#555555",
        "tab_active_border":  "#3a6ea5",
        "tab_close_hover":    "#c14545",

        # -- Sözdizimi --
        "syn_default":        "#d4d4d4",
        "syn_command":        "#569cd6",
        "syn_cmd_arg":        "#ce9178",
        "syn_bracket":        "#b5cea8",
        "syn_comment":        "#6a9955",
        "syn_math":           "#c586c0",
        "syn_math_cmd":       "#9cdcfe",
        "syn_env_arg":        "#4ec9b0",

        # -- Anlamsal --
        "sem_folder":         "#7eb8da",
        "sem_compilable":     "#e8d44d",
        "sem_error":          "#f44747",
        "sem_warning":        "#cca700",
        "sem_hint":           "#ff9900",
        "sem_suggestion":     "#4ec9b0",

        # -- Outline seviyeleri --
        "outline_part":             "#e8d44d",
        "outline_chapter":          "#c586c0",
        "outline_section":          "#d4d4d4",
        "outline_subsection":       "#9cdcfe",
        "outline_subsubsection":    "#9cdcfe",
        "outline_paragraph":        "#888888",
        "outline_subparagraph":     "#888888",

        # -- PDF vurgulama --
        "pdf_hl_bg":         "rgba(255, 200, 0, 80)",
        "pdf_hl_border":     "rgba(255, 165, 0, 180)",
        "pdf_sel_bg":        "rgba(59, 130, 246, 80)",
        "pdf_sel_border":    "rgba(59, 130, 246, 160)",
    },

    "light": {
        # -- Yüzeyler --
        "bg_primary":         "#efefef",
        "bg_secondary":       "#e6e6e6",
        "bg_toolbar":         "#e2e2e2",
        "bg_button":          "#d5d5d5",
        "bg_hover":           "#dddada",
        "bg_hover_alt":       "#e0e0e0",
        "bg_statusbar":       "#d5d5d5",
        "bg_statusbar_deep":  "#c2c2c2",
        "bg_pressed":         "#c4e1ff",
        "bg_math":            "#f0edf8",
        "bg_item_hover":      "#e5e5e5",
        "bg_pdf_scroll":      "#d4d4d4",
        "bg_pdf_placeholder": "#c0c0c0",

        # -- Yazılar --
        "fg_primary":         "#333333",
        "fg_editor":          "#1e1e1e",
        "fg_bright":          "#1e1e1e",
        "fg_muted":           "#636363",
        "fg_dim":             "#999999",
        "fg_line_numbers":    "#858585",
        "fg_label":           "#444444",

        # -- Kenarlıklar --
        "border_subtle":      "#e0e0e0",
        "border_normal":      "#d0d0d0",
        "border_mid":         "#cccccc",
        "border_input":       "#b0b0b0",
        "border_separator":   "#cccccc",

        # -- Vurgu --
        "accent":             "#0078d4",
        "accent_selection":   "#add6ff",
        "accent_progress":    "#0078d4",
        "scrollbar_handle":   "#c0c0c0",
        "tab_active_border":  "#0078d4",
        "tab_close_hover":    "#e81123",

        # -- Sözdizimi --
        "syn_default":        "#1e1e1e",
        "syn_command":        "#0000ff",
        "syn_cmd_arg":        "#a31515",
        "syn_bracket":        "#098658",
        "syn_comment":        "#008000",
        "syn_math":           "#795e26",
        "syn_math_cmd":       "#267f99",
        "syn_env_arg":        "#267f99",

        # -- Anlamsal --
        "sem_folder":         "#0078d4",
        "sem_compilable":     "#b58900",
        "sem_error":          "#d73a49",
        "sem_warning":        "#b58900",
        "sem_hint":           "#e36209",
        "sem_suggestion":     "#0078d4",

        # -- Outline seviyeleri --
        "outline_part":             "#b58900",
        "outline_chapter":          "#795e26",
        "outline_section":          "#1e1e1e",
        "outline_subsection":       "#267f99",
        "outline_subsubsection":    "#267f99",
        "outline_paragraph":        "#6e6e6e",
        "outline_subparagraph":     "#6e6e6e",

        # -- PDF vurgulama --
        "pdf_hl_bg":         "rgba(0, 100, 255, 40)",
        "pdf_hl_border":     "rgba(0, 80, 200, 160)",
        "pdf_sel_bg":        "rgba(0, 100, 255, 60)",
        "pdf_sel_border":    "rgba(0, 80, 200, 140)",
    },

    "solarized_light": {
        # -- Yüzeyler (Solarized base3 → base2 gradient) --
        "bg_primary":         "#fdf6e3",
        "bg_secondary":       "#eee8d5",
        "bg_toolbar":         "#eee8d5",
        "bg_button":          "#ddd6c1",
        "bg_hover":           "#e0dac6",
        "bg_hover_alt":       "#e8e2cf",
        "bg_statusbar":       "#eee8d5",
        "bg_statusbar_deep":  "#ddd6c1",
        "bg_pressed":         "#c4d5e4",
        "bg_math":            "#eee8d5",
        "bg_item_hover":      "#e8e2cf",
        "bg_pdf_scroll":      "#eee8d5",
        "bg_pdf_placeholder": "#ddd6c1",

        # -- Yazılar (Solarized base00 → base1) --
        "fg_primary":         "#657b83",
        "fg_editor":          "#586e75",
        "fg_bright":          "#073642",
        "fg_muted":           "#5d6b6b",
        "fg_dim":             "#b0bec5",
        "fg_line_numbers":    "#93a1a1",
        "fg_label":           "#657b83",

        # -- Kenarlıklar --
        "border_subtle":      "#e0dac6",
        "border_normal":      "#d6ceb6",
        "border_mid":         "#c9c0a9",
        "border_input":       "#b8b090",
        "border_separator":   "#d6ceb6",

        # -- Vurgu (Solarized blue accent) --
        "accent":             "#268bd2",
        "accent_selection":   "#c4d5e4",
        "accent_progress":    "#2aa198",
        "scrollbar_handle":   "#c9c0a9",
        "tab_active_border":  "#268bd2",
        "tab_close_hover":    "#dc322f",

        # -- Sözdizimi (Solarized syntax palette) --
        "syn_default":        "#586e75",
        "syn_command":        "#268bd2",
        "syn_cmd_arg":        "#2aa198",
        "syn_bracket":        "#859900",
        "syn_comment":        "#93a1a1",
        "syn_math":           "#6c71c4",
        "syn_math_cmd":       "#268bd2",
        "syn_env_arg":        "#b58900",

        # -- Anlamsal --
        "sem_folder":         "#268bd2",
        "sem_compilable":     "#b58900",
        "sem_error":          "#dc322f",
        "sem_warning":        "#b58900",
        "sem_hint":           "#cb4b16",
        "sem_suggestion":     "#2aa198",

        # -- Outline seviyeleri --
        "outline_part":             "#b58900",
        "outline_chapter":          "#6c71c4",
        "outline_section":          "#586e75",
        "outline_subsection":       "#268bd2",
        "outline_subsubsection":    "#2aa198",
        "outline_paragraph":        "#93a1a1",
        "outline_subparagraph":     "#93a1a1",

        # -- PDF vurgulama --
        "pdf_hl_bg":         "rgba(38, 139, 210, 40)",
        "pdf_hl_border":     "rgba(38, 139, 210, 140)",
        "pdf_sel_bg":        "rgba(38, 139, 210, 60)",
        "pdf_sel_border":    "rgba(38, 139, 210, 140)",
    },

    "dracula": {
        # -- Yüzeyler --
        "bg_primary":         "#282a36",
        "bg_secondary":       "#21222c",
        "bg_toolbar":         "#21222c",
        "bg_button":          "#44475a",
        "bg_hover":           "#343746",
        "bg_hover_alt":       "#3a3d4e",
        "bg_statusbar":       "#191a21",
        "bg_statusbar_deep":  "#13141b",
        "bg_pressed":         "#44475a",
        "bg_math":            "#2d2440",
        "bg_item_hover":      "#343746",
        "bg_pdf_scroll":      "#21222c",
        "bg_pdf_placeholder": "#44475a",

        # -- Yazılar --
        "fg_primary":         "#f8f8f2",
        "fg_editor":          "#f8f8f2",
        "fg_bright":          "#f8f8f2",
        "fg_muted":           "#7c89b3",
        "fg_dim":             "#50506a",
        "fg_line_numbers":    "#6272a4",
        "fg_label":           "#8be9fd",

        # -- Kenarlıklar --
        "border_subtle":      "#21222c",
        "border_normal":      "#44475a",
        "border_mid":         "#3a3d4e",
        "border_input":       "#44475a",
        "border_separator":   "#44475a",

        # -- Vurgu --
        "accent":             "#bd93f9",
        "accent_selection":   "#44475a",
        "accent_progress":    "#50fa7b",
        "scrollbar_handle":   "#44475a",
        "tab_active_border":  "#bd93f9",
        "tab_close_hover":    "#ff5555",

        # -- Sözdizimi --
        "syn_default":        "#f8f8f2",
        "syn_command":        "#ff79c6",
        "syn_cmd_arg":        "#f1fa8c",
        "syn_bracket":        "#50fa7b",
        "syn_comment":        "#6272a4",
        "syn_math":           "#bd93f9",
        "syn_math_cmd":       "#8be9fd",
        "syn_env_arg":        "#50fa7b",

        # -- Anlamsal --
        "sem_folder":         "#8be9fd",
        "sem_compilable":     "#f1fa8c",
        "sem_error":          "#ff5555",
        "sem_warning":        "#ffb86c",
        "sem_hint":           "#ffb86c",
        "sem_suggestion":     "#50fa7b",

        # -- Outline seviyeleri --
        "outline_part":             "#f1fa8c",
        "outline_chapter":          "#bd93f9",
        "outline_section":          "#f8f8f2",
        "outline_subsection":       "#8be9fd",
        "outline_subsubsection":    "#50fa7b",
        "outline_paragraph":        "#6272a4",
        "outline_subparagraph":     "#6272a4",

        # -- PDF vurgulama --
        "pdf_hl_bg":         "rgba(189, 147, 249, 60)",
        "pdf_hl_border":     "rgba(189, 147, 249, 160)",
        "pdf_sel_bg":        "rgba(98, 114, 164, 80)",
        "pdf_sel_border":    "rgba(98, 114, 164, 160)",
    },

    "monokai": {
        # -- Yüzeyler --
        "bg_primary":         "#272822",
        "bg_secondary":       "#1e1f1c",
        "bg_toolbar":         "#1e1f1c",
        "bg_button":          "#3e3d32",
        "bg_hover":           "#3e3d32",
        "bg_hover_alt":       "#49483e",
        "bg_statusbar":       "#1a1b18",
        "bg_statusbar_deep":  "#141511",
        "bg_pressed":         "#49483e",
        "bg_math":            "#2d2b22",
        "bg_item_hover":      "#3e3d32",
        "bg_pdf_scroll":      "#1e1f1c",
        "bg_pdf_placeholder": "#3e3d32",

        # -- Yazılar --
        "fg_primary":         "#f8f8f2",
        "fg_editor":          "#f8f8f2",
        "fg_bright":          "#f8f8f2",
        "fg_muted":           "#8c8770",
        "fg_dim":             "#5c5a4a",
        "fg_line_numbers":    "#75715e",
        "fg_label":           "#a6a28c",

        # -- Kenarlıklar --
        "border_subtle":      "#1e1f1c",
        "border_normal":      "#3e3d32",
        "border_mid":         "#49483e",
        "border_input":       "#49483e",
        "border_separator":   "#3e3d32",

        # -- Vurgu --
        "accent":             "#a6e22e",
        "accent_selection":   "#49483e",
        "accent_progress":    "#a6e22e",
        "scrollbar_handle":   "#49483e",
        "tab_active_border":  "#a6e22e",
        "tab_close_hover":    "#f92672",

        # -- Sözdizimi --
        "syn_default":        "#f8f8f2",
        "syn_command":        "#f92672",
        "syn_cmd_arg":        "#e6db74",
        "syn_bracket":        "#a6e22e",
        "syn_comment":        "#75715e",
        "syn_math":           "#ae81ff",
        "syn_math_cmd":       "#66d9ef",
        "syn_env_arg":        "#a6e22e",

        # -- Anlamsal --
        "sem_folder":         "#66d9ef",
        "sem_compilable":     "#e6db74",
        "sem_error":          "#f92672",
        "sem_warning":        "#fd971f",
        "sem_hint":           "#fd971f",
        "sem_suggestion":     "#a6e22e",

        # -- Outline seviyeleri --
        "outline_part":             "#e6db74",
        "outline_chapter":          "#ae81ff",
        "outline_section":          "#f8f8f2",
        "outline_subsection":       "#66d9ef",
        "outline_subsubsection":    "#a6e22e",
        "outline_paragraph":        "#75715e",
        "outline_subparagraph":     "#75715e",

        # -- PDF vurgulama --
        "pdf_hl_bg":         "rgba(166, 226, 46, 50)",
        "pdf_hl_border":     "rgba(166, 226, 46, 150)",
        "pdf_sel_bg":        "rgba(102, 217, 239, 60)",
        "pdf_sel_border":    "rgba(102, 217, 239, 140)",
    },

    "nord": {
        # -- Yüzeyler --
        "bg_primary":         "#2e3440",
        "bg_secondary":       "#292e39",
        "bg_toolbar":         "#292e39",
        "bg_button":          "#3b4252",
        "bg_hover":           "#3b4252",
        "bg_hover_alt":       "#434c5e",
        "bg_statusbar":       "#272c36",
        "bg_statusbar_deep":  "#232830",
        "bg_pressed":         "#434c5e",
        "bg_math":            "#33394a",
        "bg_item_hover":      "#3b4252",
        "bg_pdf_scroll":      "#292e39",
        "bg_pdf_placeholder": "#3b4252",

        # -- Yazılar --
        "fg_primary":         "#d8dee9",
        "fg_editor":          "#eceff4",
        "fg_bright":          "#eceff4",
        "fg_muted":           "#8a95ac",
        "fg_dim":             "#4c566a",
        "fg_line_numbers":    "#616e88",
        "fg_label":           "#81a1c1",

        # -- Kenarlıklar --
        "border_subtle":      "#292e39",
        "border_normal":      "#3b4252",
        "border_mid":         "#434c5e",
        "border_input":       "#434c5e",
        "border_separator":   "#3b4252",

        # -- Vurgu --
        "accent":             "#88c0d0",
        "accent_selection":   "#434c5e",
        "accent_progress":    "#a3be8c",
        "scrollbar_handle":   "#434c5e",
        "tab_active_border":  "#88c0d0",
        "tab_close_hover":    "#bf616a",

        # -- Sözdizimi --
        "syn_default":        "#d8dee9",
        "syn_command":        "#81a1c1",
        "syn_cmd_arg":        "#a3be8c",
        "syn_bracket":        "#8fbcbb",
        "syn_comment":        "#616e88",
        "syn_math":           "#b48ead",
        "syn_math_cmd":       "#88c0d0",
        "syn_env_arg":        "#8fbcbb",

        # -- Anlamsal --
        "sem_folder":         "#88c0d0",
        "sem_compilable":     "#ebcb8b",
        "sem_error":          "#bf616a",
        "sem_warning":        "#ebcb8b",
        "sem_hint":           "#d08770",
        "sem_suggestion":     "#a3be8c",

        # -- Outline seviyeleri --
        "outline_part":             "#ebcb8b",
        "outline_chapter":          "#b48ead",
        "outline_section":          "#d8dee9",
        "outline_subsection":       "#88c0d0",
        "outline_subsubsection":    "#8fbcbb",
        "outline_paragraph":        "#616e88",
        "outline_subparagraph":     "#616e88",

        # -- PDF vurgulama --
        "pdf_hl_bg":         "rgba(136, 192, 208, 50)",
        "pdf_hl_border":     "rgba(136, 192, 208, 150)",
        "pdf_sel_bg":        "rgba(136, 192, 208, 60)",
        "pdf_sel_border":    "rgba(136, 192, 208, 140)",
    },

    "gruvbox": {
        # -- Yüzeyler --
        "bg_primary":         "#282828",
        "bg_secondary":       "#1d2021",
        "bg_toolbar":         "#1d2021",
        "bg_button":          "#3c3836",
        "bg_hover":           "#3c3836",
        "bg_hover_alt":       "#504945",
        "bg_statusbar":       "#1d2021",
        "bg_statusbar_deep":  "#161819",
        "bg_pressed":         "#504945",
        "bg_math":            "#302c28",
        "bg_item_hover":      "#3c3836",
        "bg_pdf_scroll":      "#1d2021",
        "bg_pdf_placeholder": "#3c3836",

        # -- Yazılar --
        "fg_primary":         "#ebdbb2",
        "fg_editor":          "#ebdbb2",
        "fg_bright":          "#fbf1c7",
        "fg_muted":           "#938475",
        "fg_dim":             "#665c54",
        "fg_line_numbers":    "#928374",
        "fg_label":           "#83a598",

        # -- Kenarlıklar --
        "border_subtle":      "#1d2021",
        "border_normal":      "#3c3836",
        "border_mid":         "#504945",
        "border_input":       "#504945",
        "border_separator":   "#3c3836",

        # -- Vurgu --
        "accent":             "#fe8019",
        "accent_selection":   "#504945",
        "accent_progress":    "#b8bb26",
        "scrollbar_handle":   "#504945",
        "tab_active_border":  "#fe8019",
        "tab_close_hover":    "#fb4934",

        # -- Sözdizimi --
        "syn_default":        "#ebdbb2",
        "syn_command":        "#fb4934",
        "syn_cmd_arg":        "#fabd2f",
        "syn_bracket":        "#b8bb26",
        "syn_comment":        "#928374",
        "syn_math":           "#d3869b",
        "syn_math_cmd":       "#83a598",
        "syn_env_arg":        "#b8bb26",

        # -- Anlamsal --
        "sem_folder":         "#83a598",
        "sem_compilable":     "#fabd2f",
        "sem_error":          "#fb4934",
        "sem_warning":        "#fabd2f",
        "sem_hint":           "#fe8019",
        "sem_suggestion":     "#b8bb26",

        # -- Outline seviyeleri --
        "outline_part":             "#fabd2f",
        "outline_chapter":          "#d3869b",
        "outline_section":          "#ebdbb2",
        "outline_subsection":       "#83a598",
        "outline_subsubsection":    "#b8bb26",
        "outline_paragraph":        "#928374",
        "outline_subparagraph":     "#928374",

        # -- PDF vurgulama --
        "pdf_hl_bg":         "rgba(254, 128, 25, 50)",
        "pdf_hl_border":     "rgba(254, 128, 25, 150)",
        "pdf_sel_bg":        "rgba(131, 165, 152, 60)",
        "pdf_sel_border":    "rgba(131, 165, 152, 140)",
    },
}


class ThemeManager(QObject):
    theme_changed = pyqtSignal(dict)

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._current = settings.value("theme", "dark")
        if self._current not in THEMES:
            self._current = "dark"
        _validate_themes()

    @property
    def current_name(self) -> str:
        return self._current

    @property
    def theme(self) -> dict:
        return THEMES[self._current]

    THEME_LABELS = {
        "dark": "Koyu",
        "light": "Açık",
        "solarized_light": "Solarized Light",
        "dracula": "Dracula",
        "monokai": "Monokai",
        "nord": "Nord",
        "gruvbox": "Gruvbox",
    }

    # Çevrilebilir tema adları
    _TRANSLATABLE = {"dark", "light"}

    # pylupdate6'nın görebileceği explicit çeviri çağrıları
    _I18N_LABELS = [_("Koyu"), _("Açık")]

    def theme_label(self, name: str) -> str:
        label = self.THEME_LABELS.get(name, name)
        if name in self._TRANSLATABLE:
            return _(label)
        return label

    def available_themes(self) -> list[str]:
        return list(THEMES.keys())

    def apply(self, name: str):
        if name not in THEMES or name == self._current:
            return
        self._current = name
        self._settings.setValue("theme", name)
        self.theme_changed.emit(self.theme)
