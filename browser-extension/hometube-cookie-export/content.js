window.addEventListener("message", (event) => {
  if (event.source !== window || !event.data) {
    return;
  }

  if (event.data.type === "HOMETUBE_EXTENSION_PING") {
    event.source.postMessage(
      {
        type: "HOMETUBE_EXTENSION_PONG",
        version: chrome.runtime.getManifest().version,
      },
      "*",
    );
  }
});
