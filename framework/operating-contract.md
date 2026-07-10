# Operating Contract — the rules the operator follows mechanically

The model's edge is discipline, not prediction. This contract separates what
is **mechanical** (follow strictly) from what is **inferred** (record and
calibrate, never trust as a floor). The owner accepts high risk tolerance;
these caps are the self-declared limits that make "high risk" survivable.

## Two kinds of numbers

- **Mechanical (binding):** position weights, concentration flags, bear
  stress, entry tranches, invalidation levels. Arithmetic — no opinion
  content. These are what "I control my risk" actually means: size and
  entry price are 100% in the operator's hands.
- **Inferred (calibration targets):** bear/base/bull targets, tier
  probabilities, EV, R/R. A bear target is a *scenario*, never a floor —
  price can and sometimes will trade through it. R/R means "if the
  scenario set is right, the odds look like this," not "this is the most
  I can lose."

## Cadence

- Weekly (or after any ±10% move in a holding): `stocklux refresh` →
  `stocklux quant` → `stocklux portfolio`. Act only on changed bands,
  flags, or fired review triggers — not on mood.
- Every memo write/update ends with `stocklux export <T> --pdf`.
- Quarterly: `stocklux calibrate` + the retrospect playbook.

## Entry rules

1. Buy only at memo entry-plan tranches. A starter above the good-buy
   ceiling is allowed once per name, capped at 1/3 of that name's target
   size, and only when EV is positive.
2. Never add to a name trading above its good-buy ceiling.
3. Tranche fills triggered by a *premium collapse* or a *fired review
   trigger* require re-reading the memo before filling — a cheaper price
   for a broken reason is not a fill.

## Sizing caps (mechanical, non-negotiable)

- Single name ≤ 25% of account at cost of entry.
- One theme/layer group ≤ 60% (owner-declared aggressive setting; the
  tool flags at 40/60).
- Portfolio bear-stress drawdown ≤ 30%: if `stocklux portfolio` stress
  exceeds it, the next action must reduce it, not add to it.

## Exit / defense rules

- Price > 25% above the good-buy ceiling on a held name → trim (the
  methodology's own threshold).
- Invalidation level hit → forced re-analysis within 24h, never an
  automatic sell and never averaging down through it.
- A `warning` flag may only be overridden in writing (one line in the
  next memo's Divergence/notes: what is known that the flag isn't).

## Calibration discipline

- Probabilities and score weights change only via the retrospect playbook
  with calibration evidence (≥20 matured samples for weight changes).
- Until the ledger has depth, treat EV/R:R as ordinal guides (better /
  worse), not as expected returns.
