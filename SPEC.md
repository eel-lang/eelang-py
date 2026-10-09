---
id: eelang
type: goal-and-requirements
status: active
title: eelang — Erlang-friendly Python fork
---

# eelang — Erlang-friendly Python

Форк ветки CPython 3.15. Синтаксис остаётся питоновским, но `=` расширяется до
паттерн-матчинга, а `match` становится деструктивным: несовпадение — это ошибка,
которую не нужно проверять вручную. Форк приносит в Python принцип «let it crash»
и делается дружественным к проекту [erlang-python](https://github.com/benoitc/erlang-python).

Идентичность форка: текущая версия работает на `.py`,
`sys.implementation.name` остаётся `"cpython"` — инструменты CPython работают как есть.
Для следующей версии принят переход на расширение `.eel` как гейт фич
(см. `eelang-match-case-extension`).
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

Важное следствие: так как `assignment` пробуется для **каждого** оператора,
вложенный разбор паттернов не должен «ронять» парсинг исключением из action для
валидных выражений. Поэтому `_PyPegen_ensure_imaginary`/`_PyPegen_ensure_real`
изменены: вместо `SyntaxError` они проваливают правило чисто (NULL без ошибки) —
иначе `f(1-1, -0o2)` абортился бы на class-паттерне раньше, чем дошло бы до
парсинга выражения. Валидные комплексные паттерны (`case 1-2j:`) не затронуты;
сообщение «imaginary number required…» для ошибочных паттернов в `match` заменяется
на «invalid syntax» (тестами не зафиксировано).

### План правок в CPython 3.15

- `Grammar/python.gram`: в правило `assignment` добавляется альтернатива
  `a=patterns '=' b=annotated_rhs !'=' tc=[TYPE_COMMENT]` — после существующих правил
  присваивания (включая augassign) и до `invalid_assignment`; затем `make regen-pegen`
  (после первой сборки дерева). Дополнительно в `as_pattern` добавляется вариант цели
  `match_assign_as_target` (`NAME !('.' | '(') &'='`), чтобы `p as q = v` разбирался
  как MatchAssign — обычные guard'ы `!'='` у capture/value-паттернов при этом
  сохраняются (иначе ломается match: позиционные паттерны начинали глотать
  keyword-имена, см. `TI(T.OP, string=...)` в `Lib/_pyrepl/utils.py`).
- `Include/cpython/code.h`: `CO_FUTURE_PATTERN_MATCHING = 0x10000000` —
  не 0x2000000: биты 0x2000000–0x8000000 заняты (`CO_NO_MONITORING_EVENTS`,
  `CO_HAS_DOCSTRING`, `CO_METHOD`); флаг добавить в `PyCF_MASK` в
  `Include/cpython/compile.h`.
- `Lib/__future__.py`: `pattern_matching = _Feature((3, 15, 0, "final", 0), None,
  CO_FUTURE_PATTERN_MATCHING)`.
- `Python/future.c`: ветка в `future_check_features`.
- `Parser/Python.asdl`: узел `MatchAssign(pattern pattern, expr value)` +
  `make regen-ast`; в 3.15 обвязка такая: `Python/ast.c` (валидация),
  `Python/ast_preprocess.c` (fold), `Lib/_ast_unparse.py` (`visit_MatchAssign`;
  `Python/ast_opt.c` в 3.15 нет — оптимизатор AST убран, а `Python/ast_unparse.c`
  занимается только аннотациями), `Python/symtable.c` (имена паттерна — Store),
  `Python/codegen.c`. `Lib/ast.py` править не нужно — классы узлов приходят из `_ast`.
- `Python/symtable.c`: при выключенном флаге — `SyntaxError` (парсер флаг не знает:
  future-импорты обрабатываются после парсинга); кодоген читает флаг через
  `FUTURE_FEATURES(c)`.
- `Python/codegen.c`: `codegen_match_assign` на базе `codegen_pattern`/`fail_pop` —
  subject вычисляется один раз, при провале `MatchError(subject)`; в `codegen_match`
  при включённом флаге провал всех веток завершается `MatchError(subject)` (subject
  должен остаться доступным в точке конвергенции провалов). Имя `MatchError`
  грузится напрямую через `ADDOP_NAME_CUSTOM(... LOAD_GLOBAL ..., 1, 1)`
  (канонический `LOAD_GLOBAL` с NULL-битом), а **не** через `codegen_nameop`:
  `MatchError` отсутствует в symbol table, и внутри функции `codegen_nameop`
  сгенерировал бы `LOAD_NAME`, который в функциональном фрейме умирает с
  `SystemError: no locals found` (LOCALS() == NULL).
- `Objects/exceptions.c`: `SimpleExtendsException(PyExc_ValueError, MatchError, ...)`
  + `ITEM(MatchError)` в `static_exceptions[]` (регистрация в builtins автоматическая,
  правка bltinmodule.c не нужна); `Include/pyerrors.h`:
  `PyAPI_DATA(PyObject *) PyExc_MatchError;`; обновить
  `Lib/test/exception_hierarchy.txt`.
- Тесты: новый `Lib/test/test_match_assign.py`; future-тесты в
  `Lib/test/test_future_stmt/`; в `Lib/test/test_syntax.py` обновлены 22 ожидаемых
  сообщения, которые при выключенном флаге теперь приходят от новой альтернативы;
  в `Lib/test/test_capi/test_run.py` сниппет `SYNTAX_ERROR` заменён на чисто
  парсерную ошибку (бывший `True = 1` теперь валидный синтаксис, а ошибки стадии
  компиляции в интерактивном режиме получают синтетическое имя файла
  `<имя>-N` из `pythonrun.c` — унаследованное поведение CPython, см. `nonlocal x`);
  `MatchError` добавлен в skip-list маппинга `_compat_pickle` в
  `Lib/test/test_pickle.py` (как другие новые исключения, напр. `BaseExceptionGroup`).

Порядок сборки: `./configure && make -j` → `regen-pegen` и `regen-ast` → пересборка → тесты.

## Гарантии

- Файл без `from __future__ import pattern_matching` остаётся на 100% валидным
  CPython 3.15 — включая AST: `ast.parse`/`compile` дают то же, что CPython 3.15.
- `=` никогда не меняет семантику там, где CPython 3.15 принимает левую часть
  как цель присваивания.
- Известные ограничения: цепочки вида `q = Point(x, y) = p` остаются `SyntaxError`
  (как и в CPython); гарантию от `MatchError` даёт только неохраняемый `case _:`
  (guard может не сработать).
