---
id: eelang-match-case-extension
type: architecture-design
status: draft
title: eelang — расширение match/case (принятый дизайн)
parent: eelang
---

# Расширение match/case — принятый дизайн (ред. 3)

Принят по итогам брейншторма над `history/spec.new.txt` (рабочие заметки —
`.thinkrail/context/TASK-match-case-extension.md`). **Реализация не начата.**

Ред. 3 (09.10.2026): новая версия строится **от `cpython-3.15-fresh`** (пристин
3.15.0rc3+dev) — это отдельное дерево, не поверх текущего форка с future-флагом.

## Решения (закрыты пользователем)

- **Гейт — расширение файла, и только оно.** `.eel` — все eelang-фичи включены
  безусловно; `.py` — чистый CPython 3.15.
- **Future-флага `pattern_matching` в новом дереве нет вовсе**: `from __future__
  import pattern_matching` даёт ошибку «future feature pattern_matching is not
  defined» — и в `.py`, и в `.eel` (естественное поведение future.c; спецкода нет).
- **`match` — жёсткое ключевое слово в `.eel`**: недопустимо как обычное имя.
  Исключения: импорты (`import match`, `from path.match import match as
  other_name`) и позиция атрибута (`obj.match` — после точки токенизатор
  выдаёт NAME, как для прочих ключевых слов).
- **Последовательность в биндинге — только в скобках**: `case (a, b) = c:`
  валидно; `case a, b = c:` — SyntaxError (запятая в списке биндингов —
  всегда разделитель). Аналогично в короткой форме.
- **Jupyter**: ядро eelang компилирует клетки с именем файла `*.eel` — новые
  формы работают в ноутбуке без импортов (небольшой патч ipykernel-слоя).
- `else:` — только в новой форме `match:`; `case _:` остаётся валидным.
- `MatchError.args`: один `=` → само значение; несколько — кортеж субъектов.
- `match def`: матчинг только именованными `=`-формами; `self` — лишь если
  явно назван; параметры — обычные позиционные (аннотации можно), без
  defaults/kw-only/*args/**kwargs.

## Открыто

- [ ] **Судьба B-стейтмента `Point(x, y) = p` в новом дереве**: портировать
      (с гейтом по расширению вместо флага) или не переносить — остаются только
      match/case-формы + `MatchError` + деструктивный `match`.
- [ ] Расположение рабочего дерева v2: ветка от базы в существующем
      `cpython-3.15` (база побайтово равна fresh) или git init прямо
      в `cpython-3.15-fresh`.

## Синтаксис

```python
# 1) match без аргумента (только в .eel)
match:
    case Point(x, y) = p, mode = "special" if x > y:
        ...
    case ...:
        ...
    else:
        ...                     # гарантия от MatchError (только в этой форме)

# 2) короткая форма — стейтмент «связать или упасть»
match Point(x, y) = p, my_var = list() if x > y

# последовательность в биндинге — только в скобках:
match (a, b) = c          # ок
# match a, b = c          # SyntaxError: запятая — разделитель биндингов

# 3) диспетч
match def f(p: Point, mode: str):
    case Point(x, y) = p, "special" = mode if x > y:
        return "special"
    else:
        return "other"
```

## Семантика

- `case P1 = e1, …, Pn = en if g:` ≈ один clause матча на кортеже: субъект —
  кортеж `(e1, …, en)`, паттерн — `(P1, …, Pn)`, guard — `g`. При одном `=`
  кортеж не строится.
- Cases пробуются сверху вниз; субъекты case вычисляются только когда до него
  дошло дело (слева направо); первое совпадение (все `=` + guard) — его тело.
  Провал всех без `else` → `MatchError` (args по правилу выше).
- `else:` = хвостовой неохраняемый `case _:`.
- Короткая форма = `match (e1,…): case (P1,…) if g: pass` — связывает и уходит;
  провал → `MatchError`.
- `match def f(params):` = `def f(params): match: …` — тело функции целиком
  диспетч; имя доступно (рекурсия), `return` работает, self матчится только
  если явно назван.

## Реализация (эскиз)

- База — `cpython-3.15-fresh` (без каких-либо изменений текущего форка).
- Токенизатор: по суффиксу имени файла `.eel` трактует `match` как ключевое
  слово; в `.py` — мягкое, как в CPython. После `.` — всегда NAME.
- Грамматика импортов: `NAME` в правилах импорта → `importable_name: NAME |
  "match"` — карв-аут для py-модулей.
- Регистрация `.eel` в importlib: `Lib/importlib/_bootstrap_external.py`
  (SOURCE_SUFFIXES, path_suffixes FileFinder'а), compileall, тесты.
- Новые формы десахарятся в существующие `Match`/`FunctionDef`; гейт —
  узел-маркер, который в symtable проверяет **расширение файла**.
- `MatchError` — новый подкласс `ValueError` в builtins (как в v1).
- Ядро Jupyter: клетки компилируются с именем `*.eel`.

## Отложено явно

- `else` в классическом `match expr:` — не делаем.
- Неявный кортеж аргументов в case (эрланг-клозы без `=`) — не делаем.
- defaults/kw-only/*args/**kwargs в `match def` — не делаем.
- Future-флаг `pattern_matching` — в новом дереве не вводим вовсе.
