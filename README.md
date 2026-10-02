# Relationship News — High Recall Update

The 55/50 alternating batch model is preserved.

New discovery model:
- inspect up to 25 Google News RSS entries per keyword
- process max 6 fresh unseen Google articles per keyword
- request up to 15 GDELT results
- process max 6 fresh unseen GDELT articles
- rolling window increased to 3 hours
- tighter 24-hour smart deduplication

Translation target remains **English**.

Replace `main.py`, `config.json`, and `README.md`.
