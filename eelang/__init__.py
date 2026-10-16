"""eelang — надмножество Python 3.15: паттерн-матчинг в присваиваниях, match def, пайплайны."""

import ast

__all__ = ["MatchError", "parse"]
__version__ = "0.1.5"

_MODES = {"exec": 257, "eval": 258, "single": 256}

try:
    from . import _parser
except ImportError as exc:
    raise ImportError(
        "eelang._parser не загрузился. Расширение требует CPython 3.15, "
        "собранный с --enable-shared (интерпретатор должен экспортировать "
        f"внутренние символы парсера). Оригинальная ошибка: {exc}"
    ) from exc


class MatchError(ValueError):
    """Провал паттерн-матчинга (assert-паттерн, match def или ..assert:)."""


def parse(source, filename="<eel>", mode="exec"):
    """Разобрать eelang-исходник в ``ast.AST``.

    ``mode`` — ``"exec"`` (по умолчанию), ``"eval"`` или ``"single"``.
    """
    if mode not in _MODES:
        raise ValueError(f"unknown mode: {mode!r}")
    return _parser.parse(source, filename, _MODES[mode])


def _check_abi():
    """Быстрый отказ при несовпадении ABI расширения с рантаймом.

    Расширение читает позиции таблицы интернированных идентификаторов
    (_Py_ID) из libpython хоста. Сборка 3.15.x со сдвинутой таблицей молча
    выдаёт не те идентификаторы (в разработке наблюдалось
    ``__import__`` -> ``__imul__``) и AST-узлы без полей (``_field_types``).
    Probe-парс проверяет оба пути.
    """
    probe = "assert int() = __eelang_abi_probe__"
    detail = ""
    ok = False
    try:
        mod = _parser.parse(probe, "<eelang-abi-probe>", 257)
        names = {n.id for n in ast.walk(mod) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(mod) if isinstance(n, ast.Attribute)}
        consts = {n.value for n in ast.walk(mod) if isinstance(n, ast.Constant)}
        ok = (
            "__import__" in names
            and ".0" in names
            and "MatchError" in attrs
            and "eelang" in consts
        )
    except Exception as exc:
        detail = repr(exc)
    if not ok:
        raise RuntimeError(
            "eelang: таблица интернированных идентификаторов этого CPython "
            "не совпадает с той, под которую собрано расширение — отказ, "
            "чтобы не получить молча неверные результаты. Нужен CPython "
            "3.15.0 без патчей внутренних идентификаторов."
            + (f" Probe: {detail}" if detail else "")
        ) from None


_check_abi()
