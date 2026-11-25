# Where to look, and what to record

Use the Chrome browser tool. Follow `safety-rules.md` on every source.

## Contents
A. Instagram Reels feed · B. Instagram hashtags/search · C. Competitor page deep-dive · D. Meta Ad Library · E. Competitor Shopify store · F. AliExpress / CJ · G. Google Trends · H. TikTok Creative Center · I. Amazon reality check · J. Shop app cart (sales data)

---

## A. Instagram Reels feed (https://www.instagram.com/reels/)
- **Visible:** account, caption, likes, comments, reposts (shares), paper-plane sends, "Sponsored" label.
- **Not visible:** views and post date. Get the date from the URL with `scripts/reel_date.py`. Get views from the account's Reels tab (C).
- Read the numbers from page text or the accessibility tree, not screenshots (much faster). Screenshot only if the product is unclear.
- The feed shows what the burner account has interacted with. If the feed is stuck on one topic, use B to widen it.

## B. Instagram hashtag and search pages
- URL: `https://www.instagram.com/explore/tags/<tag>/` (if blocked, use the search bar).
- The grid shows top posts. Open a reel to read its numbers.
- Starter tags by niche:
  - general: amazonfinds, tiktokmademebuyit, viralproducts, gadgets, musthave
  - pet: dogproducts, dogmom, catproducts, petgadgets, doglover, puppytips
  - gift (Q4): giftideas, christmasgift, giftsforher, giftsforhim, stockingstuffers
  - home/kitchen: homegadgets, kitchengadgets, cleaninghacks, apartmenthacks
  - car: caraccessories, carhacks · kids: momhacks, toddlermom

## C. Competitor page deep-dive (Rauf's checks 2 and 3)
1. Open `https://www.instagram.com/<account>/` and note followers and the bio store link.
2. Open `https://www.instagram.com/<account>/reels/` and collect up to 40 reels: URL and the view count on the thumbnail. Mark the pinned ones.
3. Save as `data/pages/<account>_reels.csv` with columns `reel_url,views,pinned`.
4. Run `python scripts/page_check.py data/pages/<account>_reels.csv`.
5. Open the top 1–3 recent outliers. Read the first ~30 comments and count buying intent, keyword-only replies and complaints. Copy 3 telling comments word for word.

## D. Meta Ad Library (public; usually no login needed)
- URL: `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=video&q=<keyword>` (if the URL format fails, use the on-page filters: Active, All ads, country, Video).
- Search by **product keyword** and by **store/page name**.
- Record: advertiser, start date ("Started running on…"), number of ads/creatives, landing domain, and the hook in the first 3 seconds.
- Signals: start date 30+ days ago, several creatives for the same product, 2+ advertisers. The advertiser's other ads show what else they sell.
- Remember: the start date suggests profit but doesn't prove it.

## E. Competitor Shopify store (from the bio link)
- Best sellers: `<store>/collections/all?sort_by=best-selling`. Shopify ranks these by all-time orders, so the top items are what actually sells.
- Catalog and prices: `<store>/products.json?limit=250` (shows title, price, compare-at price, `created_at`, variants). Many stores block this. If so, skip it.
- Record: price, compare-at price, bundles, shipping promise, product launch date (`created_at`), and how many products they sell (one-product store or general store).

## F. AliExpress / CJ (supplier check)
- Search the product in plain words. Record cost, shipping cost and time to the US, weight, rating, review count, **recent** reviews, and variants.
- Pass: ≥ 4.7★ with 500+ reviews, shipping ≤ 15 days, and a price that lets you charge 3x.
- If a login or captcha wall appears, stop and tell Rauf. Don't try to get around it.

## G. Google Trends (https://trends.google.com/trends/)
- Set the country to the target market. Look at the past 5 years (fad or durable?), then the past 12 months (season and timing).
- In Related queries → Rising, note "Breakout" terms. These often reveal new angles and niche names.
- Try 2–3 names for the same product (e.g. "dog collar camera", "dog camera", "pet cam collar").

## H. TikTok Creative Center (optional)
- Top Products needs a login and works on desktop. Top Ads and trending hashtags can usually be browsed.
- If it's not logged in, skip it and note it in the report.

## I. Amazon reality check
- Search the product. If the same thing is on Amazon with Prime for about the price Rauf would charge, it **must** be niched (different buyer, bundle or version), or skipped.

## J. Shop app cart (sales data)
Used by the `/hunt` SHOP CHECK (max 15 per batch), only for product reels that aren't a hard kill and have likes ≥ 5,000 or (sends + shares) / likes ≥ 0.5.
1. Open the account profile and find the store link in the bio (follow a Linktree to the store). No link → `shop_status=no-link`.
2. Open the store and the product shown in the reel. Record `store_url`, `product_url`, `price`, `compare_at` and bundle offers.
3. Click "Add to cart" ONCE, quantity 1 (the variant shown in the reel, or the first).
4. Open https://shop.app/cart, find the item, and copy the badge text exactly (e.g. "25+ bought in past month") into `shop_bought_month` and the number into `shop_bought_month_num`. Store not in the Shop cart → `shop_status=not-shop`. Item there with no badge → `shop_bought_month=none-shown`.
5. Remove that item from the Shop cart.
**Never click Checkout, Buy now, Shop Pay, PayPal, Apple/Google Pay or any express button. Never enter an address, email or payment details.** If adding to cart needs a login or popup, close it and record `shop_status=blocked`.
