const copyButton = document.getElementById("copy-cookies");
const output = document.getElementById("cookies-output");
const status = document.getElementById("status");

copyButton.addEventListener("click", () => {
  status.textContent = "Exporting cookies…";

  chrome.runtime.sendMessage({ type: "EXPORT_ACTIVE_SITE_COOKIES" }, async (response) => {
    if (chrome.runtime.lastError) {
      status.textContent = chrome.runtime.lastError.message;
      return;
    }

    if (!response || !response.ok) {
      status.textContent = response?.error || "Could not export cookies.";
      return;
    }

    output.value = response.text;

    try {
      await navigator.clipboard.writeText(response.text);
      status.textContent = `Copied ${response.count} cookies for ${response.site} to the clipboard. Paste them into HomeTube.`;
    } catch (error) {
      status.textContent = `Exported ${response.count} cookies for ${response.site}. Clipboard write failed, copy the text manually below.`;
    }
  });
});
