"""Запуск .eel-файла: ``python -m eelang script.eel``."""

import sys
from pathlib import Path

from . import parse


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m eelang FILE.eel", file=sys.stderr)
        return 2
    path = Path(argv[0])
    source = path.read_text()
    mod = parse(source, filename=str(path))
    code = compile(mod, str(path), "exec")
    sys.path.insert(0, str(path.parent))
    namespace = {"__name__": "__main__", "__file__": str(path)}
    exec(code, namespace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
