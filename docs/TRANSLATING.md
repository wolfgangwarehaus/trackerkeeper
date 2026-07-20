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
