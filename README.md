# Relationship News RSS

GitHub-online-only RSS monitor built from **105 keywords** across **8 categories**.

Features:
- multilingual discovery with GDELT + Google News
- automatic Spanish translation
- source included in every title, e.g. `[Psychology Today] ...`
- smart duplicate detection across sources/languages
- keeps the most complete repeated version
- master feed + category feeds + keyword feeds
- GitHub Actions every hour at minute `:37`

Workflow: `.github/workflows/update.yml`

Generated: `docs/feed.xml`, `docs/categories/*.xml`, `docs/keywords/*.xml`, `docs/index.html`, `data/articles.json`.
