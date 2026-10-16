import glob
import os
import sys
import sysconfig

from setuptools import Extension, setup

ROOT = os.path.dirname(os.path.abspath(__file__))

# The extension is compiled against CPython 3.15 internals and reads _Py_ID
# identifier positions from the host libpython: refuse to build elsewhere.
if sys.version_info[:2] != (3, 15):
    raise SystemExit(
        "eelang requires CPython 3.15 to build: the C extension is tied to "
        f"3.15 internal headers (got {sys.version.split()[0]})."
    )
if not sysconfig.get_config_var("Py_ENABLE_SHARED"):
    print(
        "WARNING: building against a non-shared (static) CPython; the "
        "resulting extension will only import if the interpreter exports "
        "its internal parser symbols (_PyArena_New, _PyThreadState_GetCurrent, "
        "_PyUnicode_InternImmortal).",
        file=sys.stderr,
    )

parser_sources = (
    [os.path.join(ROOT, "csrc", "_parser.c")]
    + sorted(glob.glob(os.path.join(ROOT, "csrc", "Parser", "*.c")))
    + sorted(glob.glob(os.path.join(ROOT, "csrc", "Parser", "lexer", "*.c")))
    + sorted(glob.glob(os.path.join(ROOT, "csrc", "Parser", "tokenizer", "*.c")))
    + sorted(glob.glob(os.path.join(ROOT, "csrc", "Python", "*.c")))
)

setup(
    ext_modules=[
        Extension(
            "eelang._parser",
            sources=parser_sources,
            include_dirs=[
                os.path.join(ROOT, "csrc", "Include"),
                os.path.join(ROOT, "csrc", "Include", "internal"),
            ],
            define_macros=[("Py_BUILD_CORE", "1"), ("Py_BUILD_CORE_MODULE", "1")],
            extra_compile_args=["-O2", "-fvisibility=hidden"],
        )
    ]
)
