# Translating a dough app

dough carries Qt's standard translation layer (lifted from jellytoast's #232
work), so every loaf gets i18n for free. English is the source language; every
other language is a catalog pair in `dough/i18n/`:

- `dough_<code>.ts` — the editable XML catalog translators work on
- `dough_<code>.qm` — the compiled binary the app actually loads

(In a fork, `dough new`'s identity replace renames both the package and the
catalog basenames to the fork's slug.)

The app picks a language at startup (`run_app` → `dough.i18n.install`): the
**Settings → Language** override if set, otherwise the system locale. English
needs no catalog — untranslated strings always fall back to the English source
text, so a partially-translated catalog is fine to ship. Bare dough ships no
catalogs (`SHIPPED_LANGUAGES` is empty) and hides the Language row until a
fork adds one.

## Starting a new language

```bash
dev/update_translations.sh fr     # bootstraps dough_fr.ts + fills it
```

Then translate (below), and add the language to `SHIPPED_LANGUAGES` in
`dough/i18n/__init__.py` (code, English name, native name) — the Settings
dropdown builds itself from that list and appears once it's non-empty.

## Improving an existing language

1. Open `dough/i18n/dough_<code>.ts` in **Qt Linguist** (`pyside6-linguist`,
   installed with the dev venv) or any text editor. Each `<message>` pairs a
   `<source>` English string with a `<translation>`.
2. Keep `{0}`-style placeholders exactly as they appear — they're filled at
   runtime (`.format(...)`).
3. Compile: `dev/update_translations.sh` (recompiles every `.qm`).
4. Run the app in your language to eyeball it: pick the language in Settings,
   restart.
5. Commit **both** the `.ts` and the `.qm` (the `.qm` ships as package data).

## For developers: keeping strings translatable

- Wrap user-facing strings in `self.tr("...")` (QObject subclasses) or
  `QCoreApplication.translate("Context", "...")`.
- No f-strings inside `tr()` — use placeholders:
  `self.tr("Couldn't reach the server: {0}").format(msg)`.
- Don't translate product names or URL/technical placeholders.
- Strings evaluated at module import time (constant label lists, identity /
  persisted values) install BEFORE the translators and won't translate —
  restructure to a key/label split or lazy evaluation first.
- After adding or changing strings, run `dev/update_translations.sh` so every
  catalog picks up the new sources (existing translations are preserved;
  changed strings show as "unfinished" until retranslated).

## Numbers, dates, sizes — route through `dough.i18n.fmt`

Never f-string a number/date/size into a user-visible string — `f"{n}"` bakes
English separators ("1,234.5") that read wrong in most locales (German:
"1.234,5"). Use the helpers in `dough/i18n/fmt.py` (`fmt_int`, `fmt_decimal`,
`fmt_percent`, `fmt_datetime`, `fmt_duration`, `fmt_file_size`) and drop the
result into a translated template:

```python
label.setText(self.tr("{0} items · {1}").format(fmt_int(count),
                                                fmt_duration(secs)))
```

Everything there is a thin `QLocale` veneer except `fmt_duration` — Qt has no
native duration formatter, so it's hand-rolled from translated unit strings
with plural forms (below).

## Plurals (numerus forms)

Languages disagree on how many plural classes exist (Spanish 2, Arabic 6…),
so a count-bearing string can't be an `if n == 1` in code. The idiom:

```python
self.tr("%n file(s)", "", n)          # on a QObject subclass
```

`%n` is replaced with the count at runtime; the catalog carries one
`<numerusform>` per plural class of the language and `QTranslator` picks the
right one from CLDR rules. Untranslated, the English source falls through
with `%n` substituted.

Two rules, both verified against pyside6 6.x (see
`tests/test_i18n_plurals.py`, which compiles a live Spanish catalog):

- **The string must go through `self.tr(source, disambiguation, n)` on a
  QObject.** pyside6-lupdate's Python parser only emits
  `<message numerus="yes">` for that exact shape — the free-function
  `QCoreApplication.translate(ctx, source, disamb, n)` extracts as a plain
  (non-plural) message, even though it *resolves* numerus fine at runtime.
  That's why `fmt.py` wraps its unit strings in the `_DurationUnits` QObject.
- **Translators fill every `<numerusform>`** lupdate scaffolds (it emits the
  right count for the catalog's language) — an empty form falls back to the
  English source for that plural class only.
