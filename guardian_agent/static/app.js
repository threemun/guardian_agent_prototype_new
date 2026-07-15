const state = {
  selectedEventId: null,
  selectedElderId: "E001",
  dashboard: null,
};

const memorySamplesByElder = {
  E001: ["mom_childhood_courtyard", "mom_daughter_kindergarten", "daughter_project_launch", "family_recipe_noodles", "old_photo_red_sweater", "morning_market", "granddaughter_calligraphy", "balcony_flowers", "community_dance", "rainy_library"],
  E002: ["dad_factory_badge", "father_teaches_bicycle", "family_chess_table", "repair_radio", "new_home_keys", "tea_with_neighbor", "park_walk", "grandson_math", "winter_dumplings", "old_song"],
  E003: ["grandma_embroidery", "daughter_piano", "family_trip_lake", "festival_lanterns", "garden_tomatoes", "wardrobe_scarf", "neighbor_music_group", "daughter_first_salary", "handwritten_letter", "video_call_reunion"],
};

const riskText = {
  CRITICAL: "CRITICAL",
  WARNING: "WARNING",
  INFO: "INFO",
  normal: "平稳",
  attention: "需关注",
  abnormal: "异常",
  high_risk: "高风险",
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function loadDashboard(preferredEventId = null, elderId = state.selectedElderId) {
  state.selectedElderId = elderId || state.selectedElderId || "E001";
  const params = new URLSearchParams();
  params.set("elder_id", state.selectedElderId);
  let requestedEventId = preferredEventId || state.selectedEventId;
  const current = selectedEvent();
  if (!preferredEventId && current?.status === "CLOSED") {
    requestedEventId = "";
  }
  if (requestedEventId) params.set("selected_event_id", requestedEventId);
  const data = await api(`/api/v1/dashboard?${params.toString()}`);
  state.dashboard = data;
  const selectedFromServer = data.selected_event?.id;
  const exists = data.events.some((event) => event.id === selectedFromServer);
  state.selectedEventId = exists ? selectedFromServer : preferredEventId || state.selectedEventId;
  if (!state.selectedEventId || !data.events.some((event) => event.id === state.selectedEventId)) {
    state.selectedEventId = data.selected_event ? data.selected_event.id : data.events[0]?.id;
  }
  renderDashboard(data);
}

function renderDashboard(data) {
  document.getElementById("modeBadge").textContent = data.mode;
  document.getElementById("countToday").textContent = data.counts.today_events;
  document.getElementById("countElder").textContent = data.counts.waiting_elder;
  document.getElementById("countEscalated").textContent = data.counts.escalated;
  document.getElementById("countClosed").textContent = data.counts.closed;
  document.getElementById("eventTotal").textContent = `${data.events.length} 条事件`;
  state.selectedElderId = data.selected_elder_id || state.selectedElderId;

  renderEvents(data.events);
  const selected =
    data.selected_event && data.selected_event.id === state.selectedEventId
      ? data.selected_event
      : data.events.find((event) => event.id === state.selectedEventId);
  renderTimeline(selected ? selected.timeline || [] : []);
  renderDetail(selected);
  renderReport("dailyReport", data.daily_report);
  renderReport("weeklyReport", data.weekly_report);
  renderVitals(data.vitals || []);
  renderContract(data.contract);
  renderMemoryBoard(data.memories || [], data.memory_facets || {}, data.memory_recordings || []);
}

function renderEvents(events) {
  const list = document.getElementById("eventList");
  list.innerHTML = events
    .map((event) => {
      const active = event.id === state.selectedEventId ? "active" : "";
      return `
        <div class="event-card ${active}" data-event-id="${event.id}">
          <div class="event-title">
            <span>${escapeHtml(event.title)}</span>
            <span class="badge ${event.risk_level}">${riskText[event.risk_level] || event.risk_level}</span>
          </div>
          <div class="event-source">${escapeHtml(event.source)} / ${escapeHtml(event.location)}</div>
          <div class="event-desc">${escapeHtml(event.description)}</div>
          <div class="event-foot">
            <span>置信度 ${Number(event.confidence).toFixed(2)}</span>
            <span>${escapeHtml(event.status_label)}</span>
          </div>
        </div>
      `;
    })
    .join("");

  list.querySelectorAll(".event-card").forEach((card) => {
    card.addEventListener("click", async () => {
      state.selectedEventId = card.dataset.eventId;
      const event = await api(`/api/v1/events/${state.selectedEventId}`);
      await loadDashboard(event.id, event.elder_id);
    });
  });
}

function renderTimeline(timeline) {
  const box = document.getElementById("timeline");
  if (!timeline.length) {
    box.innerHTML = `<p class="muted">暂无决策记录</p>`;
    return;
  }
  box.innerHTML = timeline
    .map(
      (item) => `
        <div class="timeline-item ${escapeHtml(item.step_type)}">
          <div class="time">${formatTime(item.created_at)}</div>
          <div class="timeline-title">${escapeHtml(item.title)}</div>
          <div class="timeline-desc">${escapeHtml(item.description)}</div>
          ${item.tool_name ? `<span class="tool-tag">${escapeHtml(item.tool_name)}</span>` : ""}
        </div>
      `
    )
    .join("");
}

function renderDetail(event) {
  const box = document.getElementById("eventDetail");
  if (!event) {
    box.innerHTML = `<p class="muted">暂无事件</p>`;
    return;
  }
  box.innerHTML = `
    ${detailRow("事件类型", `<strong>${escapeHtml(event.type)}</strong>`)}
    ${detailRow("当前状态", `<strong>${escapeHtml(event.status_label || event.status)}</strong>`)}
    ${detailRow("风险等级", `<span class="badge ${event.risk_level}">${riskText[event.risk_level] || event.risk_level}</span>`)}
    ${detailRow("绑定主机", `<strong>${escapeHtml(event.elder?.device_host || "-")}</strong>`)}
    ${detailRow("老人档案", `${escapeHtml(event.elder?.name || "-")} / ${escapeHtml(event.elder?.room || "-")}`)}
    ${detailRow("判断证据", chipList(event.evidence || []))}
    ${detailRow("可用工具", chipList(event.tools || []))}
    ${detailRow("下一步动作", chipList(event.actions || []))}
    <div class="detail-row">
      <label>Agent说明</label>
      <div>${escapeHtml(event.description)}</div>
    </div>
  `;
}

function renderReport(targetId, report) {
  const box = document.getElementById(targetId);
  if (!report) {
    box.innerHTML = `<p class="muted">暂无报告</p>`;
    return;
  }
  const content = report.content || {};
  const suggestions = content.suggestions || [];
  const findings = content.key_findings || content.trend_findings || [];
  const abnormal = content.abnormal_items || [];
  box.innerHTML = `
    <div class="report-title">
      <strong>${escapeHtml(content.elder?.name || "")} · ${escapeHtml(report.title)}</strong>
      <span class="badge ${report.risk_level}">${riskText[report.risk_level] || report.risk_level}</span>
    </div>
    <p class="report-summary">${escapeHtml(report.summary)}</p>
    ${abnormal.length ? `<div class="tiny">异常指标</div><ul class="list">${abnormal.map((item) => `<li>${escapeHtml(item.display_name)}：${escapeHtml(item.value)}，${escapeHtml(item.analysis)}</li>`).join("")}</ul>` : ""}
    ${findings.length ? `<div class="tiny">趋势重点</div><ul class="list">${findings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
    ${suggestions.length ? `<div class="tiny">照护建议</div><ul class="list">${suggestions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  `;
}

function renderVitals(rows) {
  const tbody = document.getElementById("vitalRows");
  tbody.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${formatDateTime(row.measured_at)}</td>
          <td>${escapeHtml(row.elder_name || row.elder_id || "-")}</td>
          <td>${value(row.temperature, "摄氏度")}</td>
          <td>${value(row.heart_rate, "次/分")}</td>
          <td>${row.systolic_bp || "-"} / ${row.diastolic_bp || "-"}</td>
          <td>${value(row.fasting_glucose, "mmol/L")}</td>
          <td>${value(row.blood_oxygen, "%")}</td>
          <td>${value(row.sleep_hours, "小时")} ${row.sleep_quality || ""}</td>
          <td>${escapeHtml(row.note || "-")}</td>
        </tr>
      `
    )
    .join("");
}

function renderContract(contract) {
  const box = document.getElementById("contractBox");
  box.innerHTML = `
    <p>服务器消息入口</p>
    <code>${escapeHtml(contract.ingest_endpoint)}</code>
    <p>网页读取 Agent 结果</p>
    ${contract.result_endpoints.map((endpoint) => `<code>${escapeHtml(endpoint)}</code>`).join("")}
    <p>${escapeHtml(contract.report_note)}</p>
  `;
}

function renderMemoryBoard(memories, facets, recordings) {
  populateMemoryFilters(facets);
  renderMemories(memories);
  renderRecordings(recordings || []);
}

function populateMemoryFilters(facets) {
  const personSelect = document.getElementById("memoryPerson");
  const emotionSelect = document.getElementById("memoryEmotion");
  const topicSelect = document.getElementById("memoryTopic");
  if (!personSelect || !emotionSelect || !topicSelect) return;
  const currentPerson = personSelect.value;
  const currentEmotion = emotionSelect.value;
  const currentTopic = topicSelect.value;
  personSelect.innerHTML = `<option value="">全部人物</option>${(facets.people || [])
    .map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)
    .join("")}`;
  emotionSelect.innerHTML = `<option value="">全部情感</option>${(facets.emotions || [])
    .map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)
    .join("")}`;
  topicSelect.innerHTML = `<option value="">全部主题</option>${(facets.topics || [])
    .map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)
    .join("")}`;
  personSelect.value = currentPerson;
  emotionSelect.value = currentEmotion;
  topicSelect.value = currentTopic;
}

function renderMemories(memories) {
  const list = document.getElementById("memoryList");
  if (!list) return;
  if (!memories.length) {
    list.innerHTML = `<div class="memory-card"><h3>暂无匹配回忆</h3><p class="memory-prose">换一个人物、情感或关键词试试。</p></div>`;
    return;
  }
  list.innerHTML = memories
    .map((memory) => {
      const people = memory.people || [];
      const keywords = memory.keywords || [];
      const audioSrc = memory.recording_id ? `/api/v1/recordings/${encodeURIComponent(memory.recording_id)}/audio` : "";
      return `
        <article class="memory-card">
          <h3>${escapeHtml(memory.title)}</h3>
          <div class="memory-meta">
            <span class="memory-chip">${escapeHtml(memory.topic)}</span>
            <span class="memory-chip emotion">${escapeHtml(memory.emotion)}</span>
            <span class="memory-chip">发生 ${escapeHtml(memory.memory_date || memory.memory_time_text)}</span>
            <span class="memory-chip">录音 ${escapeHtml(formatDateTime(memory.call_started_at))}</span>
            ${people.map((person) => `<span class="memory-chip">${escapeHtml(person)}</span>`).join("")}
          </div>
          <p class="memory-prose">${escapeHtml(memory.lyric_text)}</p>
          ${audioSrc ? `<audio class="memory-audio" controls preload="none" src="${audioSrc}"></audio>` : ""}
          <div class="source-label">完整对话记录</div>
          <div class="source-text">${escapeHtml(memory.source_text)}</div>
          ${keywords.length ? `<div class="memory-meta">${keywords.slice(0, 5).map((word) => `<span class="memory-chip">${escapeHtml(word)}</span>`).join("")}</div>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderRecordings(recordings) {
  const box = document.getElementById("recordingList");
  if (!box) return;
  if (!recordings.length) {
    box.innerHTML = `<div class="recording-item"><strong>暂无录音</strong><span>可点击上方样本按钮生成。</span></div>`;
    return;
  }
  box.innerHTML = recordings
    .map(
      (recording) => `
        <div class="recording-item">
          <strong>${escapeHtml(recording.family_member)} / ${formatDateTime(recording.call_started_at)}</strong>
          <span>${escapeHtml(recording.stt_provider)} · ${recording.audio_duration_seconds || 0} 秒 · ${escapeHtml(recording.status)}</span>
          <audio class="memory-audio compact" controls preload="none" src="/api/v1/recordings/${encodeURIComponent(recording.id)}/audio"></audio>
        </div>
      `
    )
    .join("");
}

async function searchMemories() {
  const params = new URLSearchParams();
  params.set("query", document.getElementById("memoryQuery")?.value || "");
  params.set("person", document.getElementById("memoryPerson")?.value || "");
  params.set("emotion", document.getElementById("memoryEmotion")?.value || "");
  params.set("topic", document.getElementById("memoryTopic")?.value || "");
  params.set("elder_id", state.selectedElderId || "E001");
  params.set("memory_start_date", document.getElementById("memoryStart")?.value || "");
  params.set("memory_end_date", document.getElementById("memoryEnd")?.value || "");
  params.set("recorded_start_date", document.getElementById("recordedStart")?.value || "");
  params.set("recorded_end_date", document.getElementById("recordedEnd")?.value || "");
  const data = await api(`/api/v1/memories?${params.toString()}`);
  renderMemoryBoard(data.items || [], data.facets || {}, state.dashboard?.memory_recordings || []);
}

function detailRow(label, html) {
  return `<div class="detail-row"><label>${label}</label><div>${html}</div></div>`;
}

function chipList(items) {
  if (!items.length) return "-";
  return `<div class="chips">${items.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function formatTime(value) {
  if (!value) return "-";
  return value.slice(11, 19);
}

function formatDateTime(value) {
  if (!value) return "-";
  return value.replace("T", " ").slice(0, 16);
}

function value(raw, unit) {
  if (raw === null || raw === undefined || raw === "") return "-";
  return `${raw} ${unit}`;
}

function escapeHtml(raw) {
  return String(raw ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 1800);
}

async function handleAction(action) {
  let result;
  if (action === "night") {
    result = await api("/api/v1/mock/night-leave-bed", { method: "POST", body: JSON.stringify({ scenario: "standard", elder_id: state.selectedElderId }) });
    showToast("已触发夜间离床事件");
    await loadDashboard(result.event.id, result.event.elder_id);
  } else if (action === "guardian-scenario") {
    const scenarioCode = document.getElementById("scenarioSelect")?.value || "normal_bathroom";
    result = await api(`/api/v1/guardian/scenarios/${encodeURIComponent(scenarioCode)}`, {
      method: "POST",
      body: JSON.stringify({ elder_id: state.selectedElderId }),
    });
    const event = latestEventFromScenario(result);
    showToast(`已触发标准场景：${result.expectation?.label || scenarioCode}`);
    await loadDashboard(event?.id || null, event?.elder_id || state.selectedElderId);
  } else if (action === "sos") {
    result = await api("/api/v1/mock/sos", { method: "POST", body: JSON.stringify({ elder_id: state.selectedElderId }) });
    showToast("已触发 SOS 事件");
    await loadDashboard(result.event.id, result.event.elder_id);
  } else if (action === "health") {
    result = await api("/api/v1/mock/health-abnormal", { method: "POST", body: JSON.stringify({ elder_id: state.selectedElderId }) });
    showToast("已写入健康异常数据并生成日报");
    await loadDashboard(result.event.id, result.event.elder_id);
  } else if (action === "reset") {
    await api("/api/v1/mock/reset", { method: "POST", body: JSON.stringify({}) });
    state.selectedEventId = null;
    state.selectedElderId = "E001";
    showToast("演示数据已重置");
    await loadDashboard();
  } else if (action === "timeout") {
    ensureSelected();
    result = await api(`/api/v1/events/${state.selectedEventId}/timeout`, { method: "POST", body: JSON.stringify({}) });
    showToast("已模拟无响应超时");
    await loadDashboard(result.event.id, result.event.elder_id);
  } else if (action === "return-to-bed") {
    ensureSelected();
    result = await api(`/api/v1/events/${state.selectedEventId}/return-to-bed`, { method: "POST", body: JSON.stringify({}) });
    showToast("已确认返床");
    await loadDashboard(result.event.id, result.event.elder_id);
  } else if (action === "night-turn") {
    result = await submitNightTurn();
    showToast(result.reply_text || "老人原话已处理");
    await loadDashboard(result.event_id, result.elder_id);
  } else if (action === "close") {
    ensureSelected();
    result = await api(`/api/v1/events/${state.selectedEventId}/close`, { method: "POST", body: JSON.stringify({}) });
    showToast("事件已关闭");
    await loadDashboard(result.event.id, result.event.elder_id);
  } else if (action === "daily") {
    await api("/api/v1/reports/daily/generate", { method: "POST", body: JSON.stringify({ elder_id: state.selectedElderId }) });
    showToast("日报已重新生成");
    await loadDashboard(null, state.selectedElderId);
  } else if (action === "weekly") {
    await api("/api/v1/reports/weekly/generate", { method: "POST", body: JSON.stringify({ elder_id: state.selectedElderId }) });
    showToast("周报已重新生成");
    await loadDashboard(null, state.selectedElderId);
  } else if (action === "memory-search") {
    await searchMemories();
    showToast("已筛选回忆");
  }
}

async function submitNightTurn() {
  const input = document.getElementById("nightTurnText");
  const text = input?.value?.trim();
  if (!text) throw new Error("请先输入老人原话");
  const selected = selectedEvent();
  return api("/api/v1/guardian/conversations/night-turn", {
    method: "POST",
    body: JSON.stringify({
      elder_id: state.selectedElderId,
      event_id: selected && selected.status !== "CLOSED" ? selected.id : "",
      text,
      source: "web_demo",
    }),
  });
}

function latestEventFromScenario(result) {
  const rows = [...(result.results || [])].reverse();
  const withEvent = rows.find((item) => item.event);
  return withEvent ? withEvent.event : null;
}

function selectedEvent() {
  return (state.dashboard?.events || []).find((event) => event.id === state.selectedEventId) || state.dashboard?.selected_event || null;
}

function startAutoRefresh() {
  window.setInterval(() => {
    loadDashboard(null, state.selectedElderId).catch(() => {});
  }, 3000);
}

async function handleMemorySample(mockKey) {
  const pool = memorySamplesByElder[state.selectedElderId] || Object.values(memorySamplesByElder).flat();
  const chosenKey = mockKey === "random" ? pool[Math.floor(Math.random() * pool.length)] : mockKey;
  await api("/api/v1/mock/memory-call", {
    method: "POST",
    body: JSON.stringify({ mock_key: chosenKey }),
  });
  showToast("通话录音已分析并写入回忆库");
  await loadDashboard(null, state.selectedElderId);
}

async function handleFeedback(feedbackType) {
  ensureSelected();
  const result = await api(`/api/v1/events/${state.selectedEventId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback_type: feedbackType }),
  });
  showToast("老人反馈已记录");
  await loadDashboard(result.event.id, result.event.elder_id);
}

function ensureSelected() {
  if (!state.selectedEventId) {
    throw new Error("请先选择一个事件");
  }
}

document.addEventListener("click", async (event) => {
  const action = event.target.closest("[data-action]")?.dataset.action;
  const feedback = event.target.closest("[data-feedback]")?.dataset.feedback;
  const memorySample = event.target.closest("[data-memory-sample]")?.dataset.memorySample;
  const utterance = event.target.closest("[data-utterance]")?.dataset.utterance;
  try {
    if (utterance) {
      const input = document.getElementById("nightTurnText");
      if (input) input.value = utterance;
    }
    if (action) await handleAction(action);
    if (feedback) await handleFeedback(feedback);
    if (memorySample) await handleMemorySample(memorySample);
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("nightTurnText")?.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  try {
    const result = await submitNightTurn();
    showToast(result.reply_text || "老人原话已处理");
    await loadDashboard(result.event_id, result.elder_id);
  } catch (error) {
    showToast(error.message);
  }
});

loadDashboard()
  .then(startAutoRefresh)
  .catch((error) => showToast(error.message));
