# RISC-V Radar Frontend Direction

## Product Shape

The site should feel like an industry analyst dashboard, not a blog. The first screen should show the daily briefing immediately: top signals, category counts, and the freshness of the data.

## Primary Views

- Daily Briefing: top 8-12 items ranked by relevance.
- Category Lanes: News, Papers, Startups, Markets, Technology.
- Entity Watch: SiFive, Andes, Ventana, Tenstorrent, SpacemiT, StarFive, Codasip, and similar companies.
- Topic Watch: Vector, Linux, LLVM, GCC, OpenSBI, AI accelerator, automotive MCU, chiplets.
- Archive: daily JSON-backed history.

## Visual Language

- Dense but calm information layout.
- Neutral background with crisp separators.
- Accent colors should distinguish signal types, not decorate the page.
- Cards only for individual repeated news items.
- Avoid marketing hero composition; the tool itself is the first screen.

## Recommended Components

- Header with date, run status, total items, and source warnings.
- Filter bar with category tabs, source selector, and topic chips.
- Ranked signal list with title, source, date, summary, tags, and source link.
- Sidebar or right rail for companies and hot topics.
- Archive timeline by date.

## Next Implementation Step

Move from the current generated static page to a small client-side app shell:

- Keep JSON as the data contract.
- Render filters and search in the browser.
- Add `Pagefind` later for full archive search.
