// Lingua frontend — vanilla JS, no build step (mirrors the rest of this repo's
// static-HTML deployment style, but as a fully independent app).

const LANGS = [
  ["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"],
  ["it", "Italian"], ["pt", "Portuguese"], ["ja", "Japanese"], ["ko", "Korean"],
  ["zh", "Chinese (Mandarin)"], ["ru", "Russian"], ["ar", "Arabic"],
  ["nl", "Dutch"], ["sv", "Swedish"], ["pl", "Polish"], ["tr", "Turkish"], ["hi", "Hindi"],
];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  userId: null,
  user: null,
  ws: null,
  mediaRecorder: null,
  audioChunks: [],
  lesson: null, // { exercises, index, correctCount, unitId }
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

function showScreen(id) {
  $$(".screen").forEach((el) => el.classList.add("hidden"));
  $(id).classList.remove("hidden");
}

// ---------- Onboarding ----------

function populateLangSelects() {
  const native = $("#ob-native");
  const target = $("#ob-target");
  for (const [code, name] of LANGS) {
    native.add(new Option(name, code));
    target.add(new Option(name, code));
  }
  native.value = "en";
  target.value = "es";
}

async function handleOnboardingSubmit(e) {
  e.preventDefault();
  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true;
  try {
    const interests = $("#ob-interests").value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const user = await api("/api/users", {
      method: "POST",
      body: JSON.stringify({
        display_name: $("#ob-name").value.trim() || "Learner",
        native_lang: $("#ob-native").value,
        target_lang: $("#ob-target").value,
        level: $("#ob-level").value,
        interests,
      }),
    });
    state.userId = user.id;
    await enterApp();
  } catch (err) {
    alert("Could not create profile: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

// ---------- Sign-in (Google) ----------

async function checkSession() {
  const session = await api("/api/session");
  if (session.authenticated) {
    state.userId = session.user_id;
    await enterApp();
    return;
  }
  if (session.pending) {
    showScreen("#screen-onboarding");
    if (session.name) $("#ob-name").value = session.name;
    return;
  }
  showScreen("#screen-login");
  if (session.dev_login_enabled) {
    $("#dev-login-block").classList.remove("hidden");
  }
  const params = new URLSearchParams(location.search);
  if (params.get("auth_error")) {
    const err = $("#auth-error");
    err.textContent = "Sign-in failed — please try again.";
    err.classList.remove("hidden");
  }
}

function setupDevLogin() {
  $("#dev-login-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const email = $("#dev-login-email").value.trim();
    if (!email) return;
    location.href = `/auth/dev-login?email=${encodeURIComponent(email)}`;
  });
}

async function signOut() {
  await fetch("/auth/logout", { method: "POST" });
  state.userId = null;
  state.user = null;
  if (state.ws) state.ws.close();
  location.href = "/";
}

// ---------- Main app shell ----------

async function enterApp() {
  state.user = await api(`/api/users/${state.userId}`);
  showScreen("#screen-main");
  await Promise.all([loadPath(), loadProgress()]);
}

function refreshTopbar(progress) {
  $("#stat-xp").textContent = progress.xp;
  $("#stat-streak").textContent = progress.streak_days;
  $("#stat-hearts").textContent = progress.hearts;
  $("#stat-level").textContent = progress.level;
}

async function loadProgress() {
  const progress = await api(`/api/progress/${state.userId}`);
  refreshTopbar(progress);
  return progress;
}

// ---------- Dashboard (Progress tab) ----------

function showTooltip(target, text) {
  const tip = $("#chart-tooltip");
  tip.textContent = text;
  tip.style.top = `${target.getBoundingClientRect().top}px`;
  tip.classList.remove("hidden");

  // Center on the target, then clamp so the tooltip's own width (only known
  // once it's rendered, hence measuring after unhiding) never pushes it past
  // the viewport edge — otherwise the last heat-strip cell's tooltip clips.
  const rect = target.getBoundingClientRect();
  const margin = 8;
  const half = tip.offsetWidth / 2;
  let center = rect.left + rect.width / 2;
  center = Math.max(half + margin, Math.min(center, window.innerWidth - half - margin));
  tip.style.left = `${center}px`;
}

function hideTooltip() {
  $("#chart-tooltip").classList.add("hidden");
}

function renderStatRow(data) {
  const tiles = [
    ["⭐", data.xp, "XP"],
    ["🔥", data.streak_days, "Day streak"],
    ["❤️", data.hearts, "Hearts"],
    ["🏅", data.level, "Level"],
  ];
  const row = $("#dash-stat-row");
  row.innerHTML = "";
  for (const [icon, value, label] of tiles) {
    const tile = document.createElement("div");
    tile.className = "stat-tile";
    const iconEl = document.createElement("div");
    iconEl.className = "stat-icon";
    iconEl.textContent = icon;
    const valueEl = document.createElement("span");
    valueEl.className = "stat-value";
    valueEl.textContent = value;
    const labelEl = document.createElement("span");
    labelEl.className = "stat-label";
    labelEl.textContent = label;
    tile.append(iconEl, valueEl, labelEl);
    row.appendChild(tile);
  }
}

function renderLevelMeter(data) {
  const el = $("#dash-level-meter");
  el.innerHTML = "";
  if (!data.next_level) {
    const maxed = document.createElement("p");
    maxed.className = "level-meter-maxed";
    maxed.textContent = `You've reached ${data.level} — full native-level polish unlocked.`;
    el.appendChild(maxed);
    return;
  }
  const row = document.createElement("div");
  row.className = "level-meter-row";
  const badge = document.createElement("span");
  badge.className = "level-badge";
  badge.textContent = data.level;
  const target = document.createElement("span");
  target.textContent = `→ ${data.next_level}`;
  row.append(badge, target);

  const track = document.createElement("div");
  track.className = "meter-track";
  const fill = document.createElement("div");
  fill.className = "meter-fill";
  const required = data.units_required_for_next_level || 1;
  const pct = Math.min(100, Math.round((data.units_mastered_current_level / required) * 100));
  fill.style.width = `${pct}%`;
  track.appendChild(fill);

  const caption = document.createElement("p");
  caption.className = "level-meter-caption";
  caption.textContent = `${data.units_mastered_current_level} of ${required} units mastered to unlock ${data.next_level}`;

  el.append(row, track, caption);
}

function renderDueCard(data) {
  const card = $("#dash-due-card");
  if (data.due_reviews > 0) {
    card.classList.remove("hidden");
    $("#dash-due-headline").textContent = `${data.due_reviews} word${data.due_reviews === 1 ? "" : "s"} due for review`;
  } else {
    card.classList.add("hidden");
  }
}

function renderActivity(data) {
  const el = $("#dash-activity");
  el.innerHTML = "";
  const maxCount = Math.max(1, ...data.activity.map((d) => d.lessons_completed));
  const todayStr = new Date().toISOString().slice(0, 10);
  data.activity.forEach((day) => {
    const cell = document.createElement("div");
    cell.className = "activity-cell";
    if (day.date === todayStr) cell.classList.add("today");
    if (day.lessons_completed > 0) {
      const intensity = day.lessons_completed / maxCount;
      const step = intensity > 0.66 ? "700" : intensity > 0.33 ? "500" : "300";
      cell.style.background = `var(--seq-${step})`;
    }
    const label = `${day.lessons_completed} lesson${day.lessons_completed === 1 ? "" : "s"} on ${day.date}`;
    cell.setAttribute("tabindex", "0");
    cell.setAttribute("aria-label", label);
    cell.addEventListener("pointerenter", () => showTooltip(cell, label));
    cell.addEventListener("focus", () => showTooltip(cell, label));
    cell.addEventListener("pointerleave", hideTooltip);
    cell.addEventListener("blur", hideTooltip);
    el.appendChild(cell);
  });
}

function renderMasteryChart(data) {
  const el = $("#dash-mastery");
  el.innerHTML = "";
  for (const entry of data.mastery_by_level) {
    const row = document.createElement("div");
    row.className = "mastery-row" + (entry.level === data.level ? " current" : "");

    const levelEl = document.createElement("div");
    levelEl.className = "mastery-level";
    levelEl.textContent = entry.level;

    const track = document.createElement("div");
    track.className = "meter-track";
    const fill = document.createElement("div");
    fill.className = "meter-fill";
    const pct = entry.total ? Math.round((entry.mastered / entry.total) * 100) : 0;
    fill.style.width = `${pct}%`;
    track.appendChild(fill);

    const countEl = document.createElement("div");
    countEl.className = "mastery-count";
    countEl.textContent = `${entry.mastered}/${entry.total}`;

    row.append(levelEl, track, countEl);
    el.appendChild(row);
  }
}

function renderRecentLessons(data) {
  const el = $("#dash-recent");
  el.innerHTML = "";
  if (data.recent_lessons.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "Complete a lesson to see it here.";
    el.appendChild(empty);
    return;
  }
  for (const lesson of data.recent_lessons) {
    const row = document.createElement("div");
    row.className = "recent-row";

    const left = document.createElement("div");
    const topic = document.createElement("div");
    topic.className = "recent-topic";
    topic.textContent = lesson.topic;
    const date = document.createElement("div");
    date.className = "recent-date";
    date.textContent = new Date(lesson.completed_at).toLocaleDateString();
    left.append(topic, date);

    const score = document.createElement("span");
    score.className = "recent-score " + (lesson.score >= 0.8 ? "high" : "low");
    score.textContent = `${Math.round(lesson.score * 100)}%`;

    row.append(left, score);
    el.appendChild(row);
  }
}

async function loadDashboard() {
  const data = await api(`/api/progress/${state.userId}/dashboard`);
  refreshTopbar(data);
  renderStatRow(data);
  renderLevelMeter(data);
  renderDueCard(data);
  renderActivity(data);
  renderMasteryChart(data);
  renderRecentLessons(data);
}

async function loadPath() {
  const units = await api(`/api/lessons/${state.userId}/path`);
  const container = $("#skill-path");
  container.innerHTML = "";
  let lastLevel = null;
  for (const unit of units) {
    if (unit.level !== lastLevel) {
      const heading = document.createElement("div");
      heading.className = "level-heading";
      heading.textContent = `Level ${unit.level}`;
      container.appendChild(heading);
      lastLevel = unit.level;
    }
    const btn = document.createElement("button");
    btn.className = `unit-node ${unit.state}`;
    btn.textContent = unit.topic;
    btn.disabled = unit.state === "locked";
    btn.addEventListener("click", () => startLesson(unit.id));
    container.appendChild(btn);
  }
}

// ---------- Tabs ----------

function setupTabs() {
  $$(".tab-btn[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".tab-btn[data-tab]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      $$(".tab-panel").forEach((p) => p.classList.add("hidden"));
      $(`#tab-${btn.dataset.tab}`).classList.remove("hidden");
      if (btn.dataset.tab === "talk") ensureConversationSocket();
      if (btn.dataset.tab === "progress") loadDashboard();
    });
  });
}

// ---------- Lesson flow ----------

async function startLesson(unitId) {
  showScreen("#screen-lesson");
  $("#exercise-container").innerHTML = "<p>Preparing your personalized lesson…</p>";
  try {
    const exercises = await api(`/api/lessons/${state.userId}/unit/${unitId}`);
    state.lesson = { exercises, index: 0, correctCount: 0, unitId };
    $("#lesson-hearts-count").textContent = state.user.hearts;
    renderCurrentExercise();
  } catch (err) {
    $("#exercise-container").innerHTML = `<p>Could not load lesson: ${err.message}</p>`;
  }
}

$("#lesson-exit").addEventListener("click", async () => {
  state.lesson = null;
  showScreen("#screen-main");
  await loadPath();
});

function updateLessonProgressBar() {
  const { index, exercises } = state.lesson;
  const pct = Math.round((index / exercises.length) * 100);
  $("#lesson-progress-bar").style.width = `${pct}%`;
}

async function playAudio(text, targetLang) {
  try {
    const res = await fetch("/api/content/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, target_lang: targetLang }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    new Audio(URL.createObjectURL(blob)).play().catch(() => {});
  } catch {
    // best-effort; missing HF_TOKEN just means silent demo mode
  }
}

async function loadImage(imgEl, prompt) {
  try {
    const res = await fetch("/api/content/image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    imgEl.src = URL.createObjectURL(blob);
  } catch {
    // demo mode without HF_TOKEN: leave placeholder background
  }
}

function normalize(s) {
  return (s || "").toLowerCase().trim().replace(/[.,!?¿¡'"]/g, "");
}

async function recordAnswer(exercise, correct) {
  state.lesson.correctCount += correct ? 1 : 0;
  try {
    const result = await api(`/api/lessons/${state.userId}/answer`, {
      method: "POST",
      body: JSON.stringify({ vocab_key: exercise.vocab_key, correct, attempts_before_correct: 0 }),
    });
    $("#lesson-hearts-count").textContent = result.hearts;
  } catch {
    // non-fatal for the demo
  }
}

function showFeedback(container, correct, extra) {
  const banner = document.createElement("div");
  banner.className = `feedback-banner ${correct ? "correct" : "incorrect"}`;
  banner.textContent = correct ? "Correct! 🎉" : `Not quite. ${extra || ""}`;
  container.appendChild(banner);
  const next = document.createElement("button");
  next.className = "btn btn-primary";
  next.textContent = "Continue";
  next.style.marginTop = "8px";
  next.addEventListener("click", () => {
    state.lesson.index += 1;
    renderCurrentExercise();
  });
  container.appendChild(next);
}

function renderCurrentExercise() {
  const { exercises, index } = state.lesson;
  updateLessonProgressBar();
  if (index >= exercises.length) {
    finishLesson();
    return;
  }
  const ex = exercises[index];
  const container = $("#exercise-container");
  container.innerHTML = "";

  const promptEl = document.createElement("div");
  promptEl.className = "exercise-prompt";
  promptEl.textContent = ex.prompt || "Translate / answer:";
  container.appendChild(promptEl);

  const targetLang = state.user.target_lang;

  const renderers = {
    image_match: renderImageMatch,
    multiple_choice: renderMultipleChoice,
    listen_type: renderListenType,
    translate_to_target: renderTranslate,
    translate_to_native: renderTranslate,
    fill_blank: renderTranslate,
    speak_repeat: renderSpeakRepeat,
    free_conversation_prompt: renderFreeConversation,
  };
  (renderers[ex.type] || renderTranslate)(ex, container, targetLang);
}

function renderImageMatch(ex, container, targetLang) {
  const img = document.createElement("img");
  img.className = "exercise-image";
  container.appendChild(img);
  loadImage(img, ex.image_prompt || ex.target_text);
  playAudio(ex.audio_text || ex.target_text, targetLang);

  const opts = document.createElement("div");
  opts.className = "exercise-options";
  const choices = ex.options && ex.options.length ? ex.options : [ex.correct_answer];
  for (const choice of choices) {
    const btn = document.createElement("button");
    btn.className = "option-btn";
    btn.textContent = choice;
    btn.addEventListener("click", async () => {
      const correct = normalize(choice) === normalize(ex.correct_answer);
      btn.classList.add(correct ? "correct" : "incorrect");
      opts.querySelectorAll("button").forEach((b) => (b.disabled = true));
      await recordAnswer(ex, correct);
      showFeedback(container, correct, `Answer: ${ex.correct_answer}`);
    });
    opts.appendChild(btn);
  }
  container.appendChild(opts);
}

function renderMultipleChoice(ex, container) {
  const opts = document.createElement("div");
  opts.className = "exercise-options";
  const choices = ex.options && ex.options.length ? ex.options : [ex.correct_answer];
  for (const choice of choices) {
    const btn = document.createElement("button");
    btn.className = "option-btn";
    btn.textContent = choice;
    btn.addEventListener("click", async () => {
      const correct = normalize(choice) === normalize(ex.correct_answer);
      btn.classList.add(correct ? "correct" : "incorrect");
      opts.querySelectorAll("button").forEach((b) => (b.disabled = true));
      await recordAnswer(ex, correct);
      showFeedback(container, correct, `Answer: ${ex.correct_answer}`);
    });
    opts.appendChild(btn);
  }
  container.appendChild(opts);
}

function renderListenType(ex, container, targetLang) {
  const btn = document.createElement("button");
  btn.className = "audio-btn";
  btn.textContent = "🔊";
  btn.addEventListener("click", () => playAudio(ex.audio_text || ex.target_text, targetLang));
  container.appendChild(btn);
  playAudio(ex.audio_text || ex.target_text, targetLang);
  renderTextInput(ex, container);
}

function renderTranslate(ex, container) {
  const source = ex.native_text || ex.target_text;
  if (source) {
    const src = document.createElement("div");
    src.className = "exercise-prompt";
    src.textContent = source;
    container.appendChild(src);
  }
  renderTextInput(ex, container);
}

function renderTextInput(ex, container) {
  const row = document.createElement("div");
  row.className = "exercise-input-row";
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Type your answer…";
  const submit = document.createElement("button");
  submit.className = "btn btn-primary";
  submit.textContent = "Check";
  row.appendChild(input);
  row.appendChild(submit);
  container.appendChild(row);

  const submitAnswer = async () => {
    const correct = normalize(input.value) === normalize(ex.correct_answer);
    submit.disabled = true;
    input.disabled = true;
    await recordAnswer(ex, correct);
    showFeedback(container, correct, `Answer: ${ex.correct_answer}`);
  };
  submit.addEventListener("click", submitAnswer);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitAnswer();
  });
}

function renderSpeakRepeat(ex, container, targetLang) {
  const phrase = document.createElement("div");
  phrase.className = "exercise-prompt";
  phrase.textContent = ex.target_text;
  container.appendChild(phrase);

  const playBtn = document.createElement("button");
  playBtn.className = "audio-btn";
  playBtn.textContent = "🔊";
  playBtn.addEventListener("click", () => playAudio(ex.audio_text || ex.target_text, targetLang));
  container.appendChild(playBtn);
  playAudio(ex.audio_text || ex.target_text, targetLang);

  const recordBtn = document.createElement("button");
  recordBtn.className = "btn btn-primary";
  recordBtn.textContent = "🎙️ Hold & repeat";
  container.appendChild(recordBtn);

  const heard = document.createElement("div");
  heard.className = "exercise-prompt";
  container.appendChild(heard);

  let chunks = [];
  let recorder = null;

  const start = async (e) => {
    e.preventDefault();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (ev) => chunks.push(ev.data);
    recorder.start();
    recordBtn.textContent = "Recording…";
  };
  const stop = async () => {
    if (!recorder || recorder.state === "inactive") return;
    recorder.stop();
    recordBtn.textContent = "🎙️ Hold & repeat";
    await new Promise((resolve) => (recorder.onstop = resolve));
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    const res = await fetch("/api/content/stt", {
      method: "POST",
      headers: { "Content-Type": blob.type },
      body: blob,
    });
    const data = await res.json().catch(() => ({ text: "" }));
    heard.textContent = data.text ? `We heard: "${data.text}"` : "Could not transcribe — self-check below.";

    const selfCheck = document.createElement("div");
    selfCheck.className = "exercise-options";
    const yes = document.createElement("button");
    yes.className = "option-btn";
    yes.textContent = "I said it correctly";
    const no = document.createElement("button");
    no.className = "option-btn";
    no.textContent = "Need more practice";
    selfCheck.appendChild(yes);
    selfCheck.appendChild(no);
    container.appendChild(selfCheck);
    const finish = async (correct) => {
      selfCheck.querySelectorAll("button").forEach((b) => (b.disabled = true));
      await recordAnswer(ex, correct);
      showFeedback(container, correct, "");
    };
    yes.addEventListener("click", () => finish(true));
    no.addEventListener("click", () => finish(false));
  };

  recordBtn.addEventListener("mousedown", start);
  recordBtn.addEventListener("touchstart", start);
  recordBtn.addEventListener("mouseup", stop);
  recordBtn.addEventListener("mouseleave", stop);
  recordBtn.addEventListener("touchend", stop);
}

function renderFreeConversation(ex, container) {
  const row = document.createElement("div");
  row.className = "exercise-input-row";
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Write a few sentences in response…";
  const submit = document.createElement("button");
  submit.className = "btn btn-primary";
  submit.textContent = "Done";
  row.appendChild(input);
  row.appendChild(submit);
  container.appendChild(row);

  submit.addEventListener("click", async () => {
    const correct = input.value.trim().length > 0;
    submit.disabled = true;
    input.disabled = true;
    await recordAnswer(ex, correct);
    showFeedback(container, correct, correct ? "" : "Try writing a short answer next time.");
  });
}

async function finishLesson() {
  const { exercises, correctCount, unitId } = state.lesson;
  const score = exercises.length ? correctCount / exercises.length : 0;
  const result = await api(`/api/lessons/${state.userId}/complete`, {
    method: "POST",
    body: JSON.stringify({ unit_id: unitId, score }),
  });
  $("#complete-xp").textContent = `+${result.xp_gained} XP (total ${result.xp_total}) · 🔥 ${result.streak_days} day streak`;
  $("#complete-level").textContent = result.leveled_up
    ? `🎊 Level up! You're now at ${result.leveled_up}.`
    : result.mastered
      ? "Unit mastered!"
      : "Keep practicing this unit to master it.";
  showScreen("#screen-complete");
}

$("#complete-continue").addEventListener("click", async () => {
  state.lesson = null;
  showScreen("#screen-main");
  state.user = await api(`/api/users/${state.userId}`);
  await Promise.all([loadPath(), loadProgress()]);
});

// ---------- Conversation ("Talk Live") ----------

function ensureConversationSocket() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/conversation/${state.userId}`);
  state.ws = ws;

  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "ready") {
      $("#call-status").textContent = msg.message;
    } else if (msg.type === "transcript") {
      addTranscriptBubble("user", msg.text);
    } else if (msg.type === "reply") {
      addTranscriptBubble("assistant", msg.text);
      if (msg.audio_base64) {
        playConversationAudio(msg.audio_base64);
      }
    } else if (msg.type === "error") {
      $("#call-status").textContent = msg.message;
    }
  });
  ws.addEventListener("close", () => {
    $("#call-status").textContent = "Disconnected — switch tabs back to reconnect.";
  });
}

function addTranscriptBubble(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  $("#transcript").appendChild(div);
  $("#transcript").scrollTop = $("#transcript").scrollHeight;
}

function playConversationAudio(base64) {
  const avatar = $("#avatar");
  const bytes = atob(base64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  const blob = new Blob([arr], { type: "audio/flac" });
  const audio = new Audio(URL.createObjectURL(blob));
  avatar.classList.add("speaking");
  audio.addEventListener("ended", () => avatar.classList.remove("speaking"));
  audio.play().catch(() => avatar.classList.remove("speaking"));
}

function blobToBase64(blob) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result.split(",")[1]);
    reader.readAsDataURL(blob);
  });
}

function setupMic() {
  const micBtn = $("#mic-btn");
  const avatar = $("#avatar");
  let stream = null;

  const start = async (e) => {
    e.preventDefault();
    ensureConversationSocket();
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.audioChunks = [];
    state.mediaRecorder = new MediaRecorder(stream);
    state.mediaRecorder.ondataavailable = (ev) => state.audioChunks.push(ev.data);
    state.mediaRecorder.start();
    micBtn.classList.add("recording");
    micBtn.textContent = "🔴 Listening…";
    avatar.classList.add("listening");
  };

  const stop = async () => {
    if (!state.mediaRecorder || state.mediaRecorder.state === "inactive") return;
    state.mediaRecorder.stop();
    micBtn.classList.remove("recording");
    micBtn.textContent = "🎙️ Hold to talk";
    avatar.classList.remove("listening");
    await new Promise((resolve) => (state.mediaRecorder.onstop = resolve));
    stream.getTracks().forEach((t) => t.stop());
    const blob = new Blob(state.audioChunks, { type: state.mediaRecorder.mimeType || "audio/webm" });
    if (blob.size < 500) return; // too short to be real speech
    const b64 = await blobToBase64(blob);
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: "audio", data: b64, content_type: blob.type }));
    }
  };

  micBtn.addEventListener("mousedown", start);
  micBtn.addEventListener("touchstart", start);
  micBtn.addEventListener("mouseup", stop);
  micBtn.addEventListener("mouseleave", stop);
  micBtn.addEventListener("touchend", stop);

  $("#text-fallback-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("#text-fallback-input");
    if (!input.value.trim()) return;
    ensureConversationSocket();
    if (state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: "text", data: input.value.trim() }));
    }
    input.value = "";
  });
}

$("#switch-user-btn").addEventListener("click", signOut);

// ---------- Boot ----------

async function boot() {
  populateLangSelects();
  $("#onboarding-form").addEventListener("submit", handleOnboardingSubmit);
  setupTabs();
  setupMic();
  setupDevLogin();
  await checkSession();
}

boot();
