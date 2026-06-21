chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !["report-current", "poll-command"].includes(message.type)) return false;
  (async () => {
    const {
      reporterToken = "",
      reporterUrl = "http://127.0.0.1:8888/api/v1/report"
    } = await chrome.storage.local.get(["reporterToken", "reporterUrl"]);
    if (!reporterToken) throw new Error("Reporter token is not configured");
    const endpoint = new URL(reporterUrl);
    if (!/^https?:$/.test(endpoint.protocol)) throw new Error("Reporter URL must use HTTP or HTTPS");
    if (message.type === "poll-command") {
      endpoint.pathname = endpoint.pathname.replace(/\/api\/v1\/(?:report|like-url)$/, "/api/v1/command");
      endpoint.search = "";
      endpoint.searchParams.set("videoId", message.videoId);
      const response = await fetch(endpoint.href, {
        headers: { "Authorization": `Bearer ${reporterToken}` }
      });
      if (response.status === 204) return { command: null };
      if (!response.ok) throw new Error(`Command endpoint returned HTTP ${response.status}`);
      return response.json();
    }
    const response = await fetch(endpoint.href, {
      method: "POST",
      headers: { "Authorization": `Bearer ${reporterToken}`, "Content-Type": "application/json" },
      body: JSON.stringify(message.payload)
    });
    if (!response.ok) throw new Error(`Reporter returned HTTP ${response.status}`);
    return response.json();
  })().then(
    value => sendResponse({ ok: true, value }),
    error => sendResponse({ ok: false, error: String(error) })
  );
  return true;
});
