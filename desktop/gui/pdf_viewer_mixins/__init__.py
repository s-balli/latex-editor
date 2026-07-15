"""PdfViewer mixin'leri — her dosya bir sorumluluk alanı taşır."""

from gui.pdf_viewer_mixins._bookmarks import PdfBookmarksMixin
from gui.pdf_viewer_mixins._search import PdfSearchMixin
from gui.pdf_viewer_mixins._selection import PdfSelectionMixin
from gui.pdf_viewer_mixins._highlight import PdfHighlightMixin
from gui.pdf_viewer_mixins._synctex import PdfSyncTexMixin
from gui.pdf_viewer_mixins._ui_setup import PdfUISetupMixin
from gui.pdf_viewer_mixins._render import PdfRenderMixin
from gui.pdf_viewer_mixins._navigation import PdfNavigationMixin
from gui.pdf_viewer_mixins._presentation import PdfPresentationMixin
from gui.pdf_viewer_mixins._events import PdfEventsMixin
