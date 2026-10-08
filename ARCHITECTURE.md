---
id: eelang-architecture
type: architecture-design
status: draft
title: "eelang architecture: pattern-matching assignment, destructive match, MatchError"
parent: eelang
---

## Drivers

- Форк от ветки CPython 3.15: базовая ревизия — снапшот `3.15.0rc3+dev` от 2026-10-06,
  первый коммит вложенного репозитория `cpython-3.15/`. Требования и границы — в `eelang`.
- Парсер CPython не знает про future-импорты во время разбора: флаги обрабатываются
  после парсинга (`Python/future.c`). Поэтому решение «новый синтаксис или старое
  поведение» не принимается в грамматике, а фиксируется грамматикой как отдельный
  узел и проверяется на этапе компиляции.

## Decisions

### Флаг

- `CO_FUTURE_PATTERN_MATCHING = 0x2000000` в `Include/cpython/compile.h` (бит свободен:
  последний занятый — `CO_FUTURE_ANNOTATIONS` = 0x1000000) и добавление его в
  `PyCF_MASK`. Этого достаточно и для пути `compile(..., flags=...)`: `Python/compile.c`
  сливает `c_future.ff_features | cf_flags`, а `Python/bltinmodule.c` валидирует
  флаги по тому же маску.
- `Lib/__future__.py`: `pattern_matching = _Feature((3, 15, 0, "final", 0), None,
  CO_FUTURE_PATTERN_MATCHING)`; `Python/future.c` — ветка в `future_check_features`,
  ставящая бит. Версионного гейта на `_Feature` в `future.c` нет (захардкожен только
  «braces»), так что запись безопасна и на rc-сборке.
- «Флаг выключен → `SyntaxError`» проверяется в `Python/symtable.c` (`st_future`
  доступен, как для `CO_FUTURE_ANNOTATIONS`) с защитной проверкой в кодогене;
  кодоген читает флаг через `FUTURE_FEATURES(c)`. `ast.parse` остаётся лояльным,
  как и у других future-фич.

### Грамматика: вариант B (старые правила первыми)

В `Grammar/python.gram` в правило `assignment` добавляется альтернатива
`a=patterns '=' b=annotated_rhs !'=' tc=[TYPE_COMMENT]` — после существующих правил
присваивания (включая augassign) и до `invalid_assignment` (PEG ordered choice).

Это работает, потому что в грамматике 3.15 цели `star_target → star_atom` принимают
только NAME, скобочные цели, кортежи и списки целей; литералы, строки, словари,
скобочные выражения и вызовы проваливаются чисто, без raise в action, и доходят
до новой альтернативы:

- `x = v`, `x, *rest = v`, `[x, y] = v`, `a.b = v`, `a[i] = v` — старый путь;
  AST и семантика 1:1, включая List-цели;
- `Point(x, y) = p`, `5 = x`, `(1 | 2) = x`, `{"a": x} = d`, `p as q = v` — `MatchAssign`;
- `x + 1 = y`, `(yield x) = v` и подобное — `invalid_assignment` с сообщениями как
  в CPython (новая альтернатива их не перехватывает).

`!'='` в новой альтернативе сохраняет поведение CPython для `Point(x, y) = p = q`
(остаётся ошибкой); `tc=[TYPE_COMMENT]` — чтобы type-комментарий не оставался
неразобранным.

### AST и кодоген

- `Parser/Python.asdl`: новый stmt-узел `MatchAssign(pattern pattern, expr value)`.
- Узел обходят/печатают `Python/ast_opt.c`, `Python/ast_unparse.c`, `Python/symtable.c`
  (имена в паттерне — Store; переиспользуется обход паттернов из `match`) и
  `Python/codegen.c`.
- Семантика: subject вычисляется один раз; проверка — машинерией
  `codegen_pattern`/`fail_pop`; при провале — `MatchError(subject)`.

### Деструктивный match

- В `codegen_match` при включённом флаге провал всех веток завершается
  `LOAD_GLOBAL MatchError` → `CALL` с subject → `RAISE_VARARGS`. Subject должен быть
  доступен в точке конвергенции провалов (fail_pop его снимает — либо оставить
  на стеке, либо хранить в temp-слоте).

### MatchError

- `Objects/exceptions.c`: `SimpleExtendsException(PyExc_ValueError, MatchError, ...)`
  плюс `ITEM(MatchError)` в `static_exceptions[]` — таблица сама регистрирует
  исключение в builtins, правка `bltinmodule.c` не нужна.
- `Include/pyerrors.h`: `PyAPI_DATA(PyObject *) PyExc_MatchError;`.
- `Lib/test/exception_hierarchy.txt` обновляется (обязательно по комментарию
  в `exceptions.c`).

### Поверхность изменений

| Область | Что меняется |
| --- | --- |
| Грамматика | `Grammar/python.gram` + `make regen-pegen` (после первой сборки) |
| Флаг | `Include/cpython/compile.h`, `Lib/__future__.py`, `Python/future.c` |
| AST и компилятор | `Parser/Python.asdl` + `make regen-ast`, `ast_opt.c`, `ast_unparse.c`, `symtable.c`, `codegen.c` |
| Исключение | `Objects/exceptions.c`, `Include/pyerrors.h`, `exception_hierarchy.txt`, `Doc/` |
| Тесты | новый `Lib/test/test_match_assign.py`; future-тесты в `Lib/test/test_future_stmt/`; `Lib/test/test_syntax.py` — обновить ~30–40 ожидаемых сообщений, которые при выключенном флаге теперь приходят от новой альтернативы |

Порядок сборки: `./configure && make -j` → `regen-pegen` и `regen-ast` → пересборка → тесты.

## Invariants

- Валидный в CPython 3.15 модуль без future-импорта компилируется и исполняется
  идентично CPython 3.15 — включая AST (сверяется `ast.parse`/`compile`).
- `=` никогда не меняет семантику там, где CPython 3.15 принимает левую часть
  как цель присваивания.
- `MatchError` — подкласс `ValueError`; `MatchError.args == (subject,)`.
- Паттерн-присваивание — оператор, не выражение: цепочки вида `q = Point(x, y) = p`
  остаются `SyntaxError` (как и в CPython).

## Out of scope

- Оператор `=>`, расширение `.eel`, смена `sys.implementation.name`, guard-условия
  в левой части `=` — см. не-цели в `eelang`.
