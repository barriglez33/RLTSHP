# Relationship News RSS

A GitHub-online RSS monitor for relationship, dating, romance, psychology, marriage, heartbreak, astrology, horoscope, and advice content.

This repository is designed to run automatically with **GitHub Actions**. You do not need to install Python locally or leave a computer running.

## What it tracks

The project contains **105 search keywords** organized into 8 categories:

1. Dating & Romance
2. Relationship Advice
3. Red Flags & Warning Signs
4. Attachment & Psychology
5. Horoscopes & Astrology
6. Commitment & Marriage
7. Heartbreak & Milestones
8. Columns & Editorial Format

The keyword list is stored in:

```text
config.json
```

## How the monitor works

Every hour, GitHub Actions runs the scanner.

To keep each run fast enough for GitHub Actions, the 105 searches are split into two alternating batches:

```text
Batch 1
Keywords 1–55

Batch 2
Keywords 56–105
```

The sequence is:

```text
Run 1 → Batch 1
Run 2 → Batch 2
Run 3 → Batch 1
Run 4 → Batch 2
...
```

The current batch is remembered automatically in:

```text
data/state.json
```

Do not delete `data/state.json` unless you intentionally want to reset the rotation.

## Rolling two-hour news window

Each run only considers articles published within the previous **2 hours**.

Example:

```text
10:37 run → scans approximately 8:37–10:37
11:37 run → scans approximately 9:37–11:37
12:37 run → scans approximately 10:37–12:37
```

Because the keyword batches alternate, the two-hour rolling window helps prevent gaps between Batch 1 and Batch 2.

Existing URLs are checked against `data/articles.json`, so overlapping time windows do not normally create duplicate RSS entries.

## News discovery

The project uses two free discovery sources:

### GDELT

Used for broad international and multilingual news discovery.

### Google News RSS

Used as an additional source through several editions.

The current configuration checks:

- United States / English
- Mexico / Spanish
- Spain / Spanish
- United Kingdom / English

Google News results are filtered by publication date **before** the program performs expensive URL decoding and article extraction.

That is an important performance optimization.

The logic is:

```text
Google News result
        ↓
Check publication date
        ↓
Older than 2 hours?
   YES → discard immediately
   NO
        ↓
Decode publisher URL
        ↓
Already stored?
   YES → skip
   NO
        ↓
Extract article
```

## Horoscope and astrology searches

Horoscope and astrology searches use special rules because astrology publishers do not always use generic relationship terms in their headlines.

The project expands this category with context such as:

```text
love horoscope
relationship horoscope
dating horoscope
zodiac love
zodiac compatibility
romantic compatibility
astrology love
dating astrology
love tarot
romance tarot
```

This improves discovery for dating horoscopes, love astrology, compatibility stories, tarot, and zodiac relationship content.

## Article extraction

When a fresh URL is found, the program attempts to extract:

- headline
- original article URL
- source
- author
- publication date
- article body
- matched keyword
- category
- discovery source
- source language when available
- source country/edition when available

Extraction is handled with Trafilatura.

Some publishers may block automated extraction, use paywalls, or depend heavily on JavaScript. Those pages may be skipped.

## Automatic Spanish translation

Accepted articles are translated automatically to **Spanish** before they are added to the RSS.

The project keeps both versions.

Example fields in:

```text
data/articles.json
```

include:

```text
original_title
original_body

rss_title
rss_body

translation_status
translated_to
source_detected_language
translation_last_attempt
```

If an article is already in Spanish, it is marked:

```text
already_spanish
```

and is not repeatedly translated on future runs.

If translation succeeds:

```text
translation_status: translated
```

If a translation fails or is incomplete:

```text
translation_status: partial_or_fallback
```

The project can retry a limited number of older incomplete translations on later runs.

The RSS always prefers:

```text
rss_title
rss_body
```

## Source in every RSS title

Every RSS headline includes the publisher/source at the beginning.

Example:

```text
[Psychology Today] 7 señales de que una relación está entrando en una etapa difícil
```

or:

```text
[Cosmopolitan] Estos signos del zodiaco tendrán más suerte en el amor esta semana
```

This makes it easy to identify the origin of a story directly from the feed.

## Duplicate detection

The project performs smart duplicate detection.

It does not only compare URLs.

It also compares:

- publication time
- categories
- matched keywords
- translated headline similarity
- important headline words
- article-body similarity

If several publishers report essentially the same story, the program keeps the version with the most complete information.

Completeness favors things such as:

- longer useful article body
- author information
- source information
- publication metadata
- successful Spanish translation

Discarded duplicate versions can be stored under:

```text
alternate_sources
```

The number of removed repeated versions may appear as:

```text
duplicate_versions_removed
```

## RSS output

The project generates three levels of RSS feeds.

### Master feed

```text
docs/feed.xml
```

Contains all accepted relationship content.

### Category feeds

```text
docs/categories/
```

Examples:

```text
dating-romance.xml
relationship-advice.xml
red-flags-warning-signs.xml
attachment-psychology.xml
horoscopes-astrology.xml
commitment-marriage.xml
heartbreak-milestones.xml
columns-editorial-format.xml
```

### Keyword feeds

```text
docs/keywords/
```

Examples:

```text
relationship-red-flags.xml
love-bombing.xml
dating-apps.xml
attachment-styles.xml
zodiac-compatibility.xml
love-tarot.xml
divorce-news.xml
modern-love.xml
dear-abby.xml
```

## Dashboard

The project also generates:

```text
docs/index.html
```

This provides a simple browser view of recently collected stories and category links.

## GitHub Actions

The workflow file is:

```text
.github/workflows/update.yml
```

The Action appears in GitHub as:

```text
Update Relationship News RSS
```

It runs automatically every hour.

You can also run it manually:

```text
GitHub
→ Actions
→ Update Relationship News RSS
→ Run workflow
```

## Important files

```text
main.py
config.json
requirements.txt
README.md

.github/
└── workflows/
    └── update.yml

data/
├── articles.json
└── state.json

docs/
├── feed.xml
├── index.html
├── categories/
└── keywords/
```

### `main.py`

Handles:

- news discovery
- date filtering
- URL decoding
- article extraction
- translation
- duplicate detection
- RSS generation
- batch rotation

### `config.json`

Contains:

- the 105 keywords
- categories
- Google News editions
- 2-hour rolling window
- search-result limits
- translation settings
- duplicate-detection settings

### `data/articles.json`

Stores collected articles and their metadata.

Do not replace this file when updating the program unless you intentionally want to erase your article history.

### `data/state.json`

Tracks whether the next run should use Batch 1 or Batch 2.

This file is generated automatically.

### `docs/`

Contains generated RSS feeds and the dashboard.

These files are regenerated automatically by the Action.

## Updating the repository

For code/configuration updates, you generally only need to replace:

```text
main.py
config.json
.github/workflows/update.yml
```

Replace `requirements.txt` only when a new Python dependency is added.

Normally, do **not** replace:

```text
data/articles.json
data/state.json
docs/
```

This preserves your existing article history and batch state.

## GitHub Pages

If the repository is public, you can publish the generated feeds through GitHub Pages.

Go to:

```text
Settings
→ Pages
→ Build and deployment
→ Deploy from a branch
```

Choose:

```text
Branch: main
Folder: /docs
```

Then save.

Your master RSS will normally be available at:

```text
https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/feed.xml
```

Category feeds will look like:

```text
https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/categories/horoscopes-astrology.xml
```

Keyword feeds will look like:

```text
https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/keywords/zodiac-compatibility.xml
```

## Performance strategy

The project is intentionally designed to avoid the GitHub Actions timeout that can happen when all 105 searches are processed at once.

Current strategy:

```text
105 total keywords
        ↓
55-keyword batch / 50-keyword batch
        ↓
alternate every hour
        ↓
2-hour rolling publication window
        ↓
reject old Google results before URL decoding
        ↓
open only fresh, previously unseen URLs
        ↓
translate only newly accepted articles
        ↓
limited repair of older failed translations
```

This keeps broad coverage while avoiding unnecessary extraction and translation work.

## Troubleshooting

### The Action says it exceeded the execution time

Check that you are using the current 55/50 alternating batch version and that:

```text
max_age_hours
```

is set to:

```text
2
```

in `config.json`.

Also confirm that `data/state.json` is being committed by GitHub Actions.

### The same batch keeps running every hour

Check that:

```text
data/state.json
```

exists after a successful Action run.

It should contain a value similar to:

```json
{
  "next_batch": 2
}
```

or:

```json
{
  "next_batch": 1
}
```

### Articles are not being translated

Open the GitHub Action run and inspect the translation messages.

Also check `data/articles.json` for:

```text
translation_status
```

Values may include:

```text
translated
already_spanish
partial_or_fallback
```

### Horoscope feed is empty

Make sure the current version includes the special `Horoscopes & Astrology` search rules in `config.json`.

Also remember that each keyword belongs to either Batch 1 or Batch 2, so a specific astrology keyword may only be searched on its corresponding hourly batch.

### An article appears twice

The same URL should normally be skipped automatically.

Different URLs covering the same event are evaluated by smart duplicate detection. Some sufficiently different stories may intentionally remain separate.

## Cost

The project is designed to operate without a paid news API.

Main components:

```text
Google News RSS     Free
GDELT               Free
Trafilatura         Free
deep-translator     Free
GitHub Actions      Within GitHub plan limits
GitHub Pages        Free for eligible public repositories
```

## Current workflow summary

```text
GitHub Action starts
        ↓
Read data/state.json
        ↓
Choose Batch 1 (55) or Batch 2 (50)
        ↓
Search previous 2 hours
        ↓
Discard old results
        ↓
Skip URLs already stored
        ↓
Extract fresh articles
        ↓
Validate keyword/category relevance
        ↓
Translate accepted articles to Spanish
        ↓
Remove repeated coverage
        ↓
Update articles.json
        ↓
Generate master/category/keyword RSS feeds
        ↓
Generate dashboard
        ↓
Switch next batch
        ↓
Commit data + docs + state
```
