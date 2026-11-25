# Lessons learned

The agent adds 1–3 lines here after every `/log-result` and whenever Rauf corrects a call. Newest at the top. Read this before scoring.
Format: `- YYYY-MM-DD: lesson (evidence)`

- 2026-11-25: Feed reels posted <1 h ago show no counts (seatflex, skyfetch, pelsbarn) → watch + recheck, not noise. Car-mug store pre-shows a "MOST POPULAR 2x" bundle: pick 1x before Add to cart. The Shop cart still holds 87 old items; only remove the one you added.
- 2026-11-25: Pre-order-only stores (thepawsandco "Pre-order now" button) don't add to cart → shop_status=blocked. The Shop cart (now shop.com/cart) had 80 leftover items and its count changed while another tab was open. Make sure no other browser session is running before Shop checks.
- 2026-11-20: Rauf's antivirus (RAV) can block a store's /cart page, but the add-to-cart still syncs to the Shop cart (snuggleshop.shop: 75+). Kelsio and snuggleshop pre-select a 2-pack, so always reset to quantity 1.
- 2026-11-19: A reel can have big views with almost no likes (princesscrops: 52.7K views, 191 likes, which suggests paid or boosted reach). Judge it on likes, sends and Shop badge, not views. A reel's likes, comments, date and caption can be read cheaply from the `description` meta tag of `/p/<code>/`, but that tag has no sends or shares.
- 2026-11-19: Adding to cart through the store's /cart/add.js does NOT show up in the Shop cart. Click the real Add to cart button. Stores with only a "Buy Now" button (pawspherebrand) get shop_status=blocked.
- 2026-11-18: In the feed, the URL code can lag one reel behind the counts (duplicate codes on pinkiephones, yumekawaii and victory_soaps). Check a candidate's code on its own reel page before /check-product. Stores that jump to /cart after Add to cart (pillowhaven) may not show up in the Shop cart, so "not-shop" there is low confidence.
- 2026-11-17: Shopify stores geolocate the browser and show prices in KRW. Read `Shopify.currency` and convert to USD, marked as approximate (zelunio, crosiah). The Shop cart had 28 items left over from earlier batches, so make sure each checked item gets removed.

- 2026-11-15: Many stores pre-select a 2-pack or auto-add gifts or shipping protection when you click Add to cart. Check the store cart and set it back to quantity 1 before reading the Shop cart (momelle, miautag, huntingbeam). Also: check whether a report file already exists before writing; report names now include HHMM (batch-1 hunt report was overwritten).

- 2026-11-14: @snowbarkie is Rauf's own page (Pupack). I scored it as a competitor product (SKIP 46). Check CLAUDE.md "own page" before scoring an account.
- 2026-11-14: The Shop app cart shows "X+ bought in past month" for Shopify stores. That is real order proof for check 1 (minionclava: 200+). Ask Rauf for it when sales are unclear.
- 2026-11-14: page_check.py only reads pinned = "yes" (not 1). A pinned old reel counted as the only "older" reel gave a fake 0.16x momentum on minionclava.
- 2026-11-14: The feed caption can mislead about the product. Always open the store link before naming it (pawsgotwings was logged as a collar camera; it sells a wing-projector LED collar).
- 2026-11-14: Decode post dates before judging a page. Reels under 3 days old are still growing (bck_2_ftr looked like it was cooling but the momentum was 3.1x).
- 2026-11-14: The first-frame action decides whether a reel goes viral, not the hook text (bck_2_ftr: same text on 5.9M and 2.5K reels; package destruction vs model posing).
- 2026-11-14: Sends > likes on a product reel is the strongest early signal in the feed (pawsgotwings collar cam: 1.28).
- 2026-11-14: Old reels with big numbers aren't current trends. Check date and season (floating sunglasses, 134 days, summer).
