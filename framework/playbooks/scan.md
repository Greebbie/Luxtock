# Playbook: Watchlist Scan

Read `framework/methodology.md` first (it governs output discipline). This
playbook is a light, fast pass answering one question: **which names need to
be re-analyzed, and why.** It does not perform deep analysis itself. Write the
report in English.

## Steps

1. Read `data/watchlist.json`, `data/quotes.json`, and the frontmatter of the
   latest memo for each ticker.
2. For each ticker, check four things:
   - **Price deviation**: current price vs. `price_at_analysis` deviating by
     >15%?
   - **Trigger hit**: search online quickly for news on this ticker over the
     last two weeks — has the event described in `review_trigger` happened?
   - **Staleness**: is the memo more than 30 days old?
   - **Targets expired**: has the memo's `price_targets.horizon` elapsed
     (memo date + horizon ≤ today)? Expired targets don't force a re-analysis
     by themselves, but flag them — they are due for the retrospect playbook
     (`/lux-retrospect`), which is how the framework calibrates itself.
3. For the watchlist as a whole, check one thing: has there been major
   layer-level news for the underlying thesis (something that affects the
   whole layer, not just one ticker — e.g. a key raw-material contract price
   shift or new export-control rules)?

## Output

Do not write memo files. Output a table directly to the user:

| ticker | needs rerun? | reason (deviation X% / trigger hit: … / N days stale / targets expired / none) |

Plus one summary line: which 1–2 tickers to rerun first and why they are most
urgent. Names with `holding: true` outrank non-held names at equal urgency —
a stale call on something the user owns is the more expensive mistake. If
any memos have expired price targets, add one line suggesting `/lux-retrospect`.
If everything is normal, state explicitly "no action needed from this scan."
