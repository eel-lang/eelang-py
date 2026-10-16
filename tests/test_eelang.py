"""Tests for eelang: assert-patterns, match def, and pipelines.

Ported from the fork's regression suite (Lib/test/test_eelang_v3.py) and
adapted for the package: stock CPython cannot parse eelang syntax, so every
snippet goes through eelang.parse() + compile() + exec().
"""

import unittest

import eelang
from eelang import MatchError


def run(source, ns=None):
    """Parse eelang source with the C parser and exec it."""
    if ns is None:
        ns = {}
    mod = eelang.parse(source, "<eelang-test>")
    exec(compile(mod, "<eelang-test>", "exec"), ns)
    return ns


def parse_error(source):
    """Assert the eelang parser raises SyntaxError for source."""
    with unittest.TestCase().assertRaises(SyntaxError):
        eelang.parse(source, "<eelang-test>")


class MatchErrorTests(unittest.TestCase):
    def test_subclass(self):
        self.assertTrue(issubclass(MatchError, ValueError))

    def test_message(self):
        with self.assertRaises(MatchError) as cm:
            raise MatchError("no match")
        self.assertEqual(cm.exception.args, ("no match",))


class AssertPatternTests(unittest.TestCase):
    def test_capture(self):
        ns = {}
        run("x = 5\nassert x = 5\n", ns)
        self.assertEqual(ns["x"], 5)

    def test_wildcard(self):
        run("assert _ = 42\n")

    def test_literal(self):
        run("x = 5\nassert 5 = x\n")

    def test_sequence(self):
        ns = {}
        run("assert (x, y) = (1, 2)\n", ns)
        self.assertEqual((ns["x"], ns["y"]), (1, 2))

    def test_class_pattern(self):
        ns = {}
        run("""
from dataclasses import dataclass
@dataclass
class P:
    x: int
    y: int
p = P(3, 4)
assert P(x, y) = p
""", ns)
        self.assertEqual((ns["x"], ns["y"]), (3, 4))

    def test_multiple_bindings(self):
        ns = {}
        run("a = 1\nb = 2\nassert 1 = a, 2 = b if a < b\n", ns)
        self.assertEqual((ns["a"], ns["b"]), (1, 2))

    def test_failure_raises_matcherror(self):
        with self.assertRaises(MatchError):
            run("x = 6\nassert 5 = x\n")

    def test_failure_args_are_subject(self):
        with self.assertRaises(MatchError) as cm:
            run("x = 6\nassert 5 = x\n")
        self.assertEqual(cm.exception.args, (6,))

    def test_guard_failure(self):
        with self.assertRaises(MatchError):
            run("x = 5\nassert x = 5 if x > 10\n")

    def test_subject_evaluated_once(self):
        ns = {}
        run("""
from eelang import MatchError
log = []
def f():
    log.append('f')
    return 6
try:
    assert 5 = f()
except MatchError:
    pass
""", ns)
        self.assertEqual(len(ns["log"]), 1)

    def test_plain_assert_intact(self):
        with self.assertRaises(AssertionError):
            run("assert 1 == 2, 'msg'\n")

    def test_survives_optimize(self):
        # Pattern-asserts desugar to `match`, so bytecode optimization (-O)
        # must not strip them (unlike plain `assert`).
        code = compile(eelang.parse("x = 6\nassert 5 = x\n"),
                       "<t>", "exec", optimize=1)
        with self.assertRaises(MatchError):
            exec(code, {})

    def test_multiple_patterns_in_one_module(self):
        # Regression: several pattern-asserts in one module must not crash
        # (the single shared synthetic `.0` temp is reused safely).
        ns = {}
        run("assert a = 1\nassert b = 2\nassert (x, y) = (3, 4)\n", ns)
        self.assertEqual((ns["a"], ns["b"]), (1, 2))
        self.assertEqual((ns["x"], ns["y"]), (3, 4))

    def test_match_error_not_shadowed(self):
        # A user variable named MatchError must not break the raise: the
        # desugar resolves the exception via __import__('eelang').MatchError.
        ns = {}
        run("MatchError = 1\n", ns)
        with self.assertRaises(eelang.MatchError) as cm:
            run("assert 5 = 6\n", ns)
        self.assertEqual(cm.exception.args, (6,))

    def test_irrefutable_no_temp_leak(self):
        # Irrefutable patterns (bare capture/wildcard, no guard) desugar to a
        # plain `match e: case P: pass`, so no `.0` temp leaks into the scope.
        ns = {}
        run("""
def f():
    assert x = 1
    return [k for k in dir() if k.startswith('.')]
class A:
    assert y = 2
""", ns)
        self.assertEqual(ns["f"](), [])
        self.assertEqual([k for k in ns["A"].__dict__ if k.startswith('.')], [])


class MatchDefTests(unittest.TestCase):
    def test_recursion(self):
        ns = {}
        run("""
match def fib(n: int):
    case 0 = n:
        return 0
    case 1 = n:
        return 1
    case _ = n:
        return fib(n - 1) + fib(n - 2)
""", ns)
        self.assertEqual(ns["fib"](10), 55)

    def test_guard_and_else(self):
        ns = {}
        run("""
match def f(p):
    "docstring."
    case (x, y) = p if x > y:
        return 'below'
    else:
        return 'other'
""", ns)
        self.assertEqual(ns["f"]((5, 3)), "below")
        self.assertEqual(ns["f"]((2, 9)), "other")
        self.assertEqual(ns["f"].__doc__, "docstring.")

    def test_no_else_raises_matcherror(self):
        ns = {}
        run("""
match def f(x: int):
    case 1 = x:
        return 'one'
""", ns)
        with self.assertRaises(MatchError):
            ns["f"](99)

    def test_defaults_rejected(self):
        parse_error("match def g(x=1):\n    case 1 = x:\n        return 'one'\n")

    def test_self_must_be_named(self):
        ns = {}
        run("""
class Shape:
    match def describe(self, p):
        case (x, y) = p if x > y:
            return 'below'
        case (x, y) = p:
            return 'other'
""", ns)
        self.assertEqual(ns["Shape"]().describe((3, 2)), "below")

    def test_guard_only_clause(self):
        ns = {}
        run("""
match def power(x: int, n: int):
    case (_, 0) = (x, n):
        return 1
    case if n % 2 == 0:
        return power(x * x, n // 2)
    case _ = n:
        return x * power(x * x, n // 2)
""", ns)
        self.assertEqual(ns["power"](2, 10), 1024)
        self.assertEqual(ns["power"](3, 5), 243)

    def test_guard_only_clause_rejected_elsewhere(self):
        # guard-only клоз разрешён только в match def
        for src in ("match 5:\n    case if True:\n        pass\n",
                    "v =\n    5\n    ..match:\n        case if True:\n            1\n",
                    "assert if True\n"):
            parse_error(src)


class PipelineTests(unittest.TestCase):
    def test_inline_call(self):
        ns = {}
        run("x = [1,2,3] ..len()\n", ns)
        self.assertEqual(ns["x"], 3)

    def test_inline_call_args(self):
        ns = {}
        run("def add(a, b): return a + b\nx = 10 ..add(5)\n", ns)
        self.assertEqual(ns["x"], 15)

    def test_inline_block(self):
        ns = {}
        run("def mul(a, b): return a * b\nx = 3 ..mul: 4\n", ns)
        self.assertEqual(ns["x"], 12)

    def test_inline_chain(self):
        ns = {}
        run("""
def f(x): return x + 1
def g(x): return x * 2
x = 5 ..f() ..g()
""", ns)
        self.assertEqual(ns["x"], 12)

    def test_block_form(self):
        ns = {}
        run("""
def square(x): return x * x
def is_even(x): return x % 2 == 0
value =
    [1, 2, 3, 4, 5]
    ..map(square)
    ..filter(is_even)
""", ns)
        self.assertEqual(list(ns["value"]), [4, 16])

    def test_block_same_line(self):
        ns = {}
        run("""
def f(x): return x * 2
value = [1, 2, 3]
    ..map(f)
""", ns)
        self.assertEqual(list(ns["value"]), [2, 4, 6])

    def test_block_form_block_expr(self):
        ns = {}
        run("""
value =
    [1, 2, 3]
    ..map: lambda n: n * 10
    ..filter: lambda n: n > 10
""", ns)
        self.assertEqual(list(ns["value"]), [20, 30])

    def test_method_chain(self):
        ns = {}
        run("""
value =
    [3, 1, 2]
    .sort()
""", ns)
        self.assertIsNone(ns["value"])

    def test_keyword_args(self):
        ns = {}
        run("def f(a, b): return a + b\nx = 1 ..f(b=2)\n", ns)
        self.assertEqual(ns["x"], 3)

    def test_value_as_last_argument(self):
        # v ..f(a, b) == f(a, b, v)
        ns = {}
        run("def f(a, b, c): return (a, b, c)\nx = 3 ..f(1, 2)\n", ns)
        self.assertEqual(ns["x"], (1, 2, 3))

    def test_block_expr_next_line(self):
        # ..map: с телом на следующей строке
        ns = {}
        run("""
def sq(x): return x * x
v =
    [1, 2, 3]
    ..map:
        lambda x: x * x
""", ns)
        self.assertEqual(list(ns["v"]), [1, 4, 9])

    def test_match_step(self):
        ns = {}
        run("""
v =
    [1, 2, 3]
    ..match:
        case [a, b, c] if a < b:
            a + b + c
        case _:
            0
""", ns)
        self.assertEqual(ns["v"], 6)
        self.assertEqual((ns["a"], ns["b"], ns["c"]), (1, 2, 3))

    def test_match_step_same_line_body(self):
        ns = {}
        run("""
v =
    5
    ..match:
        case 5: 'five'
        case _: 'other'
""", ns)
        self.assertEqual(ns["v"], "five")

    def test_match_step_guard(self):
        ns = {}
        run("""
v =
    7
    ..match:
        case n if n > 5:
            n * 10
        case _:
            -1
""", ns)
        self.assertEqual(ns["v"], 70)

    def test_match_step_no_match_unchanged(self):
        # обычный питоновский match: нет совпадения → значение не меняется,
        # ошибки нет (не MatchError).
        ns = {}
        run("""
v =
    99
    ..match:
        case 1: 'one'
""", ns)
        self.assertEqual(ns["v"], 99)

    def test_assert_step_binds(self):
        ns = {}
        run("""
from dataclasses import dataclass
@dataclass
class Point:
    x: int
    y: int
p =
    Point(3, 4)
    ..assert:
        Point(x, y)
""", ns)
        self.assertEqual((ns["x"], ns["y"]), (3, 4))

    def test_assert_step_failure(self):
        with self.assertRaises(MatchError):
            run("""
from dataclasses import dataclass
@dataclass
class Point:
    x: int
    y: int
p =
    42
    ..assert:
        Point(x, y)
""")

    def test_steps_local_scope_in_function(self):
        ns = {}
        run("""
def f():
    v =
        5
        ..match:
            case n if n > 0:
                n * 100
            case _:
                -1
        ..assert:
            x
    return v, x
""", ns)
        self.assertEqual(ns["f"](), (500, 500))
        self.assertNotIn("v", ns)
        self.assertNotIn("x", ns)

    def test_block_form_arbitrary_targets(self):
        # Блочная форма работает с любым assignment-таргетом (attr/subscript/unpack).
        ns = {}
        run("""
class O: pass
obj = O()
obj.attr =
    [1, 2, 3]
    ..len()
d = {}
d[0] =
    [1, 2, 3]
    ..len()
a, b =
    [10, 20]
    ..map(lambda x: x + 1)
    ..list()
head, *rest =
    [1, 2, 3, 4]
    ..map(lambda x: x * 10)
    ..list()
""", ns)
        self.assertEqual(ns["obj"].attr, 3)
        self.assertEqual(ns["d"][0], 3)
        self.assertEqual((ns["a"], ns["b"]), (11, 21))
        self.assertEqual((ns["head"], ns["rest"]), (10, [20, 30, 40]))


if __name__ == "__main__":
    unittest.main()
