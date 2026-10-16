"""Запуск eelang-кода.

python -m eelang script.eel [args...]
python -m eelang -c 'code' [args...]
python -m eelang -          # код из stdin
"""

import io
import sys
import tokenize
from pathlib import Path

from . import parse


def _decode_source(data, filename):
    """Decode bytes honoring a PEP 263 coding cookie (like CPython)."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    except SyntaxError as exc:
        raise SyntaxError(f"invalid encoding declaration in '{filename}': {exc}") from exc
    return data.decode(encoding)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    if not argv:
        print("usage: python -m eelang script.eel [args...]", file=sys.stderr)
        print("       python -m eelang -c 'code' [args...]", file=sys.stderr)
        print("       python -m eelang -", file=sys.stderr)
        return 2

    if argv[0] == "-c":
        if len(argv) < 2:
            print("eelang: argument expected for the -c option", file=sys.stderr)
            return 2
        source = argv[1]
        filename = "<string>"
        script_args = argv[2:]
    elif argv[0] == "-":
        source = sys.stdin.read()
        filename = "<stdin>"
        script_args = argv[1:]
    else:
        filename = argv[0]
        script_args = argv[1:]
        try:
            data = Path(filename).read_bytes()
        except OSError as exc:
            print(f"eelang: can't open file '{filename}': {exc.strerror}",
                  file=sys.stderr)
            return 2
        try:
            source = _decode_source(data, filename)
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"eelang: {exc}", file=sys.stderr)
            return 1

    try:
        mod = parse(source, filename)
    except SyntaxError as exc:
        # Сообщение парсера уже содержит файл и строку.
        print(f"eelang: {exc}", file=sys.stderr)
        return 1

    code = compile(mod, filename, "exec")

    if filename not in ("<string>", "<stdin>"):
        sys.path.insert(0, str(Path(filename).resolve().parent))
    sys.argv = [filename] + script_args
    namespace = {"__name__": "__main__"}
    if filename not in ("<string>",):
        namespace["__file__"] = filename
    exec(code, namespace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
