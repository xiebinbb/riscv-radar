# RISC-V Radar

RISC-V Radar is a small static intelligence briefing for public RISC-V signals: news, papers, companies, markets, and engineering activity. It is designed to run daily on GitHub Actions and publish with GitHub Pages.

## Local run

```bash
export PYTHONPYCACHEPREFIX=/tmp/riscv-radar-pycache
python scripts/collect.py
MINIMAX_API_KEY=your_key python scripts/translate.py
python scripts/build_site.py
python -m http.server 8080 --directory dist
```

Open `http://localhost:8080`.

## What it collects

- RSS and Atom feeds from RISC-V, semiconductor, Linux, and embedded sources.
- arXiv metadata through the public arXiv API.
- GitHub repository metadata through GitHub Search.
- Market sources are configured as optional placeholders. Use a reliable finance API such as Alpha Vantage, Finnhub, or Polygon before enabling automated market collection.

The collector stores normalized records in `data/daily/YYYY-MM-DD.json` and the static site in `dist/`.
The translation step adds Chinese titles, summaries, and editorial takeaways while preserving the original source fields and links.
The Obsidian export creates `obsidian-vault/daily/YYYY-MM-DD.md` and updates `obsidian-vault/index.md` for local indexing and search.

For GitHub Actions, configure the repository secret `MINIMAX_API_KEY`. The workflow uses the China-region endpoint `https://api.minimaxi.com/v1` and model `MiniMax-M3`.

## Obsidian

Open `/Users/xiebinbb/github/riscv-radar/obsidian-vault/` as an Obsidian vault. After each daily workflow, pull the repository and Obsidian will index the new Markdown note locally.

To build the newest local note manually:

```bash
python scripts/build_obsidian.py
```

## Add sources

Edit `config/sources.json`. Prefer RSS or official APIs before direct website scraping.

## GitHub setup

1. Create an empty GitHub repository, for example `riscv-radar`.
2. Push this project to the repository.
3. In repository settings, enable GitHub Pages with GitHub Actions as the source.
4. Run the `Daily RISC-V Radar` workflow manually once.

The workflow is scheduled at `20 0 * * *` UTC, roughly 08:20 in Beijing time.

## Legal and quality notes

Keep the site as a source-linked briefing, not a reposting site. Store titles, URLs, short public summaries, metadata, and your own commentary. Avoid copying full articles.
