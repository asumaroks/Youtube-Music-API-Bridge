const input = document.getElementById("token");
const urlInput = document.getElementById("url");
const status = document.getElementById("status");
chrome.storage.local.get(["reporterToken", "reporterUrl"]).then(({
  reporterToken = "",
  reporterUrl = "http://127.0.0.1:8888/api/v1/report"
}) => {
  input.value = reporterToken;
  urlInput.value = reporterUrl;
});
document.getElementById("save").addEventListener("click", async () => {
  try {
    const endpoint = new URL(urlInput.value.trim());
    if (!/^https?:$/.test(endpoint.protocol)) throw new Error("Допустимы только HTTP/HTTPS");
    const originPattern = `${endpoint.origin}/*`;
    const localDefault = endpoint.origin === "http://127.0.0.1:8888";
    if (!localDefault) {
      const granted = await chrome.permissions.request({ origins: [originPattern] });
      if (!granted) throw new Error("Нет разрешения на подключение к этому адресу");
    }
    await chrome.storage.local.set({
      reporterToken: input.value.trim(),
      reporterUrl: endpoint.href
    });
    status.textContent = "Сохранено";
  } catch (error) {
    status.textContent = String(error);
  }
  setTimeout(() => { status.textContent = ""; }, 1500);
});
