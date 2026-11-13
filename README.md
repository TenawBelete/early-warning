# Early-warning investigation platform, version 0.2

Pick a focal person or body and a question. The engine starts from a base rate and updates it
with dated public evidence, using only what was public on the date you choose. A web app shows
the probability, a range, the evidence behind it, and a scored track record.

**New to this? Open `GUIDE.md`.** It walks you through putting the platform online for free
without installing anything.

## Run it

```
pip install -r requirements.txt
streamlit run app.py                      # the web app
python -m unittest discover -s tests      # 22 tests
python run_all.py                         # all cases, tuning check, forecast log
```

The engine itself needs only Python 3.10+. Streamlit and pandas are for the web app.

## What is in here

| Path | Purpose |
| --- | --- |
| `app.py` | The web app |
| `GUIDE.md` | Beginner's step-by-step guide to free hosting |
| `ew/evidence.py` | Loads evidence and enforces the date gate |
| `ew/graph.py` | Spreads relevance outward from the focus, shrinking per hop |
| `ew/engine.py` | One Bayesian update for any set of competing hypotheses |
| `ew/cases.py` | Loads a case, answers a question, backtests, computes ranges |
| `ew/tune.py` | Fits three global settings across cases and tests them on held-out cases |
| `ew/baseline.py` | "Is this person acting unlike their own normal?" |
| `configs/` | Signal types and their strengths, for geopolitical and corporate questions |
| `cases/iran_2026/`, `cases/nvidia_2026/` | Case definitions and dated evidence |
| `results/` | Run summary and dated forecast logs |

## New: Ask anything (live news)

Type any question about a person, company or country. The app fetches dated public headlines
(Google News, with GDELT as a fallback), tags each one by keyword rules (`ew/live.py`), and runs
them through the same engine. The focus is read week by week; related names are read once and
count half as much. Headlines dated after the chosen cutoff are never used. A kind of story
counts only when it is clearly more common in the last 14 days than in the same name's earlier
coverage; the first version counted every matching headline and pushed famous names to ~100%.

This mode is experimental. Keyword rules misread headlines, the starting value is a judgment,
and nothing in it has been scored against outcomes. The live fetch could not be tested from the
build environment (no access to news sites there); it is tested against recorded sample data.

## What changed in 0.2

- One engine for every case instead of two code paths; the 0.1 numbers reproduce exactly and a
  test pins them.
- Every forecast now comes with a range across nearby engine settings.
- A flag when the evidence barely moves the answer, so a base rate is not mistaken for a finding.
- A watchlist of weak early clues that do not move the probability but deserve a human look.
- A tuning tool with a leave-one-case-out check.
- Cases are validated on load: a typo in a signal type or entity is an error, not a silent skip.
- One data correction in the Nvidia case (see below).

## Honest results

| Case | Question | Brier (lower is better) | Always-50% |
| --- | --- | --- | --- |
| Iran 2026 | Strike within 14 days, 9 cutoffs | 0.163 | 0.25 |
| Nvidia 2026 | Chief executive exits within 30 days, 7 cutoffs | 0.349 | 0.25 |

- **Tuning did not pass its test.** Fitting the three global settings to both cases improves the
  average score in sample (0.256 to 0.191). Fitted on one case and tested on the other, the
  average gets slightly worse (0.256 to 0.267). The defaults are therefore kept. The app offers
  the fitted settings as a clearly labelled option.
- **Nvidia was not predictable beforehand from public data.** The day before the story broke the
  engine said 0.5%. No setting changes that, and it should not.
- **Data correction.** A May 2026 item first coded as an undated investor question is a
  short-seller's published report dated 13 May 2026. Date and reliability were corrected; its
  signal type and strength were not. Effect: Nvidia Brier 0.351 to 0.349.
- Evidence is hand-collected and signal strengths are analyst-set. Two cases are not a track
  record.

## How it really gets better

1. Add past cases, especially ones where tension rose and nothing happened.
2. Re-run `python run_all.py`. When fitted settings beat the defaults on held-out cases, adopt them.
3. Log live forecasts before outcomes and score them.
4. Replace hand-collected evidence with automatic collection.
