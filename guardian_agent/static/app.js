const state = {
  elderId: "E001",
  eventId: sessionStorage.getItem("guardian_debug_event_id") || null,
  dashboard: null,
  timer: null,
  requestId: 0,
  mutating: false,
  conversationProvider: "local_rules",
};

const statusLabels = {
  WAITING_ELDER_CONFIRM: "等待老人确认",
  CLARIFYING: "正在追问",
  MONITORING_RETURN: "观察返床",
  WAITING_FAMILY_CONFIRM: "等待子女确认",
  ESCALATED: "已紧急升级",
  CLOSED: "已关闭",
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data?.error) throw new Error(data?.error || "请求失败");
  return data || {};
}

function setCurrentEvent(eventId) {
  state.eventId = eventId || null;
  if (state.eventId) sessionStorage.setItem("guardian_debug_event_id", state.eventId);
  else sessionStorage.removeItem("guardian_debug_event_id");
}

async function loadDashboard(eventId = state.eventId) {
  const requestId = ++state.requestId;
  const params = new URLSearchParams();
  if (eventId) params.set("selected_event_id", eventId);
  if (eventId) params.set("event_id", eventId);
  const data = await api(`/api/v1/debug/session?${params}`);
  if (requestId !== state.requestId) return;
  if (data.conversation_provider) {
    state.conversationProvider = data.conversation_provider;
    configureConversationProvider();
  }
  state.dashboard = { selected_event: data.event };
  const selected = eventId && data.event?.id === eventId ? data.event : null;
  if (eventId && !selected) setCurrentEvent(null);
  render(selected, selected ? data.conversation_turns || [] : [], selected ? data.debug_timer : null, selected ? data.voice_alert : null);
}

function render(event, turns, timer, voiceAlert) {
  renderFlow(event);
  renderCurrentEvent(event);
  renderConversationTurns(turns);
  renderTimeline(event?.timeline || []);
  renderTimer(timer, event);
  renderVoiceAlert(voiceAlert);
  document.getElementById("elderSelect").value = state.elderId;
}

function renderVoiceAlert(command) {
  const box = document.getElementById("voiceAlert");
  if (!command || command.action !== "start_repeating") {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = `
    <div class="voice-alert-box">
      <div><strong>语音告警接口已激活</strong><span>待接入 TTS 模块</span></div>
      <p>“${escapeHtml(command.text)}”</p>
      <small>立即播放，播放完成后每 ${Number(command.repeat_policy?.after_playback_seconds || 2)} 秒重复，直至人工确认。</small>
      <details class="result-json"><summary>查看语音命令</summary><pre>${escapeHtml(JSON.stringify(command, null, 2))}</pre></details>
    </div>`;
}

function renderFlow(event) {
  const steps = [...document.querySelectorAll(".flow-step")];
  const stage = {
    WAITING_ELDER_CONFIRM: 1,
    CLARIFYING: 2,
    MONITORING_RETURN: 3,
    WAITING_FAMILY_CONFIRM: 4,
    ESCALATED: 4,
    CLOSED: 4,
  }[event?.status] ?? 0;
  steps.forEach((step, index) => {
    step.classList.toggle("done", Boolean(event) && index < stage);
    step.classList.toggle("active", index === stage);
  });
}

function renderCurrentEvent(event) {
  const box = document.getElementById("eventDetail");
  const idLabel = document.getElementById("currentEventId");
  const marker = document.getElementById("activeEventMarker");
  if (!event) {
    idLabel.textContent = "尚未开始测试";
    box.innerHTML = '<p class="empty">点击“睡眠带：离床”开始一次新测试。</p>';
    marker.innerHTML = "";
    return;
  }
  idLabel.textContent = event.id;
  marker.innerHTML = `<span class="event-card active" data-event-id="${escapeHtml(event.id)}"></span>`;
  const risky = ["WAITING_FAMILY_CONFIRM", "ESCALATED"].includes(event.status) ? " risk" : "";
  box.innerHTML = `
    <div class="status-banner${risky}">
      <strong>${escapeHtml(statusLabels[event.status] || event.status)}</strong>
      <span>${escapeHtml(event.description || "")}</span>
    </div>
    <dl class="detail-list">
      ${detailRow("事件类型", event.type)}
      ${detailRow("风险等级", event.risk_level)}
      ${detailRow("老人", `${event.elder?.name || event.elder_id || state.elderId}`)}
      ${detailRow("位置", event.location || "-")}
      ${detailRow("更新时间", formatDateTime(event.updated_at || event.created_at))}
    </dl>`;
}

function renderConversationTurns(turns) {
  const box = document.getElementById("conversationTurns");
  if (!turns.length) {
    box.innerHTML = state.conversationProvider === "tuya_agent"
      ? '<p class="empty">在涂鸦在线调试提交老人回答后，这里会自动显示 Agent 判断。</p>'
      : '<p class="empty">提交老人回答后显示结果。</p>';
    return;
  }
  box.innerHTML = turns.map((turn, index) => {
    const request = turn.request || {};
    const response = turn.response || {};
    const result = response.agent_result || response;
    return `
      <article class="conversation-turn">
        <div class="turn-head"><strong>第 ${index + 1} 轮</strong><span>${formatDateTime(turn.created_at)}</span></div>
        <div class="speech">老人：${escapeHtml(request.text || "-")}</div>
        <div class="reply">${result.provider === "tuya_agent" ? "涂鸦 Agent" : "系统"}：${escapeHtml(result.reply_text || response.reply_text || "-")}</div>
        <div class="turn-facts">
          <span>意图：${escapeHtml(result.intent || "-")}</span>
          <span>置信度：${formatConfidence(result.confidence)}</span>
          <span>状态：${escapeHtml(statusLabels[result.event_status] || result.event_status || "-")}</span>
          <span>风险：${escapeHtml(result.risk_level || "-")}</span>
        </div>
        <details class="result-json" open><summary>Agent 格式完整返回</summary><pre>${escapeHtml(JSON.stringify(result, null, 2))}</pre></details>
      </article>`;
  }).join("");
}

function renderTimeline(items) {
  const box = document.getElementById("timeline");
  if (!items.length) {
    box.innerHTML = '<p class="empty">尚无状态变化。</p>';
    return;
  }
  box.innerHTML = items.map((item) => `
    <div class="timeline-item">
      <div class="timeline-time">${formatDateTime(item.created_at)}</div>
      <div class="timeline-title">${escapeHtml(item.title || item.step_type || "状态变化")}</div>
      <div class="timeline-desc">${escapeHtml(item.description || "")}</div>
      ${item.result && Object.keys(item.result).length ? `<details class="timeline-json"><summary>结构化数据</summary><pre>${escapeHtml(JSON.stringify(item.result, null, 2))}</pre></details>` : ""}
    </div>`).join("");
}

function renderTimer(timer, event) {
  state.timer = timer && ["active", "firing"].includes(timer.status) ? timer : null;
  const note = document.getElementById("timerNote");
  if (!event) note.textContent = "触发离床后开始等待老人回答。";
  else if (state.timer) note.textContent = state.timer.timeout_kind === "return_monitor" ? "正在等待返床信号。" : "正在等待老人回答。";
  else note.textContent = "当前没有运行中的计时器。";
  updateTimerClock();
}

function updateTimerClock() {
  const box = document.getElementById("timerClock");
  if (!state.timer) {
    box.innerHTML = "<strong>--</strong><span>未启动</span>";
    return;
  }
  const remaining = Math.max(0, state.timer.deadline_epoch - Date.now() / 1000);
  box.innerHTML = `<strong>${remaining.toFixed(1)}s</strong><span>${escapeHtml(state.timer.timeout_kind || "等待超时")}</span>`;
}

function buildGuardianMessage(eventType, deviceType, data) {
  const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const prefix = { sleep_band: "SLEEP", radar: "RADAR", system: "GUARDIAN" }[deviceType] || "SIM";
  return {
    schema_version: "1.0",
    message_id: `web-debug-${state.elderId}-${eventType.toLowerCase()}-${id}`,
    source_system: "web_debug_simulator",
    device_type: deviceType,
    device_id: `${prefix}-${state.elderId}`,
    elder_id: state.elderId,
    event_type: eventType,
    occurred_at: new Date().toISOString(),
    data,
    raw_payload: { console: "night_full_flow", manual_trigger: true },
  };
}

async function sendSignal(signalType) {
  let message;
  const current = selectedEvent();
  const location = document.getElementById("signalLocation").value;
  if (signalType === "leave-bed") {
    message = buildGuardianMessage("LEAVE_BED", "sleep_band", {
      no_body_seconds: Number(document.getElementById("noBodySeconds").value || 180),
      radar_movement: true,
      night_time: true,
      location,
    });
  } else if (signalType === "fall") {
    message = buildGuardianMessage("FALL_DETECTED", "radar", {
      event_id: current && current.status !== "CLOSED" ? current.id : undefined,
      fall_status: true,
      someone_exists: true,
      location,
    });
  } else if (signalType === "return-to-bed") {
    ensureOpenNightEvent();
    message = buildGuardianMessage("RETURN_TO_BED", "sleep_band", { event_id: current.id, in_bed: true });
  } else if (signalType === "presence") {
    message = buildGuardianMessage("PRESENCE_CHANGED", "radar", {
      event_id: current && current.status !== "CLOSED" ? current.id : undefined,
      someone_exists: true,
      resident_status: "moving",
      fall_status: false,
      location,
    });
  } else throw new Error("未知模拟信号");

  document.getElementById("lastSignalPayload").textContent = JSON.stringify(message, null, 2);
  const response = await api("/api/v1/guardian/messages", { method: "POST", body: JSON.stringify(message) });
  setCurrentEvent(response.event?.id || null);
  await loadDashboard();
  showToast(`已发送 ${message.event_type}`);
  if (signalType === "leave-bed") await maybeAutoStartTimer();
}

async function submitNightTurn() {
  ensureOpenNightEvent();
  const text = document.getElementById("nightTurnText").value.trim();
  if (!text) throw new Error("请先输入老人原话");
  if (state.conversationProvider === "tuya_agent") {
    const agentInput = `【调试事件ID：${state.eventId}】\n老人原话：${text}`;
    await navigator.clipboard.writeText(agentInput);
    showToast("事件 ID 和老人回答已复制，请粘贴到涂鸦在线调试");
    return;
  }
  const response = await api("/api/v1/guardian/conversations/night-turn", {
    method: "POST",
    body: JSON.stringify({ elder_id: state.elderId, event_id: state.eventId, session_id: `web-${state.elderId}`, text, source: "web_debug" }),
  });
  await loadDashboard(response.event_id);
  showToast(response.reply_text || "回答已处理");
  await maybeAutoStartTimer();
}

async function startTimer() {
  ensureOpenNightEvent();
  const input = document.getElementById("timerSeconds");
  const seconds = Number(input.value);
  if (!Number.isFinite(seconds) || seconds < 1 || seconds > 3600) {
    input.focus();
    throw new Error("等待超时必须填写 1 到 3600 秒");
  }
  input.value = String(Math.round(seconds));
  const response = await api("/api/v1/debug/timers/start", { method: "POST", body: JSON.stringify({ event_id: state.eventId, seconds }) });
  state.timer = response.timer;
  updateTimerClock();
  showToast("计时器已启动");
}

async function cancelTimer() {
  ensureCurrentEvent();
  await api("/api/v1/debug/timers/cancel", { method: "POST", body: JSON.stringify({ event_id: state.eventId }) });
  state.timer = null;
  updateTimerClock();
  showToast("计时器已取消");
}

async function fireTimeout() {
  ensureOpenNightEvent();
  const current = selectedEvent();
  const message = buildGuardianMessage("NO_RESPONSE_TIMEOUT", "system", {
    event_id: current.id,
    attempts: current.status === "CLARIFYING" ? 2 : 1,
    timeout_kind: current.status === "MONITORING_RETURN" ? "return_monitor" : "elder_response",
  });
  document.getElementById("lastSignalPayload").textContent = JSON.stringify(message, null, 2);
  const response = await api("/api/v1/guardian/messages", { method: "POST", body: JSON.stringify(message) });
  await loadDashboard(response.event.id);
  showToast("已触发超时");
  if (response.event.status === "CLARIFYING") await maybeAutoStartTimer();
}

async function maybeAutoStartTimer() {
  const current = selectedEvent();
  if (document.getElementById("autoTimer").checked && current && ["WAITING_ELDER_CONFIRM", "CLARIFYING", "MONITORING_RETURN"].includes(current.status)) await startTimer();
}

async function resetDebug() {
  await api("/api/v1/mock/reset", { method: "POST", body: "{}" });
  setCurrentEvent(null);
  state.timer = null;
  document.getElementById("lastSignalPayload").textContent = "尚未发送信号";
  await loadDashboard(null);
  showToast("调试数据已重置");
}

function selectedEvent() {
  const event = state.dashboard?.selected_event;
  return event?.id === state.eventId ? event : null;
}

function ensureCurrentEvent() {
  if (!selectedEvent()) throw new Error("请先触发一次测试事件");
}

function ensureOpenNightEvent() {
  const event = selectedEvent();
  if (!event || event.type !== "POSSIBLE_LEAVE_BED" || event.status === "CLOSED") throw new Error("请先触发一个未关闭的离床事件");
}

function configureConversationProvider() {
  const isTuya = state.conversationProvider === "tuya_agent";
  document.getElementById("agentModeLabel").textContent = isTuya ? "涂鸦 Agent" : "本地规则兜底";
  document.getElementById("agentResultLabel").textContent = isTuya ? "MCP 实际返回" : "Conversation 临时返回";
  document.getElementById("nightTurnButton").textContent = isTuya
    ? "复制回答，前往涂鸦在线调试"
    : "提交文字并查看本地规则返回";
  document.getElementById("agentInputNote").textContent = isTuya
    ? "复制内容会携带当前事件 ID。涂鸦在线调试提交后，本页会自动刷新状态。"
    : "当前使用 conversation.py，仅用于涂鸦不可用时排查状态机。";
}

function detailRow(label, value) { return `<div class="detail-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "-")}</dd></div>`; }
function formatConfidence(value) { return Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "-"; }
function formatDateTime(value) { return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-"; }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]); }
function showToast(message) { const toast = document.getElementById("toast"); toast.textContent = message; toast.classList.add("show"); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.classList.remove("show"), 2200); }
function setBusy(busy) {
  state.mutating = busy;
  document.querySelectorAll("button[data-action], button[data-signal], button[data-timer]").forEach((button) => {
    button.disabled = busy;
  });
}

document.addEventListener("click", async (clickEvent) => {
  const signal = clickEvent.target.closest("[data-signal]")?.dataset.signal;
  const action = clickEvent.target.closest("[data-action]")?.dataset.action;
  const timer = clickEvent.target.closest("[data-timer]")?.dataset.timer;
  const utterance = clickEvent.target.closest("[data-utterance]")?.dataset.utterance;
  if (utterance) document.getElementById("nightTurnText").value = utterance;
  if (!signal && !action && !timer) return;
  if (state.mutating) return;
  try {
    setBusy(true);
    if (signal) await sendSignal(signal);
    if (action === "night-turn") await submitNightTurn();
    if (action === "reset") await resetDebug();
    if (timer === "start") await startTimer();
    if (timer === "cancel") await cancelTimer();
    if (timer === "fire") await fireTimeout();
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
});

document.getElementById("elderSelect").addEventListener("change", async (changeEvent) => {
  state.elderId = changeEvent.target.value;
  setCurrentEvent(null);
  await loadDashboard(null);
});

const timerSecondsInput = document.getElementById("timerSeconds");
if (!timerSecondsInput.value) timerSecondsInput.value = "15";
timerSecondsInput.addEventListener("blur", () => {
  const seconds = Number(timerSecondsInput.value);
  if (!Number.isFinite(seconds) || seconds < 1 || seconds > 3600) timerSecondsInput.value = "15";
});

setInterval(updateTimerClock, 100);
setInterval(() => { if (!state.mutating && state.eventId) loadDashboard().catch(() => {}); }, 1500);

async function initialize() {
  const config = await api("/api/v1/debug/config");
  state.conversationProvider = config.conversation_provider || "local_rules";
  configureConversationProvider();
  await loadDashboard();
}

initialize().catch((error) => showToast(error.message));
