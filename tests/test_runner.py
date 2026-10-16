"""Tests for the ``python -m eelang`` runner."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def run_eelang(*args, input_text=None):
    return subprocess.run(
        [sys.executable, "-m", "eelang", *args],
        capture_output=True,
        encoding="utf-8",  # явно: локаль хоста может быть не UTF-8
        input=input_text,
        cwd=tempfile.gettempdir(),  # вдали от исходников пакета
    )


class RunnerTests(unittest.TestCase):
    def test_file_run(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.eel"
            p.write_text("print('hello')\n")
            r = run_eelang(str(p))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, "hello\n")

    def test_argv_passthrough(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.eel"
            p.write_text("import sys\nprint(sys.argv)\n")
            r = run_eelang(str(p), "a", "b")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, f"['{p}', 'a', 'b']\n")

    def test_c_command(self):
        r = run_eelang("-c", "print(1 + 2)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "3\n")

    def test_stdin(self):
        r = run_eelang("-", input_text="print(40 + 2)\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "42\n")

    def test_coding_cookie(self):
        # PEP 263: latin-1 файл с coding cookie должен читаться корректно.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.eel"
            p.write_bytes(b"# -*- coding: latin-1 -*-\nprint('caf\xe9')\n")
            r = run_eelang(str(p))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, "caf\u00e9\n")

    def test_missing_file(self):
        r = run_eelang("/no/such/file.eel")
        self.assertEqual(r.returncode, 2)
        self.assertIn("can't open file", r.stderr)

    def test_syntax_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.eel"
            p.write_text("assert x = \n")
            r = run_eelang(str(p))
            self.assertEqual(r.returncode, 1)
            self.assertIn("bad.eel", r.stderr)

    def test_syntax_error_clean_no_traceback(self):
        # Синтакс-ошибка печатается одной строкой, без сырого traceback'а.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.eel"
            p.write_text("assert 5 = x, 'msg'\n")
            r = run_eelang(str(p))
            self.assertEqual(r.returncode, 1)
            self.assertTrue(r.stderr.startswith("eelang:"), r.stderr)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
