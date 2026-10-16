"""Дополнительные тесты eelang: API парсера, edge-кейсы паттернов, пайплайны, рантайм.

Максимально разнообразные сценарии поверх базового сьюта (test_eelang.py).
"""

import ast
import pickle
import threading
import unittest

import eelang
from eelang import MatchError


def run(source, ns=None):
    if ns is None:
        ns = {}
    mod = eelang.parse(source, "<eelang-extra>")
    exec(compile(mod, "<eelang-extra>", "exec"), ns)
    return ns


def parse_error(source):
    with unittest.TestCase().assertRaises(SyntaxError):
        eelang.parse(source, "<eelang-extra>")


class ParseApiTests(unittest.TestCase):
    """API парсера: режимы, ошибки, позиции."""

    def test_eval_mode(self):
        m = eelang.parse("1 + 2", mode="eval")
        self.assertIsInstance(m, ast.Expression)

    def test_single_mode(self):
        m = eelang.parse("x = 1", mode="single")
        self.assertIsInstance(m, ast.Interactive)

    def test_positions(self):
        m = eelang.parse("x = 1\ny = x\n")
        self.assertEqual(m.body[1].lineno, 2)
        self.assertEqual(m.body[0].lineno, 1)

    def test_bad_mode_string(self):
        with self.assertRaises(ValueError):
            eelang.parse("1", mode="bogus")

    def test_non_str_source(self):
        with self.assertRaises(TypeError):
            eelang.parse(123)

    def test_null_byte_source(self):
        with self.assertRaises(ValueError):
            eelang.parse("a\x00b")

    def test_non_str_filename(self):
        with self.assertRaises(TypeError):
            eelang.parse("1", filename=42)

    def test_error_filename_in_message(self):
        with self.assertRaises(SyntaxError) as cm:
            eelang.parse("if True print(1)", "myfile.eel")
        self.assertIn("myfile.eel", str(cm.exception))


class SupersetTests(unittest.TestCase):
    """eelang — чистое надмножество: стоковый Python обязан работать как есть."""

    def test_plain_match_statement(self):
        ns = {}
        run("""
match 5:
    case 5:
        out = 'five'
    case _:
        out = 'other'
""", ns)
        self.assertEqual(ns["out"], "five")

    def test_walrus_assert_is_plain_assert(self):
        # `assert (x := 5)` — обычный assert с walrus, не паттерн
        # (bare `assert x := 5` — SyntaxError, как и в стоковом Python).
        ns = {}
        run("assert (x := 5)\n", ns)
        self.assertEqual(ns["x"], 5)

    def test_except_star(self):
        ns = {}
        run("""
try:
    raise ExceptionGroup('grp', [ValueError('x')])
except* ValueError:
    caught = True
""", ns)
        self.assertTrue(ns["caught"])

    def test_tstring_parses(self):
        # 3.15 t-строки — стоковая фича, должны парситься.
        m = eelang.parse("x = t'hello'")
        self.assertEqual(type(m.body[0].value).__name__, "TemplateStr")

    def test_unicode_identifiers(self):
        ns = {}
        run("сумма = 40\nсумма = сумма + 2\nassert сумма = 42\n", ns)
        self.assertEqual(ns["сумма"], 42)

    def test_type_params(self):
        ns = {}
        run("""
def identity[T](x: T) -> T:
    return x
""", ns)
        self.assertEqual(ns["identity"](42), 42)
        self.assertEqual(ns["identity"]("s"), "s")


class AssertPatternExtraTests(unittest.TestCase):
    """Edge-кейсы assert-паттернов."""

    def test_mapping_pattern(self):
        ns = {}
        run("assert {'k': v, **rest} = {'k': 1, 'x': 2}\n", ns)
        self.assertEqual(ns["v"], 1)
        self.assertEqual(ns["rest"], {"x": 2})

    def test_or_pattern(self):
        ns = {}
        run("x = 2\nassert (1 | 2) = x\n", ns)
        with self.assertRaises(MatchError):
            run("x = 3\nassert (1 | 2) = x\n", {})

    def test_as_pattern(self):
        ns = {}
        run("assert ([a, b] as pair) = [1, 2]\n", ns)
        self.assertEqual(ns["pair"], [1, 2])
        self.assertEqual((ns["a"], ns["b"]), (1, 2))

    def test_star_sequence(self):
        ns = {}
        run("assert (a, *rest) = (1, 2, 3, 4)\n", ns)
        self.assertEqual(ns["a"], 1)
        # star-capture в sequence-паттерне биндится списком (как в стоковом match)
        self.assertEqual(ns["rest"], [2, 3, 4])

    def test_signed_numbers(self):
        run("x = -5\nassert -5 = x\ny = 5\nassert +5 = y\n")

    def test_complex_literal(self):
        run("z = 1 + 2j\nassert 1 + 2j = z\n")

    def test_bytes_and_none_patterns(self):
        run("x = b'ab'\nassert b'ab' = x\ny = None\nassert None = y\n")

    def test_class_keyword_pattern(self):
        ns = {}
        run("""
from dataclasses import dataclass
@dataclass
class P:
    x: int
    y: int
p = P(1, 5)
assert P(x=1, y=y) = p
""", ns)
        self.assertEqual(ns["y"], 5)

    def test_nested_class_pattern(self):
        ns = {}
        run("""
from dataclasses import dataclass
@dataclass
class P:
    x: int
    y: int
@dataclass
class Line:
    a: P
    b: P
line = Line(P(1, 2), P(3, 4))
assert Line(P(x1, y1), P(x2, y2)) = line
""", ns)
        self.assertEqual((ns["x1"], ns["y1"], ns["x2"], ns["y2"]), (1, 2, 3, 4))

    def test_wildcard_in_class_pattern(self):
        ns = {}
        run("""
from dataclasses import dataclass
@dataclass
class P:
    x: int
    y: int
p = P(7, 8)
assert P(x, _) = p
""", ns)
        self.assertEqual(ns["x"], 7)

    def test_multi_failure_args_tuple_of_subjects(self):
        with self.assertRaises(MatchError) as cm:
            run("a = 1\nb = 2\nassert 5 = a, 6 = b\n")
        self.assertEqual(cm.exception.args, ((1, 2),))

    def test_deep_nesting(self):
        ns = {}
        run("assert (a, (b, (c, d))) = (1, (2, (3, 4)))\n", ns)
        self.assertEqual((ns["a"], ns["b"], ns["c"], ns["d"]), (1, 2, 3, 4))

    def test_builtin_class_pattern(self):
        run("assert str() = 's'\n")
        with self.assertRaises(MatchError):
            run("assert str() = 5\n", {})

    def test_refutable_dot0_leak_documented(self):
        # Рефьютабельный паттерн использует `.0` — имя видно в locals()
        # (задокументированный трейдофф десахара).
        ns = {}
        run("assert int() = 5\n", ns)
        self.assertIn(".0", ns)
        self.assertEqual(ns[".0"], 5)

    def test_guard_with_as_binding(self):
        ns = {}
        run("assert (n as m) = 5 if n > 0\n", ns)
        self.assertEqual(ns["n"], 5)
        self.assertEqual(ns["m"], 5)


class MatchDefExtraTests(unittest.TestCase):
    """Дополнительные сценарии match def."""

    def test_multi_param(self):
        ns = {}
        run("""
match def add(a, b):
    case int() = a, int() = b:
        return a + b
""", ns)
        self.assertEqual(ns["add"](2, 3), 5)
        with self.assertRaises(MatchError) as cm:
            ns["add"](1, "x")
        self.assertEqual(cm.exception.args, ((1, "x"),))

    def test_varargs_rejected(self):
        parse_error("match def f(*args):\n    case 1 = args:\n        return 1\n")

    def test_kwonly_rejected(self):
        parse_error("match def f(x, *, y):\n    case 1 = x:\n        return 1\n")

    def test_union_annotation(self):
        ns = {}
        run("""
match def f(v) -> int | None:
    case int() = v:
        return v
    else:
        return None
""", ns)
        self.assertEqual(ns["f"](5), 5)
        self.assertIsNone(ns["f"]("a"))

    def test_nested_in_function(self):
        ns = {}
        run("""
def outer(x):
    match def inner(v):
        case int() = v:
            return v * 2
        else:
            return 0
    return inner(x)
""", ns)
        self.assertEqual(ns["outer"](21), 42)
        self.assertEqual(ns["outer"]("no"), 0)

    def test_mutual_recursion(self):
        ns = {}
        run("""
match def is_even(n: int):
    case 0 = n:
        return True
    case _ = n:
        return is_odd(n - 1)
match def is_odd(n: int):
    case 0 = n:
        return False
    case _ = n:
        return is_even(n - 1)
""", ns)
        self.assertTrue(ns["is_even"](10))
        self.assertFalse(ns["is_even"](7))

    def test_guard_only_first_clause(self):
        ns = {}
        run("""
match def sign(x):
    case if x > 0:
        return 'pos'
    case _ = x:
        return 'neg'
""", ns)
        self.assertEqual(ns["sign"](5), "pos")
        self.assertEqual(ns["sign"](-1), "neg")


class PipelineExtraTests(unittest.TestCase):
    """Дополнительные сценарии пайплайнов."""

    def test_mixed_kwargs_value_last_positional(self):
        # v ..f(args, kw) == f(args..., v, **kw)
        ns = {}
        run("def f(a, b, c): return (a, b, c)\nr = 3 ..f(1, c=2)\n", ns)
        self.assertEqual(ns["r"], (1, 3, 2))

    def test_match_mapping_pattern(self):
        ns = {}
        run("""
v =
    {'k': 42, 'extra': 1}
    ..match:
        case {'k': k, **rest}:
            (k, rest)
        case _:
            None
""", ns)
        self.assertEqual(ns["v"], (42, {"extra": 1}))

    def test_match_class_pattern(self):
        ns = {}
        run("""
from dataclasses import dataclass
@dataclass
class P:
    x: int
    y: int
v =
    P(3, 4)
    ..match:
        case P(x, y) if x < y:
            x * y
        case _:
            0
""", ns)
        self.assertEqual(ns["v"], 12)
        self.assertEqual((ns["x"], ns["y"]), (3, 4))

    def test_match_catchall_guard(self):
        ns = {}
        run("""
subject = 5
v =
    subject
    ..match:
        case _ if subject > 10:
            'big'
        case _:
            'small'
subject2 = 15
w =
    subject2
    ..match:
        case _ if subject2 > 10:
            'big'
        case _:
            'small'
""", ns)
        self.assertEqual(ns["v"], "small")
        self.assertEqual(ns["w"], "big")

    def test_assert_inline_form(self):
        # ..assert: с паттерном на той же строке.
        ns = {}
        run("""
from dataclasses import dataclass
@dataclass
class P:
    x: int
    y: int
v =
    P(3, 4)
    ..assert: P(x, y)
""", ns)
        self.assertEqual((ns["x"], ns["y"]), (3, 4))
        self.assertEqual((ns["v"].x, ns["v"].y), (3, 4))

    def test_assert_failure_subject_arg(self):
        with self.assertRaises(MatchError) as cm:
            run("""
from dataclasses import dataclass
@dataclass
class P:
    x: int
    y: int
p =
    42
    ..assert:
        P(x, y)
""")
        self.assertEqual(cm.exception.args, (42,))

    def test_long_inline_chain(self):
        ns = {}
        run("""
def inc(x): return x + 1
v = 0 ..inc() ..inc() ..inc() ..inc() ..inc() ..inc() ..inc() ..inc() ..inc() ..inc()
""", ns)
        self.assertEqual(ns["v"], 10)

    def test_mixed_chain_map_match_assert(self):
        ns = {}
        run("""
def sq(x): return x * x
v =
    [1, 2, 3]
    ..map(sq)
    ..list()
    ..match:
        case [a, b, c] if a < b:
            a + b + c
        case _:
            0
    ..assert:
        n
""", ns)
        self.assertEqual(ns["v"], 14)
        self.assertEqual(ns["n"], 14)
        self.assertEqual((ns["a"], ns["b"], ns["c"]), (1, 4, 9))

    def test_sorted_with_key(self):
        ns = {}
        run("v = [3, 1, 2] ..sorted(key=lambda x: -x)\n", ns)
        self.assertEqual(ns["v"], [3, 2, 1])


class MiscRuntimeTests(unittest.TestCase):
    """Рантайм: pickle, потоки, крупный модуль, независимость парсов."""

    def test_match_error_pickle(self):
        e = pickle.loads(pickle.dumps(MatchError("no match")))
        self.assertIsInstance(e, MatchError)
        self.assertEqual(e.args, ("no match",))

    def test_threaded_parses(self):
        errors = []
        src = "assert (x, y) = (1, 2)\n"

        def worker():
            try:
                for _ in range(50):
                    m = eelang.parse(src, "<thread>")
                    ns = {}
                    exec(compile(m, "<thread>", "exec"), ns)
                    if ns["x"] != 1 or ns["y"] != 2:
                        raise AssertionError("wrong bindings")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_big_module(self):
        lines = []
        for i in range(1000):
            lines.append(f"v{i} = {i}")
            lines.append(f"assert {i} = v{i}")
        src = "\n".join(lines) + "\n"
        ns = {}
        run(src, ns)
        self.assertEqual(ns["v0"], 0)
        self.assertEqual(ns["v999"], 999)
        # рефьютабельные паттерны оставляют служебное `.0`, exec добавляет
        # `__builtins__` — считаем только переменные v{...}
        self.assertEqual(sum(1 for k in ns if k.startswith("v")), 1000)

    def test_repeated_parse_independence(self):
        src = "assert x = 1\n"
        ns1, ns2 = {}, {}
        exec(compile(eelang.parse(src, "<t>"), "<t>", "exec"), ns1)
        exec(compile(eelang.parse(src, "<t>"), "<t>", "exec"), ns2)
        self.assertEqual(ns1["x"], 1)
        self.assertEqual(ns2["x"], 1)
        self.assertIsNot(ns1, ns2)


if __name__ == "__main__":
    unittest.main()


class BarePipelineTests(unittest.TestCase):
    """Голый многострочный пайплайн без присваивания (побочные эффекты)."""

    def test_bare_pipeline_with_assert(self):
        ns = {}
        run("""
class Response:
    def __init__(self, status):
        self.status = status
def httpee():
    return {"url": "http://x"}
def GET(u, resp):
    assert u == "http://target"
    return Response(200)
url = "http://target"
httpee()
..GET: url
..assert:
    Response(status=200)
""", ns)
        self.assertTrue(ns["Response"])

    def test_bare_pipeline_assert_failure(self):
        with self.assertRaises(MatchError):
            run("""
class Response:
    def __init__(self, status):
        self.status = status
def f():
    return Response(404)
f()
..assert:
    Response(status=200)
""")

    def test_bare_call_chain_side_effects(self):
        ns = {}
        run("""
log = []
def a(x):
    log.append('a')
    return x + 1
def b(x):
    log.append('b')
    return x * 2
a(1)
..b()
..a()
""", ns)
        self.assertEqual(ns["log"], ["a", "b", "a"])

    def test_bare_call_chain_no_temp_leak(self):
        ns = {}
        run("def f(x): return x + 1\nf(1)\n..f()\n", ns)
        self.assertNotIn(".0", ns)

    def test_bare_pipeline_inside_function(self):
        ns = {}
        run("""
def f(x):
    return x + 1
def run(v):
    v
    ..f()
    ..f()
""", ns)
        self.assertEqual(ns["f"](1), 2)  # смоук: функция определилась

    def test_bare_pipeline_with_match_step(self):
        ns = {}
        run("""
def f():
    return [1, 2, 3]
f()
..match:
    case [a, b, c]:
        (a, b, c)
    case _:
        'no'
""", ns)
        self.assertEqual((ns["a"], ns["b"], ns["c"]), (1, 2, 3))

    def test_bare_pipeline_dot0_leaks_with_block_steps(self):
        # statement-шаги несут значение через `.0` — оно видно в locals()
        ns = {}
        run("def f(): return 5\nf()\n..assert:\n    n\n", ns)
        self.assertEqual(ns[".0"], 5)
        self.assertEqual(ns["n"], 5)

    def test_plain_statements_still_work_after_bare_pipeline(self):
        ns = {}
        run("def f(x): return x + 1\nf(1)\n..f()\ny = 10\nz = y + 1\n", ns)
        self.assertEqual(ns["z"], 11)
