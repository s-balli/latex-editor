"""latex_utils.py — strip_comments doğrudan testleri."""

from core.latex_utils import strip_comments


class TestStripCommentsBasic:
    def test_no_comments(self):
        assert strip_comments("Hello World") == "Hello World"

    def test_full_line_comment(self):
        assert strip_comments("% bu bir yorum") == ""

    def test_inline_comment(self):
        assert strip_comments(r"\textbf{kalın} % yorum") == r"\textbf{kalın} "

    def test_empty_string(self):
        assert strip_comments("") == ""

    def test_only_whitespace_before_comment(self):
        assert strip_comments("    % yorum") == "    "

    def test_multiple_lines(self):
        text = "satir 1\n% yorum\nsatir 3"
        assert strip_comments(text) == "satir 1\n\nsatir 3"


class TestEscapedPercent:
    def test_escaped_percent_preserved(self):
        assert strip_comments(r"\% 50 indirim") == r"\% 50 indirim"

    def test_escaped_percent_with_comment(self):
        assert strip_comments(r"\% 50 % yorum") == r"\% 50 "

    def test_double_backslash_percent(self):
        # \\ kaçışı + % yorum
        assert strip_comments(r"\\% yorum") == r"\\"

    def test_triple_backslash_percent(self):
        assert strip_comments(r"\\\% kalı") == r"\\\% kalı"

    def test_only_escaped_percent(self):
        assert strip_comments(r"\%") == r"\%"


class TestEdgeCases:
    def test_percent_at_start(self):
        assert strip_comments("%yorum") == ""

    def test_consecutive_percents(self):
        # ilk % yorum başlatır
        assert strip_comments("%%yorum") == ""

    def test_no_trailing_newline(self):
        assert strip_comments("text") == "text"

    def test_indentation_preserved(self):
        assert strip_comments("    \\item bir % yorum") == "    \\item bir "

    def test_turkish_characters(self):
        assert strip_comments("Türkçe metin % yorum") == "Türkçe metin "

    def test_backslash_before_non_special(self):
        assert strip_comments(r"\textbf{a}") == r"\textbf{a}"

    def test_multiple_escaped_percents(self):
        assert strip_comments(r"\%10\%20 % yorum") == r"\%10\%20 "
