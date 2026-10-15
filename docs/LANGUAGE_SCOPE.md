# Language scope

Supported languages: **English (en), Urdu (ur), Spanish (es), Swahili (sw),
Hindi (hi), Arabic (ar)**, plus **code-switched** input (e.g. Roman-Urdu + English),
which is common in Karachi shop chat/scripts.

## Detection
`llm/extraction.py::detect_language` returns `(lang, confidence)`:
* Devanagari script (>= 3 chars) -> `hi`;
* Arabic script -> `ar` vs `ur` by keyword hits;
* otherwise Roman keyword scoring across `ur/es/sw/en`, default `en`.

Script-based detection is high confidence (0.85–0.9); Roman-script detection is lower
(0.6–0.75) because languages share the Latin alphabet.

## Tiers (honest expectations)
| tier | languages | notes |
|---|---|---|
| core | `en`, `ur`, `es`, code-switched | highest accuracy; Urdu is a primary market language |
| extended | `sw`, `hi`, `ar` | supported, expected somewhat lower accuracy (low-resource); script detection is strong |

Both tiers are scored per-language by `eval/harness.py` — see
`per_language_core` vs `per_language_low_resource` in `eval/out/report.json`.

## How multilingual coverage is achieved
* **Keyword tables are per-language and script-aware** (Latin, Arabic, Devanagari) for
  categories, anchors, location hints, income bands, paydays, currencies.
* **Normalizers** handle Arabic-Indic / extended-Arabic / Devanagari digits and
  locale-specific separators (`es`: `.` thousands, `,` decimal).
* **Gazetteer** place names are Latin-script (how Karachi locations are typically typed)
  and are matched within any surrounding-language text.
* **Follow-up questions** and **all assistant answers** are localised in all 6 languages
  (`_FOLLOWUP_Q`, `_T`, `_REASON_LOC`).

## Scope limits (stated honestly)
* The offline **rule** extractor resolves product names only when they appear in Latin
  script; purely in-script product names rely on the live **LLM** path.
* The gazetteer is a small hand-built Karachi set (extendable, [ASSUMPTION]); unknown
  places trigger a follow-up rather than a guess.
* Sentiment/idiom beyond stated facts is out of scope — extraction copies facts only.
