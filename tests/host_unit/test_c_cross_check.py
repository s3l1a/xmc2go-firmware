"""Cross-check: compile common/ with a host C compiler and compare the C
known-answer vectors with the Python implementation.

Uses MSVC cl.exe or gcc (whichever is found). Skips with a clear message if no
host C compiler exists, so the suite stays runnable everywhere.
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BAT = os.path.join(HERE, "run_c_vectors.bat")


def _has_compiler():
    from shutil import which
    if which("cl") or which("gcc"):
        return True
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                           "Microsoft Visual Studio", "Installer", "vswhere.exe")
    return os.path.exists(vswhere)


@unittest.skipUnless(_has_compiler(),
                     "no host C compiler (MSVC cl or gcc) on PATH")
class TestCCrossCheck(unittest.TestCase):
    def test_c_vectors_match_python(self):
        proc = subprocess.run([BAT], cwd=HERE, capture_output=True, text=True,
                              timeout=120)
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         "C vector run failed:\n%s" % out)
        self.assertIn("ALL C VECTORS PASS", out)
        # every individual vector must be reported ok
        for name in ("crc16(\"123456789\")", "crc32(\"123456789\")",
                     "rollback.action", "header_valid",
                     "range: bootloader start", "range: config sector CS0 (BMI)"):
            self.assertIn("ok   " + name, out)


if __name__ == "__main__":
    unittest.main()
