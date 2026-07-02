(() => {
  const form = document.getElementById("config-form");
  const statusPill = document.getElementById("status-pill");
  const statusText = document.getElementById("status-text");
  const btnScanOnce = document.getElementById("btn-scan-once");
  const btnStart = document.getElementById("btn-start");
  const btnStop = document.getElementById("btn-stop");
  const findingsList = document.getElementById("findings-list");
  const findingsCount = document.getElementById("findings-count");
  const logList = document.getElementById("log-list");
  const scanMeta = document.getElementById("scan-meta");
  const toast = document.getElementById("toast");
  const intervalSlider = form.querySelector('[name="interval_slider"]');
  const intervalInput = form.querySelector('[name="interval_seconds"]');
  const intervalHint = document.getElementById("interval-hint");

  let lastLogId = null;
  let knownFindingIds = new Set();
  let notifySoundEnabled = true;
  let audioCtx = null;

  function showToast(message, isError = false) {
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.remove("hidden");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => toast.classList.add("hidden"), 3500);
  }

  function formatInterval(seconds) {
    if (seconds < 60) return `${seconds} ثانية`;
    const mins = Math.round(seconds / 60);
    if (mins === 1) return "≈ دقيقة واحدة";
    return `≈ ${mins} دقائق`;
  }

  function syncInterval(fromSlider) {
    const value = fromSlider
      ? Number(intervalSlider.value)
      : Number(intervalInput.value);
    intervalSlider.value = value;
    intervalInput.value = value;
    intervalHint.textContent = formatInterval(value);
  }

  intervalSlider.addEventListener("input", () => syncInterval(true));
  intervalInput.addEventListener("input", () => syncInterval(false));

  function playChime() {
    if (!notifySoundEnabled) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.4);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.4);
    } catch (_) {
      // Audio may be blocked until user interaction.
    }
  }

  function applyConfig(config) {
    form.start_date.value = config.start_date;
    form.end_date.value = config.end_date;
    form.interval_seconds.value = config.interval_seconds;
    intervalSlider.value = config.interval_seconds;
    syncInterval(true);
    form.notify_sound.checked = config.notify_sound;
    notifySoundEnabled = config.notify_sound;
    form.telegram_bot_token.value = config.telegram_bot_token || "";
    form.telegram_chat_id.value = config.telegram_chat_id || "";
  }

  function gatherConfig() {
    return {
      start_date: form.start_date.value,
      end_date: form.end_date.value,
      interval_seconds: Number(form.interval_seconds.value),
      notify_sound: form.notify_sound.checked,
      telegram_bot_token: form.telegram_bot_token.value.trim(),
      telegram_chat_id: form.telegram_chat_id.value.trim(),
    };
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...options.headers },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `فشل الطلب (${response.status})`);
    }
    return data;
  }

  function renderStatus(status) {
    statusPill.classList.remove("monitoring", "scanning");
    if (status.monitoring) {
      statusPill.classList.add("monitoring");
      statusText.textContent = "جاري المراقبة";
      btnStart.classList.add("hidden");
      btnStop.classList.remove("hidden");
    } else if (status.scanning) {
      statusPill.classList.add("scanning");
      statusText.textContent = "جاري الفحص…";
    } else {
      statusText.textContent = "خامل";
      btnStart.classList.remove("hidden");
      btnStop.classList.add("hidden");
    }

    btnScanOnce.disabled = status.scanning;
    btnStart.disabled = status.monitoring || status.scanning;

    const parts = [];
    if (status.last_scan_at) parts.push(`آخر فحص: ${status.last_scan_at}`);
    if (status.next_scan_at) parts.push(`الفحص القادم: ${status.next_scan_at}`);
    scanMeta.textContent = parts.join(" · ");
  }

  function appendLogs(logs, replace = false) {
    if (replace) logList.innerHTML = "";
    for (const entry of logs) {
      const div = document.createElement("div");
      div.className = `log-entry ${entry.level}`;
      div.dataset.id = entry.id;
      div.innerHTML = `<span class="log-time">${entry.timestamp}</span><span>${escapeHtml(entry.message)}</span>`;
      logList.appendChild(div);
      lastLogId = entry.id;
    }
    logList.scrollTop = logList.scrollHeight;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function renderFindings(findings) {
    let newTickets = false;
    if (!findings.length) {
      findingsList.className = "findings-list empty-state";
      findingsList.innerHTML = "<p>لا توجد تذاكر بعد. ابدأ المراقبة أو نفّذ فحصاً واحداً.</p>";
      findingsCount.textContent = "0 تذكرة";
      return;
    }

    findingsList.className = "findings-list";
    findingsList.innerHTML = "";
    for (const f of findings) {
      if (!knownFindingIds.has(f.id)) {
        knownFindingIds.add(f.id);
        newTickets = true;
      }
      const card = document.createElement("article");
      card.className = "finding-card";
      card.innerHTML = `
        <div>
          <div class="finding-provider">${escapeHtml(f.provider)} · ${escapeHtml(f.service)}</div>
          <div class="finding-date">${escapeHtml(f.travel_date)}</div>
        </div>
        <div class="finding-details">${escapeHtml(f.details)}</div>
        <a class="btn btn-primary" href="${escapeHtml(f.url)}" target="_blank" rel="noopener">احجز الآن</a>
        <div class="finding-time">وُجدت في ${escapeHtml(f.found_at || "")}</div>
      `;
      findingsList.appendChild(card);
    }
    findingsCount.textContent = `${findings.length} تذكرة`;
    if (newTickets) playChime();
  }

  function handleEventPayload(payload) {
    if (payload.status) {
      applyConfig(payload.status.config);
      renderStatus(payload.status);
    }
    if (payload.logs?.length) {
      appendLogs(payload.logs);
    }
    if (payload.findings) {
      renderFindings(payload.findings);
    }
  }

  function connectEvents() {
    const source = new EventSource("/api/events");
    source.onmessage = (event) => {
      try {
        handleEventPayload(JSON.parse(event.data));
      } catch (_) {
        // ignore malformed events
      }
    };
    source.onerror = () => {
      source.close();
      setTimeout(connectEvents, 3000);
    };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    notifySoundEnabled = form.notify_sound.checked;
    try {
      await api("/api/config", {
        method: "POST",
        body: JSON.stringify(gatherConfig()),
      });
      showToast("تم حفظ الإعدادات");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  btnScanOnce.addEventListener("click", async () => {
    try {
      await api("/api/config", { method: "POST", body: JSON.stringify(gatherConfig()) });
      await api("/api/scan", { method: "POST" });
      showToast("بدأ الفحص");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  btnStart.addEventListener("click", async () => {
    try {
      await api("/api/config", { method: "POST", body: JSON.stringify(gatherConfig()) });
      await api("/api/monitor/start", { method: "POST" });
      showToast("بدأت المراقبة");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  btnStop.addEventListener("click", async () => {
    try {
      await api("/api/monitor/stop", { method: "POST" });
      showToast("توقفت المراقبة");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  document.getElementById("btn-clear-log").addEventListener("click", () => {
    logList.innerHTML = "";
    lastLogId = null;
  });

  document.getElementById("btn-clear-findings").addEventListener("click", async () => {
    try {
      const data = await api("/api/findings/clear", { method: "POST" });
      knownFindingIds.clear();
      renderFindings(data.findings || []);
      showToast("تم مسح قائمة التذاكر");
    } catch (err) {
      showToast(err.message, true);
    }
  });

  async function init() {
    try {
      const status = await api("/api/status");
      applyConfig(status.config);
      renderStatus(status);
      const logs = await api("/api/logs");
      appendLogs(logs, true);
      const findings = await api("/api/findings");
      renderFindings(findings);
    } catch (err) {
      showToast("تعذّر تحميل التطبيق: " + err.message, true);
    }
    connectEvents();
  }

  init();
})();
