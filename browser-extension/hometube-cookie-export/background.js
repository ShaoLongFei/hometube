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

    const activeHost = url.hostname.toLowerCase();
    chrome.cookies.getAll({}, (cookies) => {
      const matchingCookies = cookies
        .filter((cookie) => cookieMatchesHost(cookie, activeHost))
        .map(toNetscapeLine);

      if (matchingCookies.length === 0) {
        sendResponse({
          ok: false,
          error: `No cookies found for ${activeHost}. Make sure you are signed in on the active site.`,
        });
        return;
      }

      sendResponse({
        ok: true,
        site: activeHost,
        count: matchingCookies.length,
        text: `# Netscape HTTP Cookie File\n${matchingCookies.join("\n")}\n`,
      });
    });
  });

  return true;
});
