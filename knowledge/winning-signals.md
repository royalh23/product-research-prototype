# Winning-product rubric

How to decide if a product is a winner. Built on Rauf's own 3 checks, plus signals backed by research (sources at the bottom).

## Contents
1. Rauf's 3 core checks
2. Extra signals
3. Winner Score (0–100)
4. Hard kills
5. Saturation: "niche it", don't kill
6. Lifecycle stage: when to enter
7. Business-fit numbers

---

## 1. Rauf's 3 core checks

These come first. A product has to pass all three to be a WINNER.

| # | Rauf's check | How to measure it | Pass |
|---|---|---|---|
| 1 | **It already sold a lot** | Best reel views, buying-intent comments, how many other sellers have it, ads running 30+ days, supplier orders | At least 2 of these show proof (see score section A) |
| 2 | **The page's videos still get views** | `scripts/page_check.py`: momentum = median views of reels aged 3–10 days ÷ median of reels aged 11–45 days. Also look for recent outliers. | momentum ≥ 0.6, or a reel from the last 14 days at 3x+ the page median |
| 3 | **The owner still posts** (so the product still sells) | Same script: days since the last post and posts in the last 14 days | Last post ≤ 7 days ago. Best is ≤ 3 days with 4+ posts in 14 days |

**Always work out post dates from the URLs (`scripts/reel_date.py`) before judging anything.** The feed doesn't show dates, and reels under 3 days old are still growing. Calling a page "dying" because its newest reels look small is the most common mistake (see `worked-examples.md`, example 1).

## 2. Extra signals

- **Sends + shares per like** (strongest spread signal). Instagram's head, Adam Mosseri, names watch time, likes per reach and sends per reach as the top ranking signals, and sends matter most for reaching non-followers. The feed shows the paper-plane (sends) and repost counts, so use `(sends + shares) / likes`.
  - ≥ 1.0 is exceptional (rare: people DM it to friends more than they like it)
  - 0.5–1.0 is strong, 0.25–0.5 is normal, < 0.25 is weak
  - Only compare products with products. Memes and jokes always get huge sends.
- **Velocity:** sends per day since posting (`sends / age_days`). This tells a hot new reel apart from an old one that collected numbers slowly.
- **Buying intent in comments:** "link", "price", "how much", "where to buy", "ship to…", tagging a friend. Replies that are just the CTA keyword (e.g. "COD") count as half, because the video told people to type them.
- **Complaints:** "broke", "scam", "never arrived", "4 weeks", "cheap". A few complaints is normal. Complaints about delivery or trust are an opening for your version.
- **Paid proof (Meta Ad Library):** an ad that has run 30+ days is the common "it's profitable" signal. 2+ advertisers with 30+ day ads is a strong validation threshold. Treat this as a hint, not proof: an old start date doesn't prove the ad ran or made money the whole time.
- **Supplier momentum:** recent reviews matter more than the total order count. 800 orders with lots of recent reviews can mean more current momentum than 20,000 old orders.
- **Google Trends:** check 5 years first, then 12 months. Stable or rising is good. A one-time spike is a fad. "Breakout" in Rising queries means growth of more than 5,000%.

## 3. Winner Score (0–100)

Score only what you could measure. Write `n/a` for the rest and report **confidence** = measured points ÷ 100 (high ≥ 70, medium 40–69, low < 40).

**A. Proof of sales (0–30)**
- Best reel views: ≥1M = 10 · 500K–1M = 8 · 100K–500K = 4 · <100K = 2 (hidden views: likes ≥50K = 8 · 10K–50K = 4 · <10K = 2)
- Buying intent: ≥40% = 7 · 20–40% = 4 · <20% = 2
- Other sellers: 2–4 = 3 · 5+ = 3 + CROWDED · only 1 = 1
- Paid proof: ad ≥30 days or 2+ advertisers ≥14 days = 5 · none = 0
- Orders proof (Shop "bought in past month", AliExpress sold count, or sold-out variants): 200+ = 5 · 100–199 = 4 · 50–99 = 3 · 25–49 = 2 · not shown = 0 (not proof of zero sales)

**B. Still getting views, check 2 (0–25)**
- Momentum ≥ 1.0 = 15 · 0.6–1.0 = 10 · 0.35–0.6 = 5 · < 0.35 = 0
- At least one reel from the last 14 days at 3x+ the median = 10

**C. Owner still posting, check 3 (0–15)**
- Last post ≤ 3 days ago with 4+ posts in 14 days = 15 · ≤ 7 days = 10 · ≤ 14 days = 5 · > 14 days = 0

**D. Shareability (0–15)**
- (sends + shares) / likes: ≥ 1.0 = 15 · 0.5–1.0 = 10 · 0.25–0.5 = 6 · < 0.25 = 2

**E. Business fit (0–15)** Start at 15 and subtract:
- Fragile (glass, ceramic) −5 · Heavy (> 2 kg) or bulky −5 · Sizing or fit issues (clothes, shoes) −3
- Battery or electronics (more defects and returns, shipping limits) −3
- Seasonal window closes in < 6 weeks −5

**Verdict**
- **≥ 70 = WINNER CANDIDATE**: run `/niche`, then Rauf orders a sample
- **50–69 = WATCH**: add to `data/pages.csv`, re-check with `/track-pages` in 3–7 days
- **< 50 = SKIP**
- A hard kill (section 4) overrides any score.

## 4. Hard kills (skip whatever the score)

- **Trademark or IP:** characters, brands, logos, game or movie names (Call of Duty, Marvel, Disney, Powerpuff…). The demand still counts as proof, so mark it `niche-only`: sell an original design to a new buyer.
- **No margin:** you can't sell at 3x the landed cost (product + shipping), or the competitor's price is already under that.
- **Regulated or restricted:** medical claims, weapons, supplements, anything kids put in their mouth, hazardous goods.
- **Shipping:** no supplier can deliver to the target country in ≤ 15 days. 4–6 week waits lead to chargebacks.
- **Not a product:** a meme, service, app or course.

## 5. Saturation: niche it, don't kill it

Use 4 checks. If **3 or more are yes**, the obvious angle is saturated:
1. Dozens of stores or accounts sell the exact same item
2. Competitors have carried it for many months
3. Several stores run the same video, headline and benefit
4. Product pages look nearly identical (same photos, copy, reviews)

Saturated usually means proven. Don't drop it. Change the **audience, benefit, offer or creative**, and send it to `/niche`.

## 6. Lifecycle stage: when to enter

| Stage | Signs | Action |
|---|---|---|
| Early signal | Few sellers, a few videos gaining traction, "where to buy?" comments, rising recent reviews | Best entry point, together with breakout |
| Breakout | Views and orders rising fast, more sellers testing | Enter now if margin, supplier and shipping are good |
| Saturation | Many identical stores and creatives, prices falling | Enter only with a niche angle |
| Decline / evergreen | Hype fades. Problem-solvers stay as steady sellers | Skip novelties. Evergreen products need a brand angle |

## 7. Business-fit numbers

- Price ≈ 3x (product + shipping). Gross margin before ads ≥ 60%.
- Weight under 2 kg. Not fragile. No IP.
- Supplier: ≥ 4.7★ with 500+ reviews, positive feedback > 95%.
- Shipping ≤ 15 days (local warehouse is best).
- Can be shown in a 3-second hook (Rauf sells with organic Reels, so this matters a lot).

---
Sources (checked 2026-11-14):
- Instagram ranking signals: https://buffer.com/resources/instagram-algorithms/ and https://www.socialpilot.co/blog/instagram-reels-algorithm
- Go/no-go thresholds: https://dropship-spy.com/blog/how-to-find-winning-dropshipping-products-2026
- Saturation checks: https://koala-apps.io/blog/is-a-dropshipping-product-saturated/
- Lifecycle and supplier momentum: https://www.alidrop.co/blogs/aliexpress-trending-products-before-they-saturate
- Ad Library caveats: https://www.admapix.com/blog/app-going-global/find-winning-products-facebook-ads-library
- Google Trends Breakout: https://www.dropified.com/blog/how-to-use-google-trends-to-validate-dropshipping-product-ideas-step-by-step/
