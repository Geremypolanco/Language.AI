// Lingua frontend — vanilla JS, no build step (mirrors the rest of this repo's
// static-HTML deployment style, but as a fully independent app).

// Every innerHTML template literal that interpolates AI-generated or
// server-sourced free text (course content, recommendations, practice
// scenarios, ...) must escape it first — a model glitch or a successful
// prompt-injection attempt outputting raw HTML must never execute in the
// page. textContent assignments elsewhere are already safe by construction;
// this is only needed where a string is interpolated into an HTML string.
function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

// ---------- AI content feedback (thumbs up/down + report) ----------
// Attachable to any piece of AI-generated content the learner is reading —
// the direct, user-facing half of guarding against hallucinations: the
// model output can't be perfectly self-validated, so give the reader a
// one-click way to flag it when something reads wrong.

function renderFeedbackWidget(contentType, contentId) {
  const el = document.createElement("div");
  el.className = "ai-feedback-widget";
  el.innerHTML = `
    <span class="ai-feedback-label">¿Te sirvió este contenido?</span>
    <button type="button" class="ai-feedback-btn" data-rating="up" title="Útil">${iconSvg("thumb-up")}</button>
    <button type="button" class="ai-feedback-btn" data-rating="down" title="No es útil">${iconSvg("thumb-down")}</button>
    <button type="button" class="ai-feedback-btn ai-feedback-report" data-rating="report" title="Reportar un error">${iconSvg("flag")} Reportar</button>
    <span class="ai-feedback-thanks hidden">¡Gracias por tu opinión!</span>
  `;
  el.querySelectorAll(".ai-feedback-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const rating = btn.dataset.rating;
      let note = "";
      if (rating === "report") {
        note = prompt("¿Qué salió mal? (opcional)") || "";
      }
      el.querySelectorAll(".ai-feedback-btn").forEach((b) => (b.disabled = true));
      try {
        await api("/api/feedback", {
          method: "POST",
          body: JSON.stringify({ content_type: contentType, content_id: contentId, rating, note }),
        });
        el.querySelector(".ai-feedback-thanks").classList.remove("hidden");
      } catch (err) {
        el.querySelectorAll(".ai-feedback-btn").forEach((b) => (b.disabled = false));
        showToast(err.message);
      }
    });
  });
  return el;
}

// Custom SVG icons (defined in index.html's sprite) instead of emoji — emoji
// render inconsistently across OS/browser and read as an unfinished shortcut
// rather than a designed product.
function iconSvg(name, extraClass = "") {
  const cls = `icon ${extraClass}`.trim();
  return `<svg class="${cls}"><use href="#icon-${name}"/></svg>`;
}

// Any language the tutor chat model knows works for exercises/conversation —
// this list is what's offered in the picker, not a hard backend restriction.
// Keep in sync with backend/hf_client.py's _MMS_LANG_CODES for TTS voice
// coverage (a language missing from that map still teaches fully via text/
// chat, it just falls back to an English voice for audio).
//
// Labels are "language's own name for itself / Spanish name" — a picker
// showing every language only in Spanish is unreadable to anyone who
// doesn't already know Spanish, including someone choosing Spanish itself
// isn't a problem, but choosing e.g. "Alemán" when you only read German is.
const LANGS = [
  ["en", "English / Inglés"], ["es", "Español / Spanish"], ["fr", "Français / Francés"], ["de", "Deutsch / Alemán"],
  ["it", "Italiano"], ["pt", "Português / Portugués"], ["ja", "日本語 / Japonés"], ["ko", "한국어 / Coreano"],
  ["zh", "中文 / Chino (mandarín)"], ["ru", "Русский / Ruso"], ["ar", "العربية / Árabe"],
  ["nl", "Nederlands / Neerlandés"], ["sv", "Svenska / Sueco"], ["pl", "Polski / Polaco"], ["tr", "Türkçe / Turco"], ["hi", "हिन्दी / Hindi"],
  ["id", "Bahasa Indonesia / Indonesio"], ["vi", "Tiếng Việt / Vietnamita"], ["th", "ไทย / Tailandés"], ["uk", "Українська / Ucraniano"],
  ["el", "Ελληνικά / Griego"], ["he", "עברית / Hebreo"], ["cs", "Čeština / Checo"], ["ro", "Română / Rumano"],
  ["hu", "Magyar / Húngaro"], ["fi", "Suomi / Finlandés"], ["da", "Dansk / Danés"], ["no", "Norsk / Noruego"],
  ["bg", "Български / Búlgaro"], ["sk", "Slovenčina / Eslovaco"], ["hr", "Hrvatski / Croata"], ["sr", "Српски / Serbio"],
  ["lt", "Lietuvių / Lituano"], ["lv", "Latviešu / Letón"], ["et", "Eesti / Estonio"], ["sl", "Slovenščina / Esloveno"],
  ["fa", "فارسی / Persa (farsi)"], ["ur", "اردو / Urdu"], ["bn", "বাংলা / Bengalí"], ["ta", "தமிழ் / Tamil"],
  ["te", "తెలుగు / Telugu"], ["mr", "मराठी / Maratí"], ["gu", "ગુજરાતી / Guyaratí"], ["pa", "ਪੰਜਾਬੀ / Panyabí"],
  ["ml", "മലയാളം / Malabar"], ["kn", "ಕನ್ನಡ / Canarés"], ["ne", "नेपाली / Nepalí"], ["si", "සිංහල / Cingalés"],
  ["my", "မြန်မာ / Birmano"], ["km", "ខ្មែរ / Jemer"], ["lo", "ລາວ / Lao"], ["ms", "Bahasa Melayu / Malayo"],
  ["tl", "Tagalog / Filipino"], ["sw", "Kiswahili / Suajili"], ["am", "አማርኛ / Amárico"], ["so", "Soomaali / Somalí"],
  ["ha", "Hausa"], ["yo", "Yorùbá / Yoruba"], ["ig", "Igbo"], ["zu", "isiZulu / Zulú"], ["xh", "isiXhosa / Xhosa"],
  ["af", "Afrikaans"], ["is", "Íslenska / Islandés"], ["ga", "Gaeilge / Irlandés"], ["cy", "Cymraeg / Galés"],
  ["mt", "Malti / Maltés"], ["eu", "Euskera"], ["ca", "Català / Catalán"], ["gl", "Galego / Gallego"],
  ["az", "Azərbaycan / Azerbaiyano"], ["kk", "Қазақ / Kazajo"], ["uz", "O'zbek / Uzbeko"], ["mn", "Монгол / Mongol"],
  ["ka", "ქართული / Georgiano"], ["hy", "Հայերեն / Armenio"], ["sq", "Shqip / Albanés"], ["mk", "Македонски / Macedonio"],
];

// Curriculum topic names (backend/curriculum.py _TOPICS_BY_LEVEL) are stable
// English keys used internally and as LLM context — this maps them to the
// Spanish label actually shown in the UI (skill path, recent lessons).
const TOPIC_ES = {
  "Greetings & introductions": "Saludos y presentaciones",
  "Numbers & counting": "Números y conteo",
  "Family": "Familia",
  "Food & drink": "Comida y bebida",
  "Colors & shapes": "Colores y formas",
  "Everyday objects": "Objetos cotidianos",
  "Days & time": "Días y horas",
  "Daily routines": "Rutinas diarias",
  "Shopping": "De compras",
  "Directions & places in town": "Direcciones y lugares en la ciudad",
  "Weather": "El clima",
  "Hobbies": "Pasatiempos",
  "Past tense: simple stories": "Pasado: historias sencillas",
  "Making plans": "Hacer planes",
  "Travel & transportation": "Viajes y transporte",
  "Health & the body": "Salud y el cuerpo",
  "Work & school": "Trabajo y escuela",
  "Opinions & preferences": "Opiniones y preferencias",
  "Describing people": "Describir personas",
  "Telling a past experience": "Contar una experiencia pasada",
  "Free conversation: small talk": "Conversación libre: charla informal",
  "News & current events": "Noticias y actualidad",
  "Emotions & relationships": "Emociones y relaciones",
  "Giving advice": "Dar consejos",
  "Hypotheticals": "Hipótesis",
  "Debating opinions": "Debatir opiniones",
  "Free conversation: everyday problems": "Conversación libre: problemas cotidianos",
  "Idioms & colloquialisms": "Modismos y coloquialismos",
  "Nuanced arguments": "Argumentos matizados",
  "Professional communication": "Comunicación profesional",
  "Humor & wordplay": "Humor y juegos de palabras",
  "Free conversation: abstract topics": "Conversación libre: temas abstractos",
  "Regional accents & slang": "Acentos regionales y jerga",
  "Literary & rhetorical language": "Lenguaje literario y retórico",
  "Rapid native-speed conversation": "Conversación a velocidad nativa",
  "Free conversation: any topic, native pace": "Conversación libre: cualquier tema, ritmo nativo",
  "Open conversation practice": "Práctica de conversación abierta",
};
function topicEs(topic) {
  return TOPIC_ES[topic] || topic;
}

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  userId: null,
  user: null,
  ws: null,
  mediaRecorder: null,
  audioChunks: [],
  lesson: null, // { exercises, index, correctCount, unitId, startedAt }
  lessonTimerHandle: null,
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

// ---------- i18n: app shell adapts to the learner's native language ----------
// A dashboard shown in a language the learner doesn't understand yet is
// unusable, so the UI chrome (nav, onboarding, placement test, tab intros,
// dashboard card titles) follows the account's native_lang once known, and
// a manual toggle on the very first onboarding screen covers the moment
// before an account exists at all.
//
// v1 scope: Spanish (the language every screen is already authored in — no
// entry needed here, it's just left as the DOM's original text) and English.
// Any other native_lang falls back to Spanish until it gets its own
// translation — a deliberate, communicated first pass, not full coverage of
// every screen (deeper lesson/reader micro-copy is still Spanish-only).
const I18N = {
  es: {
    coach_welcome: "¡Bienvenido a Lingua! Ve a Camino y elige tu primera lección, o toca Practicar si quieres entrenar una destreza específica primero. Si también quieres estudiar una carrera universitaria (en tu propio idioma, mientras aprendes el nuevo) toca Universidad arriba y elige qué te interesa.",
    coach_due_reviews: (n) => `Tienes ${n} palabra${n === 1 ? "" : "s"} para repasar. Sigue en Camino para reforzarlas antes de avanzar.`,
    coach_streak: (n, dia) => `¡Racha de ${n} ${dia}! ¿Lista o listo para tu próxima lección?`,
    coach_welcome_back: "¡Bienvenido de nuevo! ¿Seguimos aprendiendo?",
    placement_question_progress: (n, total) => `Pregunta ${n} de ${total}`,
    placement_preparing: "Preparando tu siguiente pregunta…",
    placement_default_prompt: "Elige la respuesta correcta:",
  },
  en: {
    ob_coach_intro: "Step 1 of 2: tell me about yourself so I can prep your first lessons. At the end I'll ask a few quick questions to place your level — or you can skip it if you're already advanced.",
    ob_label_name: "Your name",
    ob_label_native: "I already speak",
    ob_label_target: "I want to learn",
    ob_label_interests: "Interests (comma-separated, personalizes your lessons)",
    ob_label_goal: "How much time do you want to spend per day?",
    ob_label_goal_hint: "(just a personal guide, never a limit)",
    ob_submit: "Find my level",
    ob_skip: "I already have an advanced level — skip the placement test",
    placement_title: "Let's find your level",
    placement_subtitle: "Answer as best you can — the questions adjust to you as you go, like a real placement test.",
    placement_result_level_prefix: "You're at level",
    placement_result_note: "You'll start your path there — it keeps adjusting as you progress.",
    placement_result_academy_tip: 'Tip: you can also study a university-style career track — in your own language — from the <strong>University</strong> tab, whenever you want.',
    placement_continue_btn: "Start learning",
    nav_path: "Path",
    nav_practice: "Practice",
    nav_library: "Library",
    nav_academy: "University",
    nav_talk: "Talk live",
    nav_progress: "Progress",
    practice_title: "What do you want to master today?",
    practice_subtitle: "Pick a skill and practice as much as you want — no limits, no fixed order.",
    practice_level_label: "Practice level",
    library_title: "Library of 500+ books",
    library_subtitle: "AI-written stories in the language you're learning — each one is generated the first time you open it.",
    filter_all_levels: "All levels",
    academy_disclaimer: 'AI-built, self-paced accelerated study track — <strong>not an accredited program</strong> and does not grant credits, certificates, or official degrees. It’s for learning only; for a real degree you need to enroll in an accredited university.',
    academy_picker_title: "What do you want to study?",
    academy_picker_subtitle: "Pick a career track and a depth level — you set the pace.",
    academy_level_associate: "Technical (Associate-equivalent) — fastest",
    academy_level_bachelor: "Professional (Bachelor's-equivalent)",
    academy_level_master: "Advanced (Master's-equivalent)",
    academy_switch_btn: "Switch career",
    talk_connecting: "Connecting…",
    talk_mic_btn: "Hold to talk",
    talk_text_placeholder: "…or type instead",
    talk_send_btn: "Send",
    ai_disclaimer: "AI can give inaccurate answers. Double-check anything important.",
    dash_league_title: "Weekly league",
    dash_league_reset: "Resets on Monday",
    dash_level_progress_title: "Level progress",
    dash_daily_goal_title: "Daily goal",
    dash_change_btn: "Change",
    dash_recommended_title: "Recommended for you",
    dash_recommended_refresh: "New suggestions",
    dash_recommended_subtitle: "Books, songs, and more to reinforce what you're learning, outside the app.",
    dash_shop_title: "Gem shop",
    dash_shop_subtitle: "Earn gems by finishing lessons. Spend them here — never with real money.",
    dash_activity_title: "Last 14 days",
    dash_mastery_title: "Mastery by level",
    dash_recent_title: "Recent lessons",
    coach_welcome: "Welcome to Lingua! Go to Path and pick your first lesson, or tap Practice if you'd rather train a specific skill first. If you also want to study a university-style career track (in your own language, while you learn the new one) tap University above and pick what interests you.",
    coach_due_reviews: (n) => `You have ${n} word${n === 1 ? "" : "s"} to review. Keep going in Path to reinforce them before moving on.`,
    coach_streak: (n) => `${n}-day streak! Ready for your next lesson?`,
    coach_welcome_back: "Welcome back! Shall we keep learning?",
    placement_question_progress: (n, total) => `Question ${n} of ${total}`,
    placement_preparing: "Preparing your next question…",
    placement_default_prompt: "Choose the correct answer:",
  },
};

function currentUiLang() {
  return state.uiLang || "es";
}

// Returns undefined (not a placeholder string) when nothing is translated
// for this key/lang — callers must leave the DOM's original Spanish text
// alone in that case rather than overwrite it with a raw key name.
function t(key, ...args) {
  const lang = currentUiLang();
  let entry = I18N[lang] && I18N[lang][key];
  if (entry === undefined) entry = I18N.es && I18N.es[key];
  if (typeof entry === "function") return entry(...args);
  return entry;
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const value = t(el.getAttribute("data-i18n"));
    if (value !== undefined) el.textContent = value;
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    const value = t(el.getAttribute("data-i18n-html"));
    if (value !== undefined) el.innerHTML = value;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const value = t(el.getAttribute("data-i18n-placeholder"));
    if (value !== undefined) el.placeholder = value;
  });
  document.documentElement.lang = currentUiLang();
  $$(".ui-lang-btn").forEach((btn) => btn.classList.toggle("active", btn.dataset.uiLang === currentUiLang()));
}

function setUiLang(lang) {
  state.uiLang = lang;
  try { localStorage.setItem("lingua_ui_lang", lang); } catch {}
  applyI18n();
}

// Once we know the signed-in user's native_lang (a 2-letter code — see
// populateLangSelects), that's authoritative over any earlier guess.
function setUiLangFromNativeCode(code) {
  setUiLang(code === "en" ? "en" : "es");
}

function initUiLang() {
  let guess = "es";
  try {
    guess = localStorage.getItem("lingua_ui_lang") || "";
  } catch {
    guess = "";
  }
  if (!guess) {
    guess = navigator.language && navigator.language.toLowerCase().startsWith("en") ? "en" : "es";
  }
  state.uiLang = guess;
  applyI18n();
  $$(".ui-lang-btn").forEach((btn) => btn.addEventListener("click", () => setUiLang(btn.dataset.uiLang)));
}

// ---------- Onboarding ----------

function populateLangSelects() {
  const native = $("#ob-native");
  const target = $("#ob-target");
  for (const [code, name] of LANGS) {
    native.add(new Option(name, code));
    target.add(new Option(name, code));
  }
  native.value = "es";
  target.value = "en";
  // The moment someone tells us their native language, the rest of
  // onboarding (placement test, result) should already follow it — no need
  // to wait until the account is created and reloaded.
  native.addEventListener("change", () => setUiLangFromNativeCode(native.value));
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
      display_name: $("#ob-name").value.trim() || "Estudiante",
      native_lang: $("#ob-native").value,
      target_lang: $("#ob-target").value,
      level,
      interests: readInterests(),
      daily_goal_minutes: parseInt($("#ob-daily-goal").value, 10) || 15,
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
    alert("No se pudo iniciar la prueba de nivel: " + err.message);
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
  el.textContent = t("placement_preparing");
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
  $("#placement-progress").textContent = t("placement_question_progress", data.question_number, PLACEMENT_TOTAL);
  $("#placement-progress-bar").style.width = `${Math.round(((data.question_number - 1) / PLACEMENT_TOTAL) * 100)}%`;
  renderPlacementQuestion(data.exercise, data.level, el);
}

function renderPlacementQuestion(ex, level, container) {
  // Placement always requests multiple_choice questions (see placement.py),
  // so this only needs the instruction/prompt, an optional native-language
  // hint, and the answer options — it must NOT also show ex.target_text on
  // its own, since for most exercise shapes that field IS the correct
  // answer and would just give it away before the learner picks.
  container.innerHTML = "";

  const prompt = document.createElement("div");
  prompt.className = "exercise-prompt";
  prompt.textContent = ex.prompt || t("placement_default_prompt");
  container.appendChild(prompt);

  if (ex.native_text) {
    const hint = document.createElement("p");
    hint.className = "subtitle";
    hint.textContent = ex.native_text;
    container.appendChild(hint);
  }

  const submit = (answer, btn, allButtons) => {
    allButtons.forEach((b) => (b.disabled = true));
    const correct = normalize(answer) === normalize(ex.correct_answer);
    btn.classList.add(correct ? "correct" : "incorrect");
    placement.history.push({ level, correct });
    setTimeout(fetchNextPlacementQuestion, 400);
  };

  const opts = document.createElement("div");
  opts.className = "exercise-options";
  const choices = ex.options && ex.options.length ? ex.options : [ex.correct_answer];
  const buttons = choices.map((choice) => {
    const btn = document.createElement("button");
    btn.className = "option-btn";
    btn.textContent = choice;
    opts.appendChild(btn);
    return btn;
  });
  buttons.forEach((btn) => btn.addEventListener("click", () => submit(btn.textContent, btn, buttons)));
  container.appendChild(opts);
}

async function finishPlacementTest(recommendedLevel) {
  $("#placement-progress-bar").style.width = "100%";
  $("#placement-result-level").textContent = recommendedLevel;
  showOnboardingStep("#onboarding-step-result");
  $("#placement-continue").onclick = () => createProfileAndEnter(recommendedLevel).catch((err) => alert(err.message));
}

$("#ob-skip-fluent").addEventListener("click", () => {
  createProfileAndEnter("NATIVE").catch((err) => alert("No se pudo crear el perfil: " + err.message));
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
    err.textContent = "No se pudo iniciar sesión — inténtalo de nuevo.";
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
  setUiLangFromNativeCode(state.user.native_lang);
  showScreen("#screen-main");
  const [, progress] = await Promise.all([loadPath(), loadProgress()]);
  showCoachGreeting(progress);
}

function coachGreetingFor(progress) {
  if (progress.xp === 0 && progress.streak_days === 0) {
    return t("coach_welcome");
  }
  if (progress.due_reviews > 0) {
    return t("coach_due_reviews", progress.due_reviews, diaWord(progress.due_reviews));
  }
  if (progress.streak_days > 0) {
    return t("coach_streak", progress.streak_days, diaWord(progress.streak_days));
  }
  return t("coach_welcome_back");
}

function showCoachGreeting(progress) {
  if (sessionStorage.getItem("lingua_coach_shown")) return;
  sessionStorage.setItem("lingua_coach_shown", "1");
  const message = coachGreetingFor(progress);
  $("#coach-toast-message").textContent = message;
  $("#coach-toast").classList.remove("hidden");
  $("#coach-toast-listen").onclick = () => playAudio(message, "es");
}

$("#coach-toast-close").addEventListener("click", () => $("#coach-toast").classList.add("hidden"));

function refreshTopbar(progress) {
  $("#stat-xp").textContent = progress.xp;
  $("#stat-streak").textContent = progress.streak_days;
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
    ["flame", data.streak_days, "Racha", "fire"],
    ["gem", data.gems, "Gemas", "gem"],
    ["star", data.xp, "XP", "xp"],
    ["medal", data.level, "Nivel", "level"],
  ];
  const row = $("#dash-stat-row");
  row.innerHTML = "";
  for (const [icon, value, label, tone] of tiles) {
    const tile = document.createElement("div");
    tile.className = "stat-tile";
    const iconEl = document.createElement("div");
    iconEl.className = `stat-icon stat-icon-${tone}`;
    iconEl.innerHTML = iconSvg(icon);
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
    maxed.textContent = `Has alcanzado ${data.level} — perfeccionamiento a nivel nativo desbloqueado.`;
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
  caption.textContent = `${data.units_mastered_current_level} de ${required} unidades dominadas para desbloquear ${data.next_level}`;

  el.append(row, track, caption);
}

function renderDailyGoal(data) {
  const el = $("#dash-daily-goal");
  el.innerHTML = "";
  const goal = data.daily_goal_minutes || 15;
  const today = data.today_minutes || 0;

  const row = document.createElement("div");
  row.className = "daily-goal-row";
  const label = document.createElement("span");
  label.textContent = `${today} de ${goal} min hoy`;
  row.appendChild(label);
  if (today >= goal) {
    const done = document.createElement("span");
    done.className = "daily-goal-done";
    done.innerHTML = `<svg class="icon"><use href="#icon-check"/></svg> ¡Cumplida!`;
    row.appendChild(done);
  }

  const track = document.createElement("div");
  track.className = "meter-track";
  const fill = document.createElement("div");
  fill.className = "meter-fill";
  fill.style.width = `${Math.min(100, Math.round((today / goal) * 100))}%`;
  track.appendChild(fill);

  el.append(row, track);

  const select = $("#daily-goal-select");
  select.value = String(goal);
}

function setupDailyGoalEditor() {
  const btn = $("#daily-goal-edit-btn");
  const select = $("#daily-goal-select");
  if (btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.addEventListener("click", () => {
    select.classList.toggle("hidden");
  });
  select.addEventListener("change", async () => {
    const daily_goal_minutes = parseInt(select.value, 10);
    await api(`/api/users/${state.userId}`, {
      method: "PATCH",
      body: JSON.stringify({ daily_goal_minutes }),
    });
    select.classList.add("hidden");
    loadDashboard();
  });
}

function renderDueCard(data) {
  const card = $("#dash-due-card");
  if (data.due_reviews > 0) {
    card.classList.remove("hidden");
    $("#dash-due-headline").textContent = `${data.due_reviews} palabra${data.due_reviews === 1 ? "" : "s"} para repasar`;
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
    new Date(d.date + "T00:00:00").toLocaleDateString("es", { weekday: "short", day: "numeric" })
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
            label: (item) => `${item.raw} lección${item.raw === 1 ? "" : "es"}`,
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
              return `${e.mastered}/${e.total} unidades dominadas`;
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
    empty.textContent = "Completa una lección para verla aquí.";
    el.appendChild(empty);
    return;
  }
  for (const lesson of data.recent_lessons) {
    const row = document.createElement("div");
    row.className = "recent-row";

    const left = document.createElement("div");
    const topic = document.createElement("div");
    topic.className = "recent-topic";
    topic.textContent = topicEs(lesson.topic);
    const date = document.createElement("div");
    date.className = "recent-date";
    date.textContent = new Date(lesson.completed_at).toLocaleDateString("es");
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
    renderLevelMeter, renderDailyGoal, setupDailyGoalEditor, renderDueCard,
    setupRecommendations, setupShop, renderActivity, renderMasteryChart, renderRecentLessons,
  ];
  for (const render of sections) {
    try {
      render(data);
    } catch (err) {
      console.error(`Dashboard section "${render.name}" failed to render`, err);
    }
  }
}

function diaWord(n) {
  return n === 1 ? "día" : "días";
}

function renderMascot(data) {
  const card = $("#mascot-card");
  const badge = $("#mascot-badge");
  const message = $("#mascot-message");
  card.classList.remove("mood-goal", "mood-cool", "mood-fire", "mood-curious", "mood-happy");
  if (data.daily_goal_minutes > 0 && data.today_minutes >= data.daily_goal_minutes) {
    card.classList.add("mood-goal");
    badge.innerHTML = iconSvg("check");
    message.textContent = `¡Objetivo de hoy cumplido! ${data.today_minutes} de ${data.daily_goal_minutes} min — sigue si quieres, sin límite.`;
  } else if (data.streak_freezes > 0) {
    card.classList.add("mood-cool");
    badge.innerHTML = iconSvg("snowflake");
    const freezeWord = data.streak_freezes === 1 ? "congelación de racha guardada" : "congelaciones de racha guardadas";
    message.textContent = `${data.streak_freezes} ${freezeWord} — tu racha está protegida si faltas un día.`;
  } else if (data.streak_days >= 7) {
    card.classList.add("mood-fire");
    badge.innerHTML = iconSvg("flame");
    message.textContent = `¡Racha de ${data.streak_days} días! Estás que ardes — sigue así.`;
  } else if (data.due_reviews > 0) {
    card.classList.add("mood-curious");
    badge.innerHTML = iconSvg("book");
    message.textContent = `${data.due_reviews} palabra${data.due_reviews === 1 ? "" : "s"} lista${data.due_reviews === 1 ? "" : "s"} para repasar en tu próxima lección.`;
  } else if (data.streak_days > 0) {
    card.classList.add("mood-happy");
    badge.innerHTML = iconSvg("sparkle");
    message.textContent = `Racha de ${data.streak_days} ${diaWord(data.streak_days)} — ¡buen trabajo, no la rompas!`;
  } else {
    badge.innerHTML = iconSvg("wave");
    message.textContent = "¿Listo para tu primera lección de hoy?";
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
    empty.textContent = "Completa una lección esta semana para unirte a la liga.";
    el.appendChild(empty);
    return;
  }
  const medalTone = { 1: "gold", 2: "silver", 3: "bronze" };
  for (const entry of data.leaderboard) {
    const row = document.createElement("div");
    row.className = "leaderboard-row" + (entry.is_you ? " is-you" : "");

    const rank = document.createElement("span");
    const tone = medalTone[entry.rank];
    rank.className = "leaderboard-rank" + (tone ? ` medal-${tone}` : "");
    if (tone) {
      rank.innerHTML = iconSvg("medal");
    } else {
      rank.textContent = `#${entry.rank}`;
    }

    const avatar = document.createElement("span");
    avatar.className = "leaderboard-avatar";
    avatar.style.background = avatarColor(entry.display_name);
    avatar.textContent = initials(entry.display_name);

    const name = document.createElement("span");
    name.className = "leaderboard-name";
    name.textContent = entry.is_you ? `${entry.display_name} (tú)` : entry.display_name;

    const xp = document.createElement("span");
    xp.className = "leaderboard-xp";
    xp.textContent = `${entry.weekly_xp} XP`;

    row.append(rank, avatar, name, xp);
    el.appendChild(row);
  }
  if (data.your_rank && data.your_rank > data.leaderboard.length) {
    const you = document.createElement("div");
    you.className = "leaderboard-row is-you";
    you.innerHTML = `<span class="leaderboard-rank">#${data.your_rank}</span><span class="leaderboard-avatar" style="background:${avatarColor("Tú")}">${initials("Tú")}</span><span class="leaderboard-name">Tú</span><span class="leaderboard-xp">${data.your_weekly_xp} XP</span>`;
    el.appendChild(you);
  }
}

function showToast(text, icon) {
  const toast = $("#toast");
  toast.innerHTML = icon ? `${iconSvg(icon)} ${text}` : text;
  toast.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toast.classList.add("hidden"), 2600);
}

function setupShop(data) {
  const freezeBtn = $("#buy-streak-freeze");
  freezeBtn.disabled = data.gems < 200;

  freezeBtn.onclick = async () => {
    try {
      await api(`/api/shop/${state.userId}/streak-freeze`, { method: "POST" });
      showToast("¡Congelación de racha comprada!", "snowflake");
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
      heading.textContent = `Nivel ${unit.level}`;
      container.appendChild(heading);
      lastLevel = unit.level;
    }
    const btn = document.createElement("button");
    btn.className = `unit-node ${unit.state}`;
    btn.textContent = topicEs(unit.topic);
    btn.addEventListener("click", () => startLesson(unit.id));
    container.appendChild(btn);
  }
}

// ---------- Practice mode (modality-focused, no fixed order) ----------

const PRACTICE_MODALITIES = [
  { type: "translate_to_target", label: "Traducción", icon: "translate", desc: "Traduce frases a tu idioma meta" },
  { type: "translate_to_native", label: "Traducción inversa", icon: "translate", desc: "Traduce frases a tu idioma nativo" },
  { type: "listen_type", label: "Escucha y escribe", icon: "volume", desc: "Escucha el audio y escribe lo que oyes" },
  { type: "image_match", label: "Imágenes", icon: "image", desc: "Empareja palabras con imágenes" },
  { type: "multiple_choice", label: "Opción múltiple", icon: "check", desc: "Elige la respuesta correcta" },
  { type: "fill_blank", label: "Completa la frase", icon: "pencil", desc: "Rellena los espacios en blanco" },
  { type: "speak_repeat", label: "Habla", icon: "mic", desc: "Repite frases en voz alta" },
  { type: "free_conversation_prompt", label: "Conversación libre", icon: "chat", desc: "Practica una conversación abierta" },
];

function setupPractice() {
  const levelSelect = $("#practice-level-select");
  if (state.user) levelSelect.value = state.user.level;

  const grid = $("#practice-grid");
  if (grid.dataset.built) return;
  grid.dataset.built = "1";
  for (const modality of PRACTICE_MODALITIES) {
    const card = document.createElement("button");
    card.className = "practice-card";
    card.innerHTML = `
      <span class="practice-card-icon"><svg class="icon"><use href="#icon-${modality.icon}"/></svg></span>
      <span class="practice-card-label">${modality.label}</span>
      <p class="practice-card-desc">${modality.desc}</p>
    `;
    card.addEventListener("click", () => startPractice(modality.type));
    grid.appendChild(card);
  }
}

async function startPractice(exerciseType) {
  const level = $("#practice-level-select").value;
  showScreen("#screen-lesson");
  $("#exercise-container").innerHTML = "<p>Preparando tu práctica…</p>";
  try {
    const body = await api(`/api/lessons/${state.userId}/practice`, {
      method: "POST",
      body: JSON.stringify({ exercise_type: exerciseType, level }),
    });
    startLesson(body.unit_id, body.exercises);
  } catch (err) {
    $("#exercise-container").innerHTML = `<p>No se pudo preparar la práctica: ${err.message}</p>`;
  }
}

// ---------- Library (500+ AI-generated books, on demand) ----------

const _libraryState = { offset: 0, genresLoaded: false };

async function setupLibrary() {
  if (!_libraryState.genresLoaded) {
    _libraryState.genresLoaded = true;
    try {
      const genres = await api("/api/library/genres");
      const select = $("#library-genre-filter");
      for (const g of genres) select.add(new Option(g.label, g.id));
    } catch (err) {
      console.error("Failed to load library genres", err);
    }
    $("#library-level-filter").addEventListener("change", () => loadLibraryPage(true));
    $("#library-genre-filter").addEventListener("change", () => loadLibraryPage(true));
    $("#library-load-more").addEventListener("click", () => loadLibraryPage(false));
  }
  if ($("#library-grid").children.length === 0) {
    loadLibraryPage(true);
  }
}

async function loadLibraryPage(reset) {
  if (reset) {
    _libraryState.offset = 0;
    $("#library-grid").innerHTML = "";
  }
  const level = $("#library-level-filter").value;
  const genre = $("#library-genre-filter").value;
  const params = new URLSearchParams({ offset: String(_libraryState.offset), limit: "30" });
  if (level) params.set("level", level);
  if (genre) params.set("genre", genre);
  const books = await api(`/api/library/${state.userId}/catalog?${params}`);
  const grid = $("#library-grid");
  for (const book of books) {
    const card = document.createElement("button");
    card.className = "book-card";
    card.innerHTML = `
      <div class="book-card-chips">
        <span class="book-chip">${book.genre_label}</span>
        <span class="book-chip level">${book.level}</span>
      </div>
      <p class="book-card-title">${book.title}</p>
      <p class="book-card-blurb">${book.blurb}</p>
    `;
    card.addEventListener("click", () => openBook(book.id));
    grid.appendChild(card);
  }
  _libraryState.offset += books.length;
  $("#library-load-more").classList.toggle("hidden", books.length < 30);
}

async function openBook(bookId) {
  showScreen("#screen-reader");
  $("#reader-title").textContent = "";
  $("#reader-genre-chip").textContent = "";
  $("#reader-level-chip").textContent = "";
  const body = $("#reader-body");
  body.textContent = "Generando tu libro…";
  body.classList.add("loading");
  $("#reader-feedback").innerHTML = "";
  try {
    const book = await api(`/api/library/${state.userId}/books/${bookId}`);
    $("#reader-title").textContent = book.title;
    $("#reader-genre-chip").textContent = book.genre_label;
    $("#reader-level-chip").textContent = book.level;
    body.textContent = book.content;
    body.classList.remove("loading");
    const feedbackEl = $("#reader-feedback");
    feedbackEl.innerHTML = "";
    feedbackEl.appendChild(renderFeedbackWidget("book", bookId));
  } catch (err) {
    body.textContent = `No se pudo generar el libro: ${err.message}`;
    body.classList.remove("loading");
  }
}

$("#reader-exit").addEventListener("click", () => showScreen("#screen-main"));

// ---------- Recommendations (books, songs, and other media) ----------

async function fetchRecommendations() {
  const list = $("#recommendations-list");
  list.innerHTML = `<p class="recommendations-empty">Buscando sugerencias…</p>`;
  try {
    const items = await api("/api/content/recommendations", {
      method: "POST",
      body: JSON.stringify({
        target_lang: state.user.target_lang,
        level: state.user.level,
        interests: state.user.interests || [],
      }),
    });
    list.innerHTML = "";
    if (!items.length) {
      list.innerHTML = `<p class="recommendations-empty">No hay sugerencias por ahora.</p>`;
      return;
    }
    const kindIcons = { book: "book", song: "volume", podcast: "mic", show: "sparkle" };
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "recommendation-item";
      row.innerHTML = `
        <span class="recommendation-icon">${iconSvg(kindIcons[item.kind] || "sparkle")}</span>
        <div>
          <p class="recommendation-title">${escapeHtml(item.title)}</p>
          <p class="recommendation-creator">${escapeHtml(item.creator)}</p>
          <p class="recommendation-reason">${escapeHtml(item.reason)}</p>
        </div>
      `;
      list.appendChild(row);
    }
  } catch (err) {
    list.innerHTML = `<p class="recommendations-empty">No se pudieron cargar sugerencias: ${err.message}</p>`;
  }
}

function setupRecommendations() {
  const btn = $("#recommendations-refresh-btn");
  if (!btn.dataset.wired) {
    btn.dataset.wired = "1";
    btn.addEventListener("click", fetchRecommendations);
  }
  if ($("#recommendations-list").children.length === 0) {
    fetchRecommendations();
  }
}

// ---------- University-prep academy (self-paced, explicitly non-accredited) ----------

const ACADEMY_LEVEL_LABELS = {
  ASSOCIATE: "Técnico (equivalente a Asociado)",
  BACHELOR: "Profesional (equivalente a Licenciatura)",
  MASTER: "Avanzado (equivalente a Maestría)",
};

// Each of the 31 fields has a named tutor; visual identity comes from a
// per-category color pair + the field's own icon, rather than 31 bespoke
// illustrations — a sustainable way to give every subject a distinct face.
const ACADEMY_CATEGORY_COLORS = {
  "Tecnología": ["#2dd4bf", "#0f766e"],
  "Negocios": ["#ffc800", "#b45309"],
  "Salud": ["#fb7185", "#be123c"],
  "Ciencias": ["#c084fc", "#7c3aed"],
  "Ingeniería": ["#94a3b8", "#475569"],
  "Humanidades": ["#d97706", "#92400e"],
  "Artes": ["#f472b6", "#a21caf"],
};

function tutorAvatarSvg(field) {
  const [light, dark] = ACADEMY_CATEGORY_COLORS[field.category] || ["#2dd4bf", "#0f766e"];
  return `
    <span class="tutor-avatar" style="background: linear-gradient(135deg, ${light}, ${dark})">
      <svg class="icon"><use href="#icon-${field.icon}"/></svg>
    </span>
  `;
}

const _academyState = { fieldsLoaded: false, currentCourseId: null };

async function setupAcademy() {
  if (!_academyState.fieldsLoaded) {
    _academyState.fieldsLoaded = true;
    await loadAcademyFields();
    $("#academy-switch-btn").addEventListener("click", showAcademyPicker);
    $("#course-exit").addEventListener("click", () => showScreen("#screen-main"));
    $("#course-complete-btn").addEventListener("click", completeCurrentCourse);
    $("#course-practice-btn").addEventListener("click", startPracticeScenario);
    $("#course-video-btn").addEventListener("click", generateCourseVideo);
  }
  const progress = await api(`/api/academy/${state.userId}/progress`);
  if (progress.enrollment) {
    showAcademyCurriculum(progress);
  } else {
    showAcademyPicker();
  }
}

async function loadAcademyFields() {
  const fields = await api("/api/academy/fields");
  const container = $("#academy-fields");
  container.innerHTML = "";
  const byCategory = {};
  for (const field of fields) {
    (byCategory[field.category] ||= []).push(field);
  }
  for (const [category, items] of Object.entries(byCategory)) {
    const heading = document.createElement("div");
    heading.className = "academy-category-heading";
    heading.textContent = category;
    container.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "academy-fields-grid";
    for (const field of items) {
      const card = document.createElement("button");
      card.className = "field-card";
      card.innerHTML = `
        ${tutorAvatarSvg(field)}
        <p class="field-card-title">${field.name}</p>
        <p class="field-card-tutor">Tu tutor: ${field.tutor_name}</p>
        <p class="field-card-desc">${field.description}</p>
      `;
      card.addEventListener("click", () => enrollInField(field.id));
      grid.appendChild(card);
    }
    container.appendChild(grid);
  }
}

async function enrollInField(fieldId) {
  const level = $("#academy-level-select").value;
  const progress = await api(`/api/academy/${state.userId}/enroll`, {
    method: "POST",
    body: JSON.stringify({ field_id: fieldId, level }),
  }).then(async () => api(`/api/academy/${state.userId}/progress`));
  showAcademyCurriculum(progress);
}

function showAcademyPicker() {
  $("#academy-picker").classList.remove("hidden");
  $("#academy-curriculum").classList.add("hidden");
}

async function showAcademyCurriculum(progress) {
  $("#academy-picker").classList.add("hidden");
  $("#academy-curriculum").classList.remove("hidden");

  $("#academy-current-field").textContent = progress.enrollment.field_name;
  $("#academy-current-level").textContent = ACADEMY_LEVEL_LABELS[progress.enrollment.level] || progress.enrollment.level;
  $("#academy-current-tutor").textContent = `Tu tutor: ${progress.enrollment.tutor_name}`;
  $("#academy-tutor-avatar").innerHTML = tutorAvatarSvg(progress.enrollment);
  _academyState.currentTutor = { name: progress.enrollment.tutor_name, icon: progress.enrollment.icon, category: progress.enrollment.category };

  const pct = progress.total_courses ? Math.round((progress.completed_course_ids.length / progress.total_courses) * 100) : 0;
  $("#academy-progress-fill").style.width = `${pct}%`;
  $("#academy-progress-caption").textContent = `${progress.completed_course_ids.length} de ${progress.total_courses} cursos completados`;

  const list = $("#academy-course-list");
  list.innerHTML = `<p class="recommendations-empty">Generando tu plan de estudios…</p>`;
  const curriculum = await api(`/api/academy/${state.userId}/curriculum`);
  list.innerHTML = "";
  const completedIds = new Set(progress.completed_course_ids);
  curriculum.courses.forEach((course, i) => {
    const done = completedIds.has(course.id);
    const row = document.createElement("button");
    row.className = `course-item ${done ? "completed" : ""}`;
    row.innerHTML = `
      <span class="course-item-check">${done ? iconSvg("check") : i + 1}</span>
      <div>
        <p class="course-item-title">${escapeHtml(course.title)}</p>
        <p class="course-item-desc">${escapeHtml(course.description)}</p>
      </div>
    `;
    row.addEventListener("click", () => openCourse(course.id, course.title));
    list.appendChild(row);
  });
}

function youtubeSearchUrl(query) {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
}

async function openCourse(courseId, title) {
  _academyState.currentCourseId = courseId;
  showScreen("#screen-course");
  $("#course-title").textContent = title;

  const fieldName = _academyState.currentTutor ? $("#academy-current-field").textContent : "";
  $("#course-youtube-link").href = youtubeSearchUrl(`${title} ${fieldName}`.trim());

  const modulesEl = $("#course-modules");
  modulesEl.innerHTML = `<p class="recommendations-empty">Generando tu curso…</p>`;
  $("#course-feedback").innerHTML = "";
  try {
    const course = await api(`/api/academy/${state.userId}/courses/${courseId}`);
    modulesEl.innerHTML = "";
    for (const mod of course.modules) {
      const section = document.createElement("div");
      section.innerHTML = `
        <h3 class="course-module-title">${escapeHtml(mod.title)}</h3>
        <p class="course-module-content">${escapeHtml(mod.content)}</p>
      `;
      modulesEl.appendChild(section);
    }
    const feedbackEl = $("#course-feedback");
    feedbackEl.innerHTML = "";
    feedbackEl.appendChild(renderFeedbackWidget("course", courseId));
  } catch (err) {
    modulesEl.innerHTML = `<p class="recommendations-empty">No se pudo generar el curso: ${err.message}</p>`;
  }

  $("#practice-scenario-box").classList.add("hidden");
  $("#practice-scenario-box").innerHTML = "";
  $("#course-video-box").classList.add("hidden");
  $("#course-video-box").innerHTML = "";
}

async function completeCurrentCourse() {
  if (!_academyState.currentCourseId) return;
  const progress = await api(`/api/academy/${state.userId}/courses/${_academyState.currentCourseId}/complete`, {
    method: "POST",
  });
  showScreen("#screen-main");
  showAcademyCurriculum(progress);
}

async function startPracticeScenario() {
  const box = $("#practice-scenario-box");
  box.classList.remove("hidden");
  box.innerHTML = `<p class="recommendations-empty">Generando un caso práctico…</p>`;
  try {
    const { scenario } = await api(`/api/academy/${state.userId}/courses/${_academyState.currentCourseId}/scenario`);
    box.innerHTML = `
      <p class="practice-scenario-label">Caso práctico</p>
      <p class="practice-scenario-text">${escapeHtml(scenario)}</p>
      <textarea id="practice-response-input" placeholder="Escribe qué harías…" rows="4"></textarea>
      <button id="practice-response-submit" class="btn btn-primary">Enviar respuesta</button>
      <div id="practice-feedback" class="practice-feedback hidden"></div>
    `;
    box.dataset.scenario = scenario;
    $("#practice-response-submit").addEventListener("click", () => submitPracticeResponse(scenario));
  } catch (err) {
    box.innerHTML = `<p class="recommendations-empty">No se pudo generar el caso: ${err.message}</p>`;
  }
}

async function submitPracticeResponse(scenario) {
  const response = $("#practice-response-input").value.trim();
  if (!response) return;
  const feedbackEl = $("#practice-feedback");
  feedbackEl.classList.remove("hidden");
  feedbackEl.textContent = "Analizando tu respuesta…";
  try {
    const { feedback } = await api(`/api/academy/${state.userId}/courses/${_academyState.currentCourseId}/scenario/feedback`, {
      method: "POST",
      body: JSON.stringify({ scenario, response }),
    });
    feedbackEl.textContent = feedback;
  } catch (err) {
    feedbackEl.textContent = `No se pudo generar retroalimentación: ${err.message}`;
  }
}

async function generateCourseVideo() {
  const box = $("#course-video-box");
  box.classList.remove("hidden");
  box.innerHTML = `<p class="recommendations-empty">Generando un video corto… puede tardar uno o dos minutos.</p>`;
  const title = $("#course-title").textContent;
  const fieldName = $("#academy-current-field").textContent;
  const prompt = `A short, clear educational video explaining ${title}${fieldName ? `, part of ${fieldName}` : ""}.`;
  try {
    const res = await fetch("/api/content/video", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed: ${res.status}`);
    }
    const blob = await res.blob();
    const video = document.createElement("video");
    video.controls = true;
    video.className = "course-video-player";
    video.src = URL.createObjectURL(blob);
    box.innerHTML = `<p class="practice-scenario-label">Video generado por IA</p>`;
    box.appendChild(video);
  } catch (err) {
    box.innerHTML = `<p class="recommendations-empty">No se pudo generar el video: ${err.message}</p>`;
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
      if (btn.dataset.tab === "practice") setupPractice();
      if (btn.dataset.tab === "library") setupLibrary();
      if (btn.dataset.tab === "academy") setupAcademy();
      if (btn.dataset.tab === "talk") ensureConversationSocket();
      if (btn.dataset.tab === "progress") loadDashboard();
    });
  });
}

// ---------- Lesson flow ----------

function startLessonTimer() {
  stopLessonTimer();
  const valueEl = $("#lesson-timer-value");
  const tick = () => {
    const elapsed = Math.floor((Date.now() - state.lesson.startedAt) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    valueEl.textContent = `${mins}:${String(secs).padStart(2, "0")}`;
  };
  tick();
  state.lessonTimerHandle = setInterval(tick, 1000);
}

function stopLessonTimer() {
  if (state.lessonTimerHandle) {
    clearInterval(state.lessonTimerHandle);
    state.lessonTimerHandle = null;
  }
}

function lessonElapsedSeconds() {
  if (!state.lesson || !state.lesson.startedAt) return 0;
  return Math.floor((Date.now() - state.lesson.startedAt) / 1000);
}

async function startLesson(unitId, preloadedExercises) {
  showScreen("#screen-lesson");
  $("#exercise-container").innerHTML = "<p>Preparando tu lección personalizada…</p>";
  try {
    const exercises = preloadedExercises || (await api(`/api/lessons/${state.userId}/unit/${unitId}`));
    state.lesson = { exercises, index: 0, correctCount: 0, unitId, startedAt: Date.now() };
    startLessonTimer();
    renderCurrentExercise();
  } catch (err) {
    $("#exercise-container").innerHTML = `<p>No se pudo cargar la lección: ${err.message}</p>`;
  }
}

$("#lesson-exit").addEventListener("click", async () => {
  stopLessonTimer();
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
    await api(`/api/lessons/${state.userId}/answer`, {
      method: "POST",
      body: JSON.stringify({ vocab_key: exercise.vocab_key, correct, attempts_before_correct: 0 }),
    });
  } catch {
    // non-fatal for the demo
  }
}

const PRAISE = ["¡Correcto!", "¡Muy bien!", "¡Gran trabajo!", "¡Lo lograste!", "¡Exactamente!"];
const MISS_LEADIN = ["No es correcto.", "Cerca, pero no es correcto.", "¡Casi!"];

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
  next.textContent = "Continuar";
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
  promptEl.textContent = ex.prompt || "Traduce / responde:";
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
      showFeedback(container, correct, `Respuesta: ${ex.correct_answer}`);
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
      showFeedback(container, correct, `Respuesta: ${ex.correct_answer}`);
    });
    opts.appendChild(btn);
  }
  container.appendChild(opts);
}

function renderListenType(ex, container, targetLang) {
  const btn = document.createElement("button");
  btn.className = "audio-btn";
  btn.innerHTML = iconSvg("volume");
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
  input.placeholder = "Escribe tu respuesta…";
  const submit = document.createElement("button");
  submit.className = "btn btn-primary";
  submit.textContent = "Comprobar";
  row.appendChild(input);
  row.appendChild(submit);
  container.appendChild(row);

  const submitAnswer = async () => {
    const correct = normalize(input.value) === normalize(ex.correct_answer);
    submit.disabled = true;
    input.disabled = true;
    await recordAnswer(ex, correct);
    showFeedback(container, correct, `Respuesta: ${ex.correct_answer}`);
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
  playBtn.innerHTML = iconSvg("volume");
  playBtn.addEventListener("click", () => playAudio(ex.audio_text || ex.target_text, targetLang));
  container.appendChild(playBtn);
  playAudio(ex.audio_text || ex.target_text, targetLang);

  const recordBtn = document.createElement("button");
  recordBtn.className = "btn btn-primary";
  recordBtn.innerHTML = `${iconSvg("mic")} Mantén presionado y repite`;
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
    recordBtn.textContent = "Grabando…";
  };
  const stop = async () => {
    if (!recorder || recorder.state === "inactive") return;
    recorder.stop();
    recordBtn.innerHTML = `${iconSvg("mic")} Mantén presionado y repite`;
    await new Promise((resolve) => (recorder.onstop = resolve));
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    const res = await fetch("/api/content/stt", {
      method: "POST",
      headers: { "Content-Type": blob.type },
      body: blob,
    });
    const data = await res.json().catch(() => ({ text: "" }));
    heard.textContent = data.text ? `Escuchamos: "${data.text}"` : "No se pudo transcribir — verifica tú mismo abajo.";

    const selfCheck = document.createElement("div");
    selfCheck.className = "exercise-options";
    const yes = document.createElement("button");
    yes.className = "option-btn";
    yes.textContent = "Lo dije correctamente";
    const no = document.createElement("button");
    no.className = "option-btn";
    no.textContent = "Necesito más práctica";
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
  input.placeholder = "Escribe unas frases en respuesta…";
  const submit = document.createElement("button");
  submit.className = "btn btn-primary";
  submit.textContent = "Listo";
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
      showFeedback(container, correct, "Intenta escribir una respuesta corta la próxima vez.");
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
  const elapsedSeconds = lessonElapsedSeconds();
  stopLessonTimer();
  const result = await api(`/api/lessons/${state.userId}/complete`, {
    method: "POST",
    body: JSON.stringify({ unit_id: unitId, score, elapsed_seconds: elapsedSeconds }),
  });
  $("#complete-xp-pill").textContent = result.xp_gained;
  $("#complete-gems-pill").textContent = result.gems_gained;
  $("#complete-streak").innerHTML = result.streak_freeze_used
    ? `${iconSvg("snowflake")} Congelación de racha usada — ¡tu racha de ${result.streak_days} ${diaWord(result.streak_days)} está a salvo!`
    : `${iconSvg("flame")} Racha de ${result.streak_days} ${diaWord(result.streak_days)}`;
  $("#complete-level").innerHTML = result.leveled_up
    ? `${iconSvg("sparkle")} ¡Subiste de nivel! Ahora estás en ${result.leveled_up}.`
    : result.mastered
      ? "¡Unidad dominada!"
      : "Sigue practicando esta unidad para dominarla.";
  $("#complete-mascot").classList.toggle("mood-fire", !!result.leveled_up);
  $("#complete-mascot-badge").innerHTML = iconSvg(result.leveled_up ? "sparkle" : "star");
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
    $("#call-status").textContent = "Desconectado — cambia de pestaña para reconectar.";
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
    micBtn.textContent = "Escuchando…";
    avatar.classList.add("listening");
  };

  const stop = async () => {
    if (!state.mediaRecorder || state.mediaRecorder.state === "inactive") return;
    state.mediaRecorder.stop();
    micBtn.classList.remove("recording");
    micBtn.innerHTML = `${iconSvg("mic")} Mantén presionado para hablar`;
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

// ---------- Cookie consent (GDPR/CCPA) ----------
// Zero-cookie-load by default: nothing but the essential session cookie
// (already HttpOnly/Secure/SameSite=Lax, set server-side in routers/auth.py)
// is ever set until the learner explicitly chooses. This app doesn't load
// any analytics or marketing scripts today, so there's nothing for
// loadScriptIfConsented() to actually gate yet — it exists so the day a
// script is added, it plugs into this consent state instead of loading
// unconditionally. The preference itself is recorded in a plain (non-
// HttpOnly) cookie: HttpOnly cookies can only ever be set via a Set-Cookie
// response header and can never be read by client JS by design (that's the
// whole point of HttpOnly, protecting the session cookie from XSS) — a
// banner that needs to read the learner's own choice to decide whether to
// load a script structurally cannot use one. Secure + SameSite=Strict are
// both compatible with a non-HttpOnly cookie and are used here.

const CONSENT_COOKIE = "lingua_consent";

function getConsent() {
  const match = document.cookie.match(new RegExp(`(?:^|; )${CONSENT_COOKIE}=([^;]*)`));
  if (!match) return null;
  try {
    return JSON.parse(decodeURIComponent(match[1]));
  } catch {
    return null;
  }
}

function setConsent(prefs) {
  const value = encodeURIComponent(JSON.stringify(prefs));
  const secureFlag = location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${CONSENT_COOKIE}=${value}; path=/; max-age=31536000; SameSite=Strict${secureFlag}`;
}

// Ready for the first real analytics/marketing script: only runs `onload`
// (which should append the <script> tag) if the learner opted into
// `category` ("analytics" | "marketing"). Currently unused — nothing in
// this app needs it yet, but new scripts must be wired through this, not
// loaded unconditionally in index.html.
function loadScriptIfConsented(category, onload) {
  const consent = getConsent();
  if (consent && consent[category]) onload();
}

function setupCookieConsent() {
  const banner = $("#cookie-consent-banner");
  if (getConsent()) return; // already decided, zero re-prompt

  banner.classList.remove("hidden");

  $("#cookie-consent-accept").addEventListener("click", () => {
    setConsent({ essential: true, analytics: true, marketing: true });
    banner.classList.add("hidden");
  });
  $("#cookie-consent-reject").addEventListener("click", () => {
    setConsent({ essential: true, analytics: false, marketing: false });
    banner.classList.add("hidden");
  });
  $("#cookie-consent-save").addEventListener("click", () => {
    setConsent({
      essential: true,
      analytics: $("#cookie-consent-analytics").checked,
      marketing: $("#cookie-consent-marketing").checked,
    });
    banner.classList.add("hidden");
  });
}

// ---------- Boot ----------

async function boot() {
  initUiLang();
  populateLangSelects();
  $("#onboarding-form").addEventListener("submit", handleOnboardingSubmit);
  setupTabs();
  setupMic();
  setupDevLogin();
  setupCookieConsent();
  await checkSession();
}

boot();
