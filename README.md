# Product Hunter 🐾

**An AI research agent that finds winning dropshipping products on Instagram and Facebook, checks if they are still selling, and turns them into niche versions you can sell without competing with the original seller.**

Built on [Claude Code](https://claude.com/claude-code). You talk to it with short commands like `/hunt` or `/check-product <link>`, and it does the research in your browser, scores the product, and writes a report.

It is made for one kind of business: **organic Instagram / Facebook Reels (no paid ads), selling mostly to the US.**

---

## Contents
1. [What it does](#what-it-does)
2. [The method: 3 checks](#the-method-3-checks)
3. [Setup (5 minutes)](#setup-5-minutes)
4. [Commands](#commands)
5. [Weekly routine](#weekly-routine)
6. [How it learns](#how-it-learns)
7. [Folder structure](#folder-structure)
8. [Scripts](#scripts)
9. [Safety rules](#safety-rules)
10. [FAQ](#faq)

---

## What it does

```
  Find            Check              Niche it             Test & learn
 ───────►  ─────────────────►  ──────────────────►  ─────────────────────►
 /hunt     /check-product        /niche               /log-result
 scans     3 checks + score      3–5 niche versions   your real results
 Reels,    → WINNER / watch /    + price + hooks      make the next
 hashtags, niche-only / skip                          scores better
 Ad Library
```

- **Finds** product reels that are going viral right now.
- **Checks** if the product really sold, and if the seller's page is still alive.
- **Scores** it from 0 to 100 (the *Winner Score*) with a confidence level.
- **Niches** it: same proven idea, but for a specific buyer and problem, so you are not copying the original.
- **Tracks** competitor pages over time: heating up, steady, or dying?
- **Compares** your own page with rivals, and with itself last week.
- **Learns** from your real test results.

---

## The method: 3 checks

Every product is judged on three simple questions. A product must pass all three to be a **WINNER**.

| # | Check | How the agent measures it | Pass |
|---|---|---|---|
| 1 | **It already sold a lot** | Reel views, "link / price / where to buy" comments, other sellers, ads running 30+ days, order counts | At least 2 kinds of proof |
| 2 | **The page's videos still get views** | *Momentum* = median views of reels 3–10 days old ÷ reels 11–45 days old. Plus any recent outlier reel | Momentum ≥ 0.6, or a reel from the last 14 days at 3× the page median |
| 3 | **The owner is still posting** | Days since the last post, posts in the last 14 days | Last post ≤ 7 days ago |

> 💡 **Why dates matter:** Instagram's feed hides post dates. The agent decodes the real date from the reel URL. Reels under 3 days old are still growing, so they are never used to call a page "dead".

### Winner Score (0–100)

| Part | Points | What it measures |
|---|---|---|
| A. Proof of sales | 30 | Views, buying comments, other sellers, ads, orders |
| B. Still getting views | 25 | Momentum + recent outliers (check 2) |
| C. Owner still posting | 15 | Posting activity (check 3) |
| D. Shareability | 15 | (sends + shares) ÷ likes |
| E. Business fit | 15 | Margin, shipping, supplier, season |

**70+ = winner candidate · 50–69 = watch · under 50 = skip.** Hard kills (trademark, no margin, restricted goods, slow shipping) override any score.

If something can't be seen, it is written as `n/a` and the **confidence** goes down. The agent never makes up numbers.

Full rules: [`knowledge/winning-signals.md`](knowledge/winning-signals.md)

### Verdicts

| Verdict | Meaning |
|---|---|
| `winner` | Passes all 3 checks. Go niche it. |
| `niche-only` | Proven, but crowded or trademarked. Sell only an original niche version. |
| `watch` | Promising. Re-check in a few days. |
| `skip` / `skip-seasonal` | Dead, risky, or the season window is closing. |

---

## Setup (5 minutes)

**You need:** [Claude Code](https://claude.com/claude-code), Google Chrome with the Claude in Chrome extension, and (optional) Python 3.8+.

1. **Clone or download this repo** into the folder where you run Claude Code. `CLAUDE.md` and the `.claude` folder must sit directly in that folder.
   ```bash
   git clone <this-repo-url> product-hunter
   cd product-hunter
   ```
2. **Start Claude Code with the browser:**
   ```bash
   claude --chrome
   ```
   Accept the "trust this folder" question.
3. **Check the commands loaded.** Type `/skills`. You should see: `hunt`, `check-product`, `niche`, `track-pages`, `log-result`, `compare-pages`, `fb-page`.
4. **Test the date tool:**
   ```bash
   python scripts/reel_date.py DfYOAFdCRcX
   ```
   It should print `2026-11-05`. No Python? That's fine, the agent uses a browser fallback (`scripts/reel_date.js`), or install Python from [python.org](https://www.python.org).
5. **Log a burner Instagram account into Chrome** (never your business account), then try:
   ```
   /check-product https://www.instagram.com/reel/DfoeITusRrD/
   ```

---

## Commands

| Command | What it does | Example |
|---|---|---|
| `/hunt [source] [niche]` | One safe batch of discovery → list of candidates | `/hunt` · `/hunt tags:pet` · `/hunt ads:dog camera` |
| `/check-product <link>` | Deep check: 3 checks + supplier + Winner Score → verdict | `/check-product https://instagram.com/reel/...` or `@account` |
| `/niche <product>` | 3–5 niche versions, picks the best, price + hook scripts | `/niche LED dog collar` |
| `/track-pages` | Re-checks every watched competitor page | `/track-pages` |
| `/compare-pages [rival]` | Your page vs a rival, and your page now vs last time | `/compare-pages @rival` · `/compare-pages me` |
| `/fb-page [me \| rival]` | Facebook page analysis, and Instagram vs Facebook | `/fb-page me` |
| `/log-result` | Records what happened when you tested a product | `/log-result LED collar, 5 videos, 40k views, 3 sales` |

You can also just talk normally: *"is this a winner?"*, *"find me pet products"*, *"next batch"*.

Every command saves a report in `reports/<type>/`, named like `check_2026-11-17_led-collar.md`.

---

## Weekly routine

| When | Type | What you get |
|---|---|---|
| Daily, 1–3 times | `/hunt` | New candidates (one safe batch each) |
| When something looks good | `/check-product <link>` | 3 checks + score + verdict |
| When it's a winner | `/niche <product>` | Niche version, price, 3 hook scripts |
| Twice a week | `/track-pages` | Which competitors are heating up or dying |
| Once a week | `/compare-pages me` | How your own page is doing |
| After every test | `/log-result` | The agent learns what really sells for you |

---

## How it learns

The agent gets better the more you use it:

| File | Role |
|---|---|
| `CLAUDE.md` | Permanent rules: the method, how answers should look |
| `knowledge/winning-signals.md` | The scoring rubric |
| `knowledge/worked-examples.md` | Real past calls, to calibrate scores |
| `knowledge/lessons.md` | Mistakes and corrections. Added every time you correct it |
| `data/results_log.csv` | **Your real test results. This is the training data.** |

- Before scoring, the agent reads the lessons and your last 10 results.
- When it gets something wrong, tell it why and say **"add this to lessons"**.
- After 5+ logged results, it looks for patterns (which signals really predicted sales) and **suggests** rubric changes. It only changes the rubric after you say yes.

---

## Folder structure

```
.
├── CLAUDE.md                 # The agent's main instructions
├── .claude/skills/           # The commands (/hunt, /check-product, ...)
├── knowledge/
│   ├── winning-signals.md    # Rubric + Winner Score
│   ├── safety-rules.md       # Browser safety limits
│   ├── niche-framework.md    # How to find a niche version
│   ├── sources-playbook.md   # Where and how to hunt
│   ├── worked-examples.md    # Calibration examples
│   └── lessons.md            # What the agent learned from corrections
├── data/
│   ├── products.csv          # Every product seen (deduped by reel URL)
│   ├── pages.csv             # Competitor pages being tracked
│   ├── results_log.csv       # Your real test results
│   ├── pages/                # Raw reel lists per page (<account>_reels.csv)
│   └── snapshots/            # Dated page snapshots (JSON) for comparisons
├── scripts/                  # Small Python tools (no installs needed)
├── reports/                  # One markdown report per run
│   ├── hunt/  check/  niche/  track/
│   └── compare/  progress/  facebook/
└── notes/                    # Your own notes
```

**Data rule:** CSV files are only appended or updated. Rows are never deleted, so you keep the full history.

---

## Scripts

All scripts use only the Python standard library (Python 3.8+). Try `python`, then `py`, then `python3`.

| Script | What it does | Example |
|---|---|---|
| `reel_date.py` | Gets the real post date from a reel URL | `python scripts/reel_date.py <url>` · `--csv data/products.csv` |
| `page_check.py` | Page median, outliers, momentum (check 2), posting activity (check 3) | `python scripts/page_check.py data/pages/<account>_reels.csv` |
| `page_snapshot.py` | Saves a dated snapshot of a page's numbers | `python scripts/page_snapshot.py data/pages/<account>_reels.csv --account <account> --followers 1200` |
| `compare_snapshots.py` | Compares two snapshots side by side | `python scripts/compare_snapshots.py --progress <account>` |
| `reel_date.js` | Browser fallback for `reel_date.py` when Python isn't installed | Run in the browser tab |

To check a new page by hand, copy `data/pages/_template_reels.csv`, fill in `reel_url` and `views`, then run `page_check.py` on it.

---

## Safety rules

The agent uses your real Chrome, so it follows strict rules ([`knowledge/safety-rules.md`](knowledge/safety-rules.md)):

- 🔒 **Burner account only.** If it sees your business account, it stops.
- 👀 **Read only.** It never likes, follows, comments, saves, shares, DMs or posts.
- 🛒 Add to cart is allowed only for the Shop check (quantity 1, then removed). **Never checkout or payment.**
- 🔑 **It never types passwords.** If a login screen appears, it asks you to log in.
- 🐢 **Slow and human-like:** 2–6 seconds between actions, max 40 product reels per batch, max 3 batches a day.
- 🛑 **Stops right away** on a captcha, "action blocked", or "try again later".
- ™️ **No copying trademarked products or designs.** IP products are `niche-only`: original design, new buyer.

---

## FAQ

**Do I need to know how to code?**
No. You type commands in plain English. The scripts run automatically.

**Why does it say `n/a` sometimes?**
It couldn't see that number (hidden views, blocked page, etc.). It never guesses. The confidence level tells you how much to trust the score.

**Why "niche versions" instead of selling the same product?**
The original seller already owns that audience. A niche version (same proven idea, a different buyer and problem) gets the proof without the competition.

**Does it consider the season?**
Yes. In Q4 it focuses on gifts and Christmas delivery. In January: gym, organisation and new-year products. It warns you when a seasonal product's selling window closes in under 6 weeks.

**Can it run several checks at the same time?**
Browser work always runs one at a time, to keep the account safe.

---

## Credits

- Built with [Claude Code](https://claude.com/claude-code).
- The `dropshipping` skill comes from [clawic/skills](https://github.com/clawic/skills).
"# research-agent" 
