"""paths.py — Windows/WSL yol dönüşüm testleri."""

from core.paths import windows_to_wsl, wsl_to_windows


class TestWindowsToWsl:
    def test_c_drive(self):
        assert windows_to_wsl(r"C:\Users\test") == "/mnt/c/Users/test"

    def test_d_drive(self):
        assert windows_to_wsl(r"D:\Projects\file.tex") == "/mnt/d/Projects/file.tex"

    def test_lowercase_drive(self):
        assert windows_to_wsl(r"e:\data") == "/mnt/e/data"

    def test_no_drive(self):
        assert windows_to_wsl("relative/path.txt") == "relative/path.txt"

    def test_already_forward_slash(self):
        assert windows_to_wsl("C:/Users/test") == "/mnt/c/Users/test"

    def test_root_drive(self):
        assert windows_to_wsl("C:\\") == "/mnt/c/"

    def test_single_letter_no_colon(self):
        assert windows_to_wsl("C") == "C"

    def test_empty_string(self):
        assert windows_to_wsl("") == ""

    def test_unc_path(self):
        assert windows_to_wsl(r"\\server\share\file") == "//server/share/file"

    def test_spaces_in_path(self):
        assert windows_to_wsl(r"C:\My Files\doc.tex") == "/mnt/c/My Files/doc.tex"


class TestWslToWindows:
    def test_c_drive(self):
        assert wsl_to_windows("/mnt/c/Users/test") == r"C:\Users\test"

    def test_d_drive(self):
        assert wsl_to_windows("/mnt/d/data/file.tex") == r"D:\data\file.tex"

    def test_uppercase_drive(self):
        assert wsl_to_windows("/mnt/E/temp") == r"E:\temp"

    def test_root_path(self):
        assert wsl_to_windows("/mnt/c/") == "C:\\"

    def test_not_wsl_path(self):
        assert wsl_to_windows("/home/user/file") == "/home/user/file"

    def test_empty_string(self):
        assert wsl_to_windows("") == ""

    def test_spaces_in_path(self):
        assert wsl_to_windows("/mnt/c/My Files/doc.tex") == r"C:\My Files\doc.tex"

    def test_mnt_without_drive(self):
        assert wsl_to_windows("/mnt/") == "/mnt/"


class TestRoundTrip:
    def test_windows_roundtrip(self):
        original = r"C:\Users\test\document.tex"
        assert wsl_to_windows(windows_to_wsl(original)) == original

    def test_wsl_roundtrip(self):
        original = "/mnt/c/Users/test/document.tex"
        assert windows_to_wsl(wsl_to_windows(original)) == original
