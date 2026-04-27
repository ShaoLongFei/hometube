function getPrimaryDomain(hostname) {
  const commonSecondLevelSuffixes = new Set([
    "co.uk",
    "org.uk",
    "gov.uk",
    "ac.uk",
    "com.cn",
    "net.cn",
    "org.cn",
    "com.hk",
    "com.tw",
    "co.jp",
    "co.kr",
    "co.in",
    "com.au",
    "com.br",
    "com.mx",
    "com.tr",
    "com.sg",
  ]);

  const labels = (hostname || "").toLowerCase().split(".").filter(Boolean);
  if (labels.length <= 2) {
    return labels.join(".");
  }

  const lastTwo = labels.slice(-2).join(".");
  const lastThree = labels.slice(-3).join(".");

  if (commonSecondLevelSuffixes.has(lastTwo) && labels.length >= 3) {
    return lastThree;
  }

  return lastTwo;
}

function cookieMatchesHost(cookie, hostname) {
  const normalizedDomain = (cookie.domain || "").replace(/^\./, "").toLowerCase();
  const normalizedHost = (hostname || "").toLowerCase();

  return (
    normalizedHost === normalizedDomain ||
    normalizedHost.endsWith(`.${normalizedDomain}`)
  );
}

function toNetscapeLine(cookie) {
  const domain = cookie.domain || "";
  const includeSubdomains = cookie.hostOnly ? "FALSE" : "TRUE";
  const path = cookie.path || "/";
  const secure = cookie.secure ? "TRUE" : "FALSE";
  const expiration = Math.floor(cookie.expirationDate || 0);
  const name = cookie.name || "";
  const value = cookie.value || "";

  return [
    domain,
    includeSubdomains,
    path,
    secure,
    expiration,
    name,
    value,
  ].join("\t");
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "EXPORT_ACTIVE_SITE_COOKIES") {
    return;
  }

  chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs) => {
    const activeTab = tabs[0];
    if (!activeTab || !activeTab.url) {
      sendResponse({ ok: false, error: "No active tab URL available." });
      return;
    }

    let url;
    try {
      url = new URL(activeTab.url);
    } catch (error) {
      sendResponse({ ok: false, error: "Active tab URL is invalid." });
      return;
    }

    const primaryDomain = getPrimaryDomain(url.hostname);
    chrome.cookies.getAll({}, (cookies) => {
      const matchingCookies = cookies
        .filter((cookie) => cookieMatchesHost(cookie, url.hostname))
        .filter((cookie) => getPrimaryDomain(cookie.domain || "") === primaryDomain)
        .map(toNetscapeLine);

      if (matchingCookies.length === 0) {
        sendResponse({
          ok: false,
          error: `No cookies found for ${primaryDomain}. Make sure you are signed in on the active site.`,
        });
        return;
      }

      sendResponse({
        ok: true,
        site: primaryDomain,
        count: matchingCookies.length,
        text: `# Netscape HTTP Cookie File\n${matchingCookies.join("\n")}\n`,
      });
    });
  });

  return true;
});
