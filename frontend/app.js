// Lingua frontend — vanilla JS, no build step (mirrors the rest of this repo's
// static-HTML deployment style, but as a fully independent app).

// Any language the tutor chat model knows works for exercises/conversation —
// this list is what's offered in the picker, not a hard backend restriction.
// Keep in sync with backend/hf_client.py's _MMS_LANG_CODES for TTS voice
// coverage (a language missing from that map still teaches fully via text/
// chat, it just falls back to an English voice for audio).
const LANGS = [
  ["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"],
  ["it", "Italian"], ["pt", "Portuguese"], ["ja", "Japanese"], ["ko", "Korean"],
  ["zh", "Chinese (Mandarin)"], ["ru", "Russian"], ["ar", "Arabic"],
  ["nl", "Dutch"], ["sv", "Swedish"], ["pl", "Polish"], ["tr", "Turkish"], ["hi", "Hindi"],
  ["id", "Indonesian"], ["vi", "Vietnamese"], ["th", "Thai"], ["uk", "Ukrainian"],
  ["el", "Greek"], ["he", "Hebrew"], ["cs", "Czech"], ["ro", "Romanian"],
  ["hu", "Hungarian"], ["fi", "Finnish"], ["da", "Danish"], ["no", "Norwegian"],
  ["bg", "Bulgarian"], ["sk", "Slovak"], ["hr", "Croatian"], ["sr", "Serbian"],
  ["lt", "Lithuanian"], ["lv", "Latvian"], ["et", "Estonian"], ["sl", "Slovenian"],
  ["fa", "Persian (Farsi)"], ["ur", "Urdu"], ["bn", "Bengali"], ["ta", "Tamil"],
  ["te", "Telugu"], ["mr", "Marathi"], ["gu", "Gujarati"], ["pa", "Punjabi"],
  ["ml", "Malayalam"], ["kn", "Kannada"], ["ne", "Nepali"], ["si", "Sinhala"],
  ["my", "Burmese"], ["km", "Khmer"], ["lo", "Lao"], ["ms", "Malay"],
  ["tl", "Tagalog (Filipino)"], ["sw", "Swahili"], ["am", "Amharic"], ["so", "Somali"],
  ["ha", "Hausa"], ["yo", "Yoruba"], ["ig", "Igbo"], ["zu", "Zulu"], ["xh", "Xhosa"],
  ["af", "Afrikaans"], ["is", "Icelandic"], ["ga", "Irish"], ["cy", "Welsh"],
  ["mt", "Maltese"], ["eu", "Basque"], ["ca", "Catalan"], ["gl", "Galician"],
  ["az", "Azerbaijani"], ["kk", "Kazakh"], ["uz", "Uzbek"], ["mn", "Mongolian"],
  ["ka", "Georgian"], ["hy", "Armenian"], ["sq", "Albanian"], ["mk", "Macedonian"],
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

function readInterests() {
  return $("#ob-interests").value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

async function createProfileAndEnter(level) {
  const user = await api("/api/users", {
    method: "POST",
    body: JSON.stringify({
      display_name: $("#ob-name").value.trim() || "Learner",
      native_lang: $("#ob-native").value,
      target_lang: $("#ob-target").value,
      level,
      interests: readInterests(),
    }),
  });
  state.userId = user.id;
  await enterApp();
}

function showOnboardingStep(id) {
  $$("#screen-onboarding .onboarding-card").forEach((el) => el.classList.add("hidden"));
  $(id).classList.remove("hidden");
}

async function handleOnboardingSubmit(e) {
  e.preventDefault();
  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true;
  try {
    await startPlacementTest();
  } catch (err) {
    alert("Could not start placement test: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

// ---------- Adaptive placement test ----------

const PLACEMENT_TOTAL = 6;
const placement = { history: [], current: null };

async function startPlacementTest() {
  placement.history = [];
  showOnboardingStep("#onboarding-step-placement");
  await fetchNextPlacementQuestion();
}

async function fetchNextPlacementQuestion() {
  const el = $("#placement-exercise");
  el.innerHTML = "<p>Preparing your next question…</p>";
  const data = await api("/api/placement", {
    method: "POST",
    body: JSON.stringify({
      native_lang: $("#ob-native").value,
      target_lang: $("#ob-target").value,
      interests: readInterests(),
      history: placement.history,
    }),
  });
  if (data.done) {
    await finishPlacementTest(data.recommended_level);
    return;
  }
  placement.current = data;
  $("#placement-progress").textContent = `Question ${data.question_number} of ${PLACEMENT_TOTAL}`;
  $("#placement-progress-bar").style.width = `${Math.round(((data.question_number - 1) / PLACEMENT_TOTAL) * 100)}%`;
  renderPlacementQuestion(data.exercise, data.level, el);
}

function renderPlacementQuestion(ex, level, container) {
  container.innerHTML = "";

  const prompt = document.createElement("div");
  prompt.className = "exercise-prompt";
  prompt.textContent = ex.prompt || ex.target_text;
  container.appendChild(prompt);

  if (ex.native_text) {
    const hint = document.createElement("p");
    hint.className = "subtitle";
    hint.textContent = ex.native_text;
    container.appendChild(hint);
  }

  const target = document.createElement("div");
  target.className = "exercise-prompt";
  target.textContent = ex.target_text;
  container.appendChild(target);

  const submit = (answer) => {
    const correct = normalize(answer) === normalize(ex.correct_answer);
    placement.history.push({ level, correct });
    fetchNextPlacementQuestion();
  };

  if (ex.options && ex.options.length) {
    const opts = document.createElement("div");
    opts.className = "exercise-options";
    for (const choice of ex.options) {
      const btn = document.createElement("button");
      btn.className = "option-btn";
      btn.textContent = choice;
      btn.addEventListener("click", () => submit(choice));
      opts.appendChild(btn);
    }
    container.appendChild(opts);
  } else {
    const row = document.createElement("div");
    row.className = "exercise-input-row";
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Type your answer…";
    const btn = document.createElement("button");
    btn.className = "btn btn-primary";
    btn.textContent = "Check";
    row.append(input, btn);
    container.appendChild(row);
    const go = () => submit(input.value);
    btn.addEventListener("click", go);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
    });
  }
}

async function finishPlacementTest(recommendedLevel) {
  $("#placement-progress-bar").style.width = "100%";
  $("#placement-result-level").textContent = recommendedLevel;
  showOnboardingStep("#onboarding-step-result");
  $("#placement-continue").onclick = () => createProfileAndEnter(recommendedLevel).catch((err) => alert(err.message));
}

$("#ob-skip-fluent").addEventListener("click", () => {
  createProfileAndEnter("NATIVE").catch((err) => alert("Could not create profile: " + err.message));
});

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
  $("#stat-gems").textContent = progress.gems;
  $("#stat-level").textContent = progress.level;
}

async function loadProgress() {
  const progress = await api(`/api/progress/${state.userId}`);
  refreshTopbar(progress);
  return progress;
}

// ---------- Dashboard (Progress tab) ----------

function animateCountUp(el, target) {
  const duration = 500;
  const start = performance.now();
  const from = 0;
  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(from + (target - from) * eased);
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function renderStatRow(data) {
  const tiles = [
    ["🔥", data.streak_days, "Day streak", "fire"],
    ["💎", data.gems, "Gems", "gem"],
    ["❤️", data.hearts, "Hearts", "heart"],
    ["⭐", data.xp, "XP", "xp"],
    ["🏅", data.level, "Level", "level"],
  ];
  const row = $("#dash-stat-row");
  row.innerHTML = "";
  for (const [icon, value, label, tone] of tiles) {
    const tile = document.createElement("div");
    tile.className = "stat-tile";
    const iconEl = document.createElement("div");
    iconEl.className = `stat-icon stat-icon-${tone}`;
    iconEl.textContent = icon;
    const valueEl = document.createElement("span");
    valueEl.className = "stat-value";
    const labelEl = document.createElement("span");
    labelEl.className = "stat-label";
    labelEl.textContent = label;
    tile.append(iconEl, valueEl, labelEl);
    row.appendChild(tile);
    if (typeof value === "number") {
      animateCountUp(valueEl, value);
    } else {
      valueEl.textContent = value;
    }
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

function isDarkMode() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

const charts = {};
function renderChart(canvasId, config) {
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart($(`#${canvasId}`), config);
  return charts[canvasId];
}

function renderActivity(data) {
  const dark = isDarkMode();
  const gridColor = dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
  const tickColor = dark ? "#a8b3ba" : "#898781";
  const todayStr = new Date().toISOString().slice(0, 10);
  const labels = data.activity.map((d) =>
    new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric" })
  );
  const values = data.activity.map((d) => d.lessons_completed);
  const barColor = data.activity.map((d) => (d.date === todayStr ? "#1489c4" : "#1cb0f6"));

  renderChart("dash-activity-chart", {
    type: "bar",
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: barColor, borderRadius: 5, maxBarThickness: 22 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => data.activity[items[0].dataIndex].date,
            label: (item) => `${item.raw} lesson${item.raw === 1 ? "" : "s"}`,
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: tickColor, font: { size: 10 } } },
        y: { beginAtZero: true, ticks: { precision: 0, color: tickColor }, grid: { color: gridColor } },
      },
    },
  });
}

function renderMasteryChart(data) {
  const dark = isDarkMode();
  const gridColor = dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
  const tickColor = dark ? "#a8b3ba" : "#898781";
  const entries = data.mastery_by_level;
  const labels = entries.map((e) => e.level);
  const pct = entries.map((e) => (e.total ? Math.round((e.mastered / e.total) * 100) : 0));
  const colors = entries.map((e) => (e.level === data.level ? "#1cb0f6" : dark ? "#2c5490" : "#9ec5f4"));

  renderChart("dash-mastery-chart", {
    type: "bar",
    data: {
      labels,
      datasets: [{ data: pct, backgroundColor: colors, borderRadius: 6, maxBarThickness: 26 }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => {
              const e = entries[item.dataIndex];
              return `${e.mastered}/${e.total} units mastered`;
            },
          },
        },
      },
      scales: {
        x: { min: 0, max: 100, ticks: { display: false }, grid: { color: gridColor } },
        y: { grid: { display: false }, ticks: { color: tickColor, font: { weight: "bold" } } },
      },
    },
  });
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
  // Each section renders independently — a failure in one (e.g. the charts'
  // CDN script blocked by a network/ad-blocker) must not blank out the rest
  // of the dashboard.
  const sections = [
    refreshTopbar, renderStatRow, renderMascot, renderLeaderboard,
    renderLevelMeter, renderDueCard, renderActivity, renderMasteryChart,
    renderRecentLessons, setupShop,
  ];
  for (const render of sections) {
    try {
      render(data);
    } catch (err) {
      console.error(`Dashboard section "${render.name}" failed to render`, err);
    }
  }
}

function renderMascot(data) {
  const card = $("#mascot-card");
  const badge = $("#mascot-badge");
  const message = $("#mascot-message");
  card.classList.remove("mood-sad", "mood-cool", "mood-fire", "mood-curious", "mood-happy");
  if (data.hearts === 0) {
    card.classList.add("mood-sad");
    badge.textContent = "💔";
    message.textContent = "Out of hearts! Refill them in the gem shop or wait for tomorrow.";
  } else if (data.streak_freezes > 0) {
    card.classList.add("mood-cool");
    badge.textContent = "🧊";
    message.textContent = `${data.streak_freezes} streak freeze${data.streak_freezes === 1 ? "" : "s"} banked — your streak is protected if you miss a day.`;
  } else if (data.streak_days >= 7) {
    card.classList.add("mood-fire");
    badge.textContent = "🔥";
    message.textContent = `${data.streak_days}-day streak! You're on fire — keep it going.`;
  } else if (data.due_reviews > 0) {
    card.classList.add("mood-curious");
    badge.textContent = "🧐";
    message.textContent = `${data.due_reviews} word${data.due_reviews === 1 ? "" : "s"} ready for review in your next lesson.`;
  } else if (data.streak_days > 0) {
    card.classList.add("mood-happy");
    badge.textContent = "😊";
    message.textContent = `${data.streak_days} day streak — nice work, don't break it!`;
  } else {
    badge.textContent = "👋";
    message.textContent = "Ready for your first lesson today?";
  }
}

const AVATAR_PALETTE = ["#1cb0f6", "#58cc02", "#ff9600", "#ce82ff", "#ff4b4b", "#ffc800"];
function avatarColor(name) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}
function initials(name) {
  return (name || "?").trim().slice(0, 2).toUpperCase();
}

function renderLeaderboard(data) {
  const el = $("#dash-leaderboard");
  el.innerHTML = "";
  if (data.leaderboard.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "Complete a lesson this week to join the leaderboard.";
    el.appendChild(empty);
    return;
  }
  const medals = { 1: "🥇", 2: "🥈", 3: "🥉" };
  for (const entry of data.leaderboard) {
    const row = document.createElement("div");
    row.className = "leaderboard-row" + (entry.is_you ? " is-you" : "");

    const rank = document.createElement("span");
    rank.className = "leaderboard-rank";
    rank.textContent = medals[entry.rank] || `#${entry.rank}`;

    const avatar = document.createElement("span");
    avatar.className = "leaderboard-avatar";
    avatar.style.background = avatarColor(entry.display_name);
    avatar.textContent = initials(entry.display_name);

    const name = document.createElement("span");
    name.className = "leaderboard-name";
    name.textContent = entry.is_you ? `${entry.display_name} (you)` : entry.display_name;

    const xp = document.createElement("span");
    xp.className = "leaderboard-xp";
    xp.textContent = `${entry.weekly_xp} XP`;

    row.append(rank, avatar, name, xp);
    el.appendChild(row);
  }
  if (data.your_rank && data.your_rank > data.leaderboard.length) {
    const you = document.createElement("div");
    you.className = "leaderboard-row is-you";
    you.innerHTML = `<span class="leaderboard-rank">#${data.your_rank}</span><span class="leaderboard-avatar" style="background:${avatarColor("You")}">${initials("You")}</span><span class="leaderboard-name">You</span><span class="leaderboard-xp">${data.your_weekly_xp} XP</span>`;
    el.appendChild(you);
  }
}

function showToast(text) {
  const toast = $("#toast");
  toast.textContent = text;
  toast.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toast.classList.add("hidden"), 2600);
}

function setupShop(data) {
  const freezeBtn = $("#buy-streak-freeze");
  const heartBtn = $("#buy-heart-refill");
  freezeBtn.disabled = data.gems < 200;
  heartBtn.disabled = data.gems < 100 || data.hearts >= 5;

  freezeBtn.onclick = async () => {
    try {
      await api(`/api/shop/${state.userId}/streak-freeze`, { method: "POST" });
      showToast("🧊 Streak freeze purchased!");
      await loadDashboard();
    } catch (err) {
      showToast(err.message);
    }
  };
  heartBtn.onclick = async () => {
    try {
      await api(`/api/shop/${state.userId}/heart-refill`, { method: "POST" });
      showToast("❤️ Hearts refilled!");
      await loadDashboard();
    } catch (err) {
      showToast(err.message);
    }
  };
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

const PRAISE = ["Correct! 🎉", "Nice one! ✨", "Great job! 👏", "You've got it! 🙌", "Exactly right! 💪"];
const MISS_LEADIN = ["Not quite.", "Close, but not quite.", "Almost!"];

function showFeedback(container, correct, extra, customMessage) {
  const banner = document.createElement("div");
  banner.className = `feedback-banner ${correct ? "correct" : "incorrect"}`;
  if (customMessage) {
    banner.textContent = customMessage;
  } else if (correct) {
    banner.textContent = PRAISE[Math.floor(Math.random() * PRAISE.length)];
  } else {
    const leadIn = MISS_LEADIN[Math.floor(Math.random() * MISS_LEADIN.length)];
    banner.textContent = `${leadIn} ${extra || ""}`;
  }
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
    const answer = input.value.trim();
    const correct = answer.length > 0;
    submit.disabled = true;
    input.disabled = true;
    await recordAnswer(ex, correct);
    if (!correct) {
      showFeedback(container, correct, "Try writing a short answer next time.");
      return;
    }
    submit.textContent = "…";
    try {
      const { reply } = await api("/api/content/tutor-reply", {
        method: "POST",
        body: JSON.stringify({
          target_lang: state.user.target_lang,
          native_lang: state.user.native_lang,
          level: state.user.level,
          interests: state.user.interests,
          prompt: ex.prompt,
          user_answer: answer,
        }),
      });
      showFeedback(container, true, "", reply);
    } catch {
      showFeedback(container, true);
    }
  });
}

async function finishLesson() {
  const { exercises, correctCount, unitId } = state.lesson;
  const score = exercises.length ? correctCount / exercises.length : 0;
  const result = await api(`/api/lessons/${state.userId}/complete`, {
    method: "POST",
    body: JSON.stringify({ unit_id: unitId, score }),
  });
  $("#complete-xp-pill").textContent = result.xp_gained;
  $("#complete-gems-pill").textContent = result.gems_gained;
  $("#complete-streak").textContent = result.streak_freeze_used
    ? `🧊 Streak freeze used — your ${result.streak_days}-day streak is safe!`
    : `🔥 ${result.streak_days} day streak`;
  $("#complete-level").textContent = result.leveled_up
    ? `🎊 Level up! You're now at ${result.leveled_up}.`
    : result.mastered
      ? "Unit mastered!"
      : "Keep practicing this unit to master it.";
  $("#complete-mascot").classList.toggle("mood-fire", !!result.leveled_up);
  $("#complete-mascot-badge").textContent = result.leveled_up ? "🎉" : "⭐";
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
