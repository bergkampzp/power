const $ = (id) => document.getElementById(id);

chrome.storage.local.get(["backendUrl", "token"]).then((c) => {
  $("url").value = c.backendUrl || "";
  $("tok").value = c.token || "";
});

$("save").onclick = async () => {
  await chrome.storage.local.set({
    backendUrl: $("url").value.trim(),
    token: $("tok").value.trim(),
  });
  $("msg").textContent = "已保存";
  $("msg").style.color = "green";
};

$("test").onclick = async () => {
  const cfg = await chrome.storage.local.get(["backendUrl", "token"]);
  if (!cfg.backendUrl || !cfg.token) {
    $("msg").textContent = "请先填写后端地址和令牌并保存";
    $("msg").style.color = "red";
    return;
  }
  const ck = await chrome.cookies.get({
    url: "https://spot.poweremarket.com",
    name: "CAMSID",
  });
  if (!ck) {
    $("msg").textContent = "未检测到 CAMSID，请先在同一浏览器登录 spot.poweremarket.com";
    $("msg").style.color = "orange";
    return;
  }
  try {
    const r = await fetch(
      cfg.backendUrl.replace(/\/$/, "") + "/api/extension/cookie",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: cfg.token, cookie: "CAMSID=" + ck.value }),
      }
    );
    $("msg").textContent = r.ok
      ? "推送成功，已触发同步"
      : "推送失败 " + r.status;
    $("msg").style.color = r.ok ? "green" : "red";
  } catch (e) {
    $("msg").textContent = "网络错误: " + e.message;
    $("msg").style.color = "red";
  }
};
