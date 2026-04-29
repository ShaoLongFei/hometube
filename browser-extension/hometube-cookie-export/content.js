window.addEventListener("message", (event) => {
  if (!event.data) {
    return;
  }

  if (event.data.type === "HOMETUBE_EXTENSION_PING") {
    const target = event.source || window;
    target.postMessage(
      {
        type: "HOMETUBE_EXTENSION_PONG",
        version: chrome.runtime.getManifest().version,
      },
      "*",
    );
  }
});
