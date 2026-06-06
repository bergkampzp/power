const PLATFORM_URL = "https://spot.poweremarket.com";

async function pushCookie() {
  const cfg = await chrome.storage.local.get(["backendUrl", "token"]);
  if (!cfg.backendUrl || !cfg.token) return;
  const ck = await chrome.cookies.get({ url: PLATFORM_URL, name: "CAMSID" });
  if (!ck) return;
  try {
    await fetch(cfg.backendUrl.replace(/\/$/, "") + "/api/extension/cookie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: cfg.token, cookie: "CAMSID=" + ck.value }),
    });
  } catch (e) {
    // Network failure — will retry on next login
  }
}

// Primary trigger: fires when user logs in to spot.poweremarket.com (CAMSID written)
chrome.cookies.onChanged.addListener((info) => {
  if (
    info.cookie.name === "CAMSID" &&
    info.cookie.domain.includes("poweremarket.com") &&
    !info.removed
  ) {
    pushCookie();
  }
});

// Fallback: push every 23 hours in case CAMSID was renewed without a page visit
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("daily_push", { periodInMinutes: 23 * 60 });
});
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "daily_push") pushCookie();
});
