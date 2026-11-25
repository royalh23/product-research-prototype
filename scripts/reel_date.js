// Fallback when Python isn't installed: run this in the browser tab (javascript tool).
// Paste the whole thing, then call reelDate("https://www.instagram.com/reel/DfYOAFdCRcX/").
// Returns { code, postDateUTC, ageDays }.
function reelDate(url) {
  const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  const m = String(url).match(/(?:reel|reels|p|tv)\/([A-Za-z0-9_-]+)/);
  const code = (m ? m[1] : String(url)).slice(0, 11);
  let n = 0n;
  for (const ch of code) n = n * 64n + BigInt(A.indexOf(ch));
  const ms = Number(n >> 23n) + 1314220021721;
  const d = new Date(ms);
  return { code, postDateUTC: d.toISOString().slice(0, 16).replace("T", " "), ageDays: +((Date.now() - ms) / 864e5).toFixed(1) };
}
// Many at once: ["url1","url2"].map(reelDate)
