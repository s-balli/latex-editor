"""input_parser modülü testleri."""

import os
import pytest

from core.input_parser import parse_inputs, group_by_directory
from core.latex_utils import strip_comments as _strip_comments


# --- strip_comments ---


class TestStripComments:
    def test_no_comments(self):
        assert _strip_comments("hello world") == "hello world"

    def test_full_line_comment(self):
        result = _strip_comments("% yorum\nhello")
        assert result == "\nhello"

    def test_inline_comment(self):
        result = _strip_comments("kod % yorum")
        assert result == "kod "

    def test_escaped_percent(self):
        result = _strip_comments(r"\% yüzde")
        assert r"\%" in result

    def test_empty_string(self):
        assert _strip_comments("") == ""

    def test_backslash_before_percent(self):
        result = _strip_comments(r"\\% yorum")
        assert "%" not in result


# --- parse_inputs ---


class TestParseInputs:
    def test_empty_content(self):
        assert parse_inputs("", "/tmp") == []

    def test_single_input(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content")
        result = parse_inputs("\\input{chapter1}", str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "chapter1.tex"

    def test_single_include(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content")
        result = parse_inputs("\\include{chapter1}", str(tmp_path))
        assert len(result) == 1

    def test_missing_extension(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content")
        result = parse_inputs("\\input{chapter1}", str(tmp_path))
        assert result[0]["name"] == "chapter1.tex"

    def test_explicit_extension(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content")
        result = parse_inputs("\\input{chapter1.tex}", str(tmp_path))
        assert len(result) == 1

    def test_empty_ref_skipped(self, tmp_path):
        result = parse_inputs("\\input{}", str(tmp_path))
        assert result == []

    def test_nested_input(self, tmp_path):
        c = tmp_path / "c.tex"
        c.write_text("leaf content")
        b = tmp_path / "b.tex"
        b.write_text("\\input{c}")
        result = parse_inputs("\\input{b}", str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "b.tex"
        assert len(result[0]["children"]) == 1
        assert result[0]["children"][0]["name"] == "c.tex"

    def test_circular_reference(self, tmp_path):
        a = tmp_path / "a.tex"
        b = tmp_path / "b.tex"
        a.write_text("\\input{b}")
        b.write_text("\\input{a}")
        result = parse_inputs("\\input{a}", str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "a.tex"
        # b -> a cycle prevented
        assert len(result[0]["children"]) == 1

    def test_path_traversal_blocked(self, tmp_path):
        result = parse_inputs("\\input{../../etc/passwd}", str(tmp_path))
        assert result == []

    def test_nonexistent_file_skipped(self, tmp_path):
        result = parse_inputs("\\input{nonexistent}", str(tmp_path))
        assert result == []

    def test_multiple_inputs(self, tmp_path):
        for name in ("ch1.tex", "ch2.tex", "ch3.tex"):
            (tmp_path / name).write_text("content")
        result = parse_inputs(
            "\\input{ch1}\n\\input{ch2}\n\\input{ch3}", str(tmp_path)
        )
        assert len(result) == 3

    def test_comment_input_ignored(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content")
        result = parse_inputs("% \\input{chapter1}", str(tmp_path))
        assert result == []

    def test_space_before_brace(self, tmp_path):
        chapter = tmp_path / "chapter1.tex"
        chapter.write_text("content")
        result = parse_inputs("\\input {chapter1}", str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "chapter1.tex"


# --- group_by_directory ---


class TestGroupByDirectory:
    def test_empty_list(self):
        assert group_by_directory([], "/tmp") == []

    def test_all_in_root(self, tmp_path):
        refs = [
            {"name": "a.tex", "path": str(tmp_path / "a.tex")},
            {"name": "b.tex", "path": str(tmp_path / "b.tex")},
        ]
        result = group_by_directory(refs, str(tmp_path))
        assert len(result) == 2
        assert all(not r.get("is_dir") for r in result)

    def test_subdirectory_grouped(self, tmp_path):
        sub = tmp_path / "chapters"
        refs = [
            {"name": "ch1.tex", "path": str(sub / "ch1.tex")},
        ]
        result = group_by_directory(refs, str(tmp_path))
        assert len(result) == 1
        assert result[0].get("is_dir") is True
        assert result[0]["name"] == "chapters"

    def test_mixed_root_and_subdir(self, tmp_path):
        sub = tmp_path / "chapters"
        refs = [
            {"name": "main.tex", "path": str(tmp_path / "main.tex")},
            {"name": "ch1.tex", "path": str(sub / "ch1.tex")},
        ]
        result = group_by_directory(refs, str(tmp_path))
        # root file first, then dir group
        assert len(result) == 2
        assert not result[0].get("is_dir")
        assert result[1].get("is_dir") is True

    def test_nested_children(self, tmp_path):
        sub = tmp_path / "chapters"
        refs = [
            {
                "name": "ch1.tex",
                "path": str(sub / "ch1.tex"),
                "children": [
                    {"name": "sec1.tex", "path": str(sub / "sec1.tex")},
                ],
            },
        ]
        result = group_by_directory(refs, str(tmp_path))
        assert result[0]["is_dir"] is True
        # children within the dir group
        assert len(result[0]["children"]) == 1
