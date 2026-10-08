---
id: eelang
type: goal-and-requirements
status: draft
title: eelang — Erlang-friendly Python fork
---

# eelang — Erlang-friendly Python

Форк ветки CPython 3.15. Синтаксис остаётся питоновским, но `=` расширяется до
паттерн-матчинга, а `match` становится деструктивным: несовпадение — это ошибка,
которую не нужно проверять вручную. Форк приносит в Python принцип «let it crash»
и делается дружественным к проекту [erlang-python](https://github.com/benoitc/erlang-python).

Идентичность форка: расширение исходных файлов остаётся `.py`,
`sys.implementation.name` остаётся `"cpython"` — инструменты CPython работают как есть.
База — ветка 3.15, снапшот `3.15.0rc3+dev` от 2026-10-06 (первый коммит вложенного
репозитория `cpython-3.15/`).

## Фичи

### 1. `=` как паттерн-матчинг

`Point(x, y) = p` — валидный синтаксис. В левой части `=` может стоять всё, что
допускает оператор `match..case`, кроме if-условий.

Аналог из Ruby (только для справки, `=>` не реализуем):

    p => Point(x, y)

### 2. match становится деструктивным

Если не сматчилось ничего — `MatchError`. Чтобы гарантировать отсутствие ошибки,
нужно добавить одним из вариантов неохраняемый `case _:`.
В Ruby оператор case уже деструктивный.

### 3. MatchError

Подкласс `ValueError`, доступен как `builtins.MatchError`. В `args` кладётся
несовпавшее значение (аналог `badmatch` из Erlang).

## Включение фич

И новый синтаксис `=`, и деструктивный `match` включаются только через

    from __future__ import pattern_matching

флаг можно также передать в `compile(src, flags=__future__.pattern_matching.compiler_flag)`.

Без него модуль ведёт себя как чистый CPython 3.15: новый синтаксис даёт
`SyntaxError`, `match` проваливается молча, как раньше.

## Предлагаемая реализация

Для тех случаев, которые в данный момент не приводят к SyntaxError, реализация
`=` остаётся той же. То есть текущий синтаксис должен остаться таким же — это
критерий, по которому решается, когда заменять `=` на match.

Решение «старое поведение vs паттерн-матчинг» принимается на этапе парсинга:
грамматика статична, `patterns '=' rhs` парсится всегда, существующие правила
присваивания идут первыми (PEG ordered choice):

- `=` остаётся обычным присваиванием во всех случаях, где левая часть валидна
  в CPython 3.15: `a.b = v` и `a[i] = v` — запись; `a, *rest = seq` — распаковка
  с `ValueError`; `x = expr` (capture) — обычное присваивание, которое не падает.
- Паттерн-матчинг применяется только когда левая часть не является валидной целью
  присваивания: `Point(x, y) = p`, `5 = x`, `(1, 2) = t`, `(1 | 2) = x`,
  `{"a": x} = d`, `p as q = v`.

Почему это работает без переделки существующих правил: в грамматике 3.15 цели
(`star_target → star_atom`) принимают только NAME, скобочные цели, кортежи и списки
целей; литералы, строки, словари, скобочные выражения и вызовы проваливаются чисто
(без ошибки в action) и доходят до новой альтернативы. Формы, которые не являются
паттернами (`x + 1 = y`, `(yield x) = v`), по-прежнему ловит `invalid_assignment`
с прежними сообщениями.

### План правок в CPython 3.15

- `Grammar/python.gram`: в правило `assignment` добавляется альтернатива
  `a=patterns '=' b=annotated_rhs !'=' tc=[TYPE_COMMENT]` — после существующих правил
  присваивания (включая augassign) и до `invalid_assignment`; затем `make regen-pegen`
  (после первой сборки дерева).
- `Include/cpython/compile.h`: `CO_FUTURE_PATTERN_MATCHING = 0x2000000` и добавить
  его в `PyCF_MASK`.
- `Lib/__future__.py`: `pattern_matching = _Feature((3, 15, 0, "final", 0), None,
  CO_FUTURE_PATTERN_MATCHING)`.
- `Python/future.c`: ветка в `future_check_features`.
- `Parser/Python.asdl`: узел `MatchAssign(pattern pattern, expr value)` +
  `make regen-ast`; обход и печать в `Python/ast_opt.c`, `Python/ast_unparse.c`,
  `Python/symtable.c` (имена паттерна — Store), `Python/codegen.c`.
- `Python/symtable.c`: при выключенном флаге — `SyntaxError` (парсер флаг не знает:
  future-импорты обрабатываются после парсинга); кодоген читает флаг через
  `FUTURE_FEATURES(c)`.
- `Python/codegen.c`: `codegen_match_assign` на базе `codegen_pattern`/`fail_pop` —
  subject вычисляется один раз, при провале `MatchError(subject)`; в `codegen_match`
  при включённом флаге провал всех веток завершается `MatchError(subject)` (subject
  должен остаться доступным в точке конвергенции провалов).
- `Objects/exceptions.c`: `SimpleExtendsException(PyExc_ValueError, MatchError, ...)`
  + `ITEM(MatchError)` в `static_exceptions[]` (регистрация в builtins автоматическая,
  правка bltinmodule.c не нужна); `Include/pyerrors.h`:
  `PyAPI_DATA(PyObject *) PyExc_MatchError;`; обновить
  `Lib/test/exception_hierarchy.txt`.
- Тесты: новый `Lib/test/test_match_assign.py`; future-тесты в
  `Lib/test/test_future_stmt/`; в `Lib/test/test_syntax.py` обновить ~30–40 ожидаемых
  сообщений, которые при выключенном флаге теперь приходят от новой альтернативы;
  документация в `Doc/`.

Порядок сборки: `./configure && make -j` → `regen-pegen` и `regen-ast` → пересборка → тесты.

## Гарантии

- Файл без `from __future__ import pattern_matching` остаётся на 100% валидным
  CPython 3.15 — включая AST: `ast.parse`/`compile` дают то же, что CPython 3.15.
- `=` никогда не меняет семантику там, где CPython 3.15 принимает левую часть
  как цель присваивания.
- Известные ограничения: цепочки вида `q = Point(x, y) = p` остаются `SyntaxError`
  (как и в CPython); гарантию от `MatchError` даёт только неохраняемый `case _:`
  (guard может не сработать); `match` без веток всегда кидает.
