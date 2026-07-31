// Lingua frontend — vanilla JS, no build step (mirrors the rest of this repo's
// static-HTML deployment style, but as a fully independent app).

// Custom SVG icons (defined in index.html's sprite) instead of emoji — emoji
// render inconsistently across OS/browser and read as an unfinished shortcut
// rather than a designed product.
function iconSvg(name, extraClass = "") {
  const cls = `icon ${extraClass}`.trim();
  return `<svg class="${cls}"><use href="#icon-${name}"/></svg>`;
}

// ---------- Persona portraits ----------
// Every teacher (5 core + one per Academy field, see backend/personas.py) is
// a real, photorealistic HF-generated portrait, not a hand-drawn mascot. If
// HF_TOKEN isn't configured (demo mode) the portrait request 404s/503s, so
// every portrait falls back to a hand-illustrated face (see index.html's
// avatar-core-* symbols) rather than a broken image icon.

// Hand-illustrated portraits (see index.html's <symbol id="avatar-core-*">
// defs) — the fallback when the real FLUX-generated photo isn't available
// (no HF_TOKEN, or the request fails). Each core teacher has its own; every
// departmental faculty persona (id "faculty:<field_id>") is deterministically
// assigned one of the same five so it always gets a real illustrated face
// instead of a plain monogram, not a fresh portrait per field.
const PERSONA_ILLUSTRATIONS = {
  "core-elena": "avatar-core-elena",
  "core-marcus": "avatar-core-marcus",
  "core-amara": "avatar-core-amara",
  "core-sofia": "avatar-core-sofia",
  "core-theo": "avatar-core-theo",
};
const FACULTY_ILLUSTRATION_CYCLE = Object.values(PERSONA_ILLUSTRATIONS);

function illustrationIdFor(persona) {
  if (PERSONA_ILLUSTRATIONS[persona.id]) return PERSONA_ILLUSTRATIONS[persona.id];
  let hash = 0;
  for (let i = 0; i < persona.id.length; i++) hash = (hash * 31 + persona.id.charCodeAt(i)) >>> 0;
  return FACULTY_ILLUSTRATION_CYCLE[hash % FACULTY_ILLUSTRATION_CYCLE.length];
}

// A signature accent color per core teacher — carried through their card
// (ring around the avatar, role label, hover glow) so each "agent" reads as
// a distinct character at a glance, not five identical white cards that
// only differ by which photo is in the circle.
const PERSONA_ACCENT_COLORS = {
  "core-elena": "var(--blue)",
  "core-marcus": "var(--orange)",
  "core-amara": "var(--purple)",
  "core-sofia": "var(--pink)",
  "core-theo": "var(--teal)",
};
const FACULTY_ACCENT_CYCLE = Object.values(PERSONA_ACCENT_COLORS);

function accentColorFor(persona) {
  if (PERSONA_ACCENT_COLORS[persona.id]) return PERSONA_ACCENT_COLORS[persona.id];
  let hash = 0;
  for (let i = 0; i < persona.id.length; i++) hash = (hash * 31 + persona.id.charCodeAt(i)) >>> 0;
  return FACULTY_ACCENT_CYCLE[hash % FACULTY_ACCENT_CYCLE.length];
}

function renderPersonaAvatar(container, persona) {
  if (!container) return;
  container.innerHTML = "";
  if (!persona) {
    container.innerHTML = `<svg class="icon icon-brand" style="width:100%;height:100%"><use href="#icon-brand"/></svg>`;
    return;
  }
  const img = document.createElement("img");
  img.className = "persona-portrait";
  img.alt = persona.name;
  img.src = persona.portrait_url;
  img.loading = "lazy";
  img.onerror = () => {
    container.innerHTML = `<svg style="width:100%;height:100%"><use href="#${illustrationIdFor(persona)}"/></svg>`;
  };
  container.appendChild(img);
}

async function loadPersonas() {
  if (!state.personas.length) {
    state.personas = await api("/api/personas");
  }
  return state.personas;
}

function currentPersona() {
  return state.personas.find((p) => p.id === state.user?.tutor_persona_id) || null;
}

// Any language the tutor chat model knows works for exercises/conversation —
// this list is what's offered in the picker, not a hard backend restriction.
// Keep in sync with backend/hf_client.py's _MMS_LANG_CODES for TTS voice
// coverage (a language missing from that map still teaches fully via text/
// chat, it just falls back to an English voice for audio).
const LANGS = [
  ["en", "Inglés"], ["es", "Español"], ["fr", "Francés"], ["de", "Alemán"],
  ["it", "Italiano"], ["pt", "Portugués"], ["ja", "Japonés"], ["ko", "Coreano"],
  ["zh", "Chino (mandarín)"], ["ru", "Ruso"], ["ar", "Árabe"],
  ["nl", "Neerlandés"], ["sv", "Sueco"], ["pl", "Polaco"], ["tr", "Turco"], ["hi", "Hindi"],
  ["id", "Indonesio"], ["vi", "Vietnamita"], ["th", "Tailandés"], ["uk", "Ucraniano"],
  ["el", "Griego"], ["he", "Hebreo"], ["cs", "Checo"], ["ro", "Rumano"],
  ["hu", "Húngaro"], ["fi", "Finlandés"], ["da", "Danés"], ["no", "Noruego"],
  ["bg", "Búlgaro"], ["sk", "Eslovaco"], ["hr", "Croata"], ["sr", "Serbio"],
  ["lt", "Lituano"], ["lv", "Letón"], ["et", "Estonio"], ["sl", "Esloveno"],
  ["fa", "Persa (farsi)"], ["ur", "Urdu"], ["bn", "Bengalí"], ["ta", "Tamil"],
  ["te", "Telugu"], ["mr", "Maratí"], ["gu", "Guyaratí"], ["pa", "Panyabí"],
  ["ml", "Malabar"], ["kn", "Canarés"], ["ne", "Nepalí"], ["si", "Cingalés"],
  ["my", "Birmano"], ["km", "Jemer"], ["lo", "Lao"], ["ms", "Malayo"],
  ["tl", "Tagalo (filipino)"], ["sw", "Suajili"], ["am", "Amárico"], ["so", "Somalí"],
  ["ha", "Hausa"], ["yo", "Yoruba"], ["ig", "Igbo"], ["zu", "Zulú"], ["xh", "Xhosa"],
  ["af", "Afrikáans"], ["is", "Islandés"], ["ga", "Irlandés"], ["cy", "Galés"],
  ["mt", "Maltés"], ["eu", "Euskera"], ["ca", "Catalán"], ["gl", "Gallego"],
  ["az", "Azerbaiyano"], ["kk", "Kazajo"], ["uz", "Uzbeko"], ["mn", "Mongol"],
  ["ka", "Georgiano"], ["hy", "Armenio"], ["sq", "Albanés"], ["mk", "Macedonio"],
];

const LANG_NAME_BY_CODE = Object.fromEntries(LANGS);

// Every exercise type gets an explicit instruction line — before this, the
// UI showed raw exercise text with no indication of what the learner was
// supposed to do with it (translate? choose? repeat aloud?), which read as
// broken rather than as a real exercise.
const EXERCISE_INSTRUCTIONS = {
  image_match: () => "Mira la imagen y elige la palabra correcta:",
  multiple_choice: () => "Elige la opción correcta:",
  listen_type: () => "Escucha el audio y escribe lo que oyes:",
  translate_to_target: (nativeLang, targetLang) => `Traduce esta frase a ${LANG_NAME_BY_CODE[targetLang] || targetLang}:`,
  translate_to_native: (nativeLang, targetLang) => `Traduce esta frase a ${LANG_NAME_BY_CODE[nativeLang] || nativeLang}:`,
  fill_blank: () => "Completa el espacio en blanco:",
  speak_repeat: () => "Escucha y repite en voz alta:",
  free_conversation_prompt: () => "Responde con tus propias palabras:",
};

function exerciseInstructionFor(type, nativeLang, targetLang) {
  const fn = EXERCISE_INSTRUCTIONS[type];
  return fn ? fn(nativeLang, targetLang) : "Responde:";
}

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
  personas: [], // the 5 core teachers, fetched once per session — see loadPersonas()
  demoMode: false, // true when the backend has no HF_TOKEN — see checkDemoMode()
};

// Fetched once at boot (see boot()) — when true, a persistent banner explains
// why exercise content is generic placeholder text instead of real
// AI-generated lessons, rather than letting it silently look broken.
async function checkDemoMode() {
  try {
    const health = await api("/api/health");
    state.demoMode = !health.hf_configured;
  } catch {
    state.demoMode = false;
  }
}

function renderDemoModeBanner(container) {
  if (!state.demoMode || !container) return;
  const banner = document.createElement("div");
  banner.className = "demo-mode-banner";
  banner.textContent =
    "Modo demo — este servidor no tiene una clave de Hugging Face configurada, así que ves contenido de ejemplo genérico en vez de lecciones generadas por IA.";
  container.prepend(banner);
}

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
  const profileNative = $("#profile-native");
  const profileTarget = $("#profile-target");
  for (const [code, name] of LANGS) {
    native.add(new Option(name, code));
    target.add(new Option(name, code));
    profileNative.add(new Option(name, code));
    profileTarget.add(new Option(name, code));
  }
  native.value = "es";
  target.value = "en";
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
  el.innerHTML = "<p>Preparando tu siguiente pregunta…</p>";
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
  $("#placement-progress").textContent = `Pregunta ${data.question_number} de ${PLACEMENT_TOTAL}`;
  $("#placement-progress-bar").style.width = `${Math.round(((data.question_number - 1) / PLACEMENT_TOTAL) * 100)}%`;
  renderPlacementQuestion(data.exercise, data.level, el);
}

function renderPlacementQuestion(ex, level, container) {
  container.innerHTML = "";
  renderDemoModeBanner(container);

  const nativeLang = $("#ob-native").value;
  const targetLang = $("#ob-target").value;

  const instruction = document.createElement("div");
  instruction.className = "exercise-prompt";
  instruction.textContent = exerciseInstructionFor(ex.type, nativeLang, targetLang);
  container.appendChild(instruction);

  // Only the SOURCE side of a translation is ever shown — never the
  // correct_answer side, which would hand the learner the answer before
  // they've attempted it. image_match/multiple_choice show neither text
  // side, since the choices themselves carry the content.
  let source = null;
  if (ex.type === "translate_to_target") source = ex.native_text;
  else if (ex.type === "translate_to_native" || ex.type === "listen_type" || ex.type === "speak_repeat") source = ex.target_text;
  else if (ex.type === "fill_blank") source = ex.target_text;

  if (ex.type === "image_match") {
    const img = document.createElement("img");
    img.className = "exercise-image";
    container.appendChild(img);
    loadImage(img, ex.image_prompt || ex.target_text);
    playAudio(ex.audio_text || ex.target_text, targetLang);
  } else if (source) {
    const src = document.createElement("div");
    src.className = "exercise-prompt";
    src.textContent = source;
    container.appendChild(src);
    if (ex.type === "listen_type" || ex.type === "speak_repeat") {
      playAudio(ex.audio_text || ex.target_text, targetLang);
    }
  }

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
    input.placeholder = "Escribe tu respuesta…";
    const btn = document.createElement("button");
    btn.className = "btn btn-primary";
    btn.textContent = "Comprobar";
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
  renderPersonaAvatar($("#placement-avatar-slot"), null); // no account/tutor chosen yet — brand mark
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
  showScreen("#screen-main");
  await Promise.all([loadPath(), loadProgress(), loadPersonas()]);
}

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
  renderPersonaAvatar($("#dash-avatar-slot"), currentPersona());
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
  try {
    const book = await api(`/api/library/${state.userId}/books/${bookId}`);
    $("#reader-title").textContent = book.title;
    $("#reader-genre-chip").textContent = book.genre_label;
    $("#reader-level-chip").textContent = book.level;
    body.textContent = book.content;
    body.classList.remove("loading");
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
          <p class="recommendation-title">${item.title}</p>
          <p class="recommendation-creator">${item.creator}</p>
          <p class="recommendation-reason">${item.reason}</p>
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
  DOCTORATE: "Investigación (equivalente a Doctorado)",
};

// Each of the 31 fields carries a real SVG icon (backend/academy.py's
// `icon` field, drawn from index.html's icon sprite — never emoji) tinted
// by its category, rather than a plain, undifferentiated card. Colors reuse
// this app's existing palette (see styles.css :root) instead of inventing
// a new one per category.
const ACADEMY_CATEGORY_COLORS = {
  "Tecnología": ["rgba(28,176,246,0.14)", "var(--blue-dark)"],
  "Negocios": ["rgba(255,200,0,0.16)", "var(--gold-dark)"],
  "Salud": ["rgba(255,75,75,0.12)", "var(--danger)"],
  "Ciencias": ["rgba(206,130,255,0.16)", "var(--purple-dark)"],
  "Ingeniería": ["rgba(255,150,0,0.14)", "var(--orange-dark)"],
  "Humanidades": ["rgba(20,184,166,0.14)", "var(--teal-dark)"],
  "Artes": ["rgba(244,114,182,0.16)", "var(--pink-dark)"],
};

function academyFieldIconBadge(field) {
  const [bg, fg] = ACADEMY_CATEGORY_COLORS[field.category] || ["rgba(28,58,82,0.08)", "var(--text)"];
  return `<span class="field-card-icon" style="background:${bg};color:${fg}">${iconSvg(field.icon)}</span>`;
}

const _academyState = { fieldsLoaded: false, currentCourseId: null };

async function setupAcademy() {
  try {
    if (!_academyState.fieldsLoaded) {
      _academyState.fieldsLoaded = true;
      await loadAcademyFields();
      $("#academy-switch-btn").addEventListener("click", showAcademyPicker);
      $("#course-exit").addEventListener("click", () => showScreen("#screen-main"));
      $("#course-complete-btn").addEventListener("click", completeCurrentCourse);
    }
    const progress = await api(`/api/academy/${state.userId}/progress`);
    if (progress.enrollment) {
      await showAcademyCurriculum(progress);
    } else {
      showAcademyPicker();
    }
  } catch (err) {
    // A silently-failed fetch here used to just leave the tab blank/stuck —
    // "no me deja elegir ninguna carrera" — with no indication anything
    // went wrong. Surface it instead, and let the field grid stay so the
    // learner can retry.
    $("#academy-fields").innerHTML = `<p class="recommendations-empty">No se pudo cargar la Universidad: ${err.message}</p>`;
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
        ${academyFieldIconBadge(field)}
        <p class="field-card-title">${field.name}</p>
        <p class="field-card-desc">${field.description}</p>
      `;
      card.addEventListener("click", () => enrollInField(field.id));
      grid.appendChild(card);
    }
    container.appendChild(grid);
  }
}

async function enrollInField(fieldId) {
  try {
    const level = $("#academy-level-select").value;
    const progress = await api(`/api/academy/${state.userId}/enroll`, {
      method: "POST",
      body: JSON.stringify({ field_id: fieldId, level }),
    }).then(async () => api(`/api/academy/${state.userId}/progress`));
    await showAcademyCurriculum(progress);
  } catch (err) {
    // Previously unhandled — any failure here (auth hiccup, bad field id,
    // a 500) meant the click just silently did nothing, which read as
    // "no me deja elegir ninguna carrera" rather than a visible error.
    alert("No se pudo inscribir en esta carrera: " + err.message);
  }
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

  api(`/api/academy/fields/${progress.enrollment.field_id}/faculty`)
    .then((faculty) => {
      renderPersonaAvatar($("#academy-faculty-avatar"), faculty);
      $("#academy-faculty-name").textContent = `${faculty.name} — ${faculty.title}`;
      $("#academy-faculty-philosophy").textContent = faculty.philosophy;
      $("#academy-faculty-card").style.setProperty("--persona-accent", accentColorFor(faculty));
    })
    .catch((err) => console.error("No se pudo cargar el profesorado", err));

  const pct = progress.total_courses ? Math.round((progress.completed_course_ids.length / progress.total_courses) * 100) : 0;
  $("#academy-progress-fill").style.width = `${pct}%`;
  $("#academy-progress-caption").textContent = `${progress.completed_course_ids.length} de ${progress.total_courses} cursos completados`;

  const list = $("#academy-course-list");
  list.innerHTML = `<p class="recommendations-empty">Generando tu plan de estudios…</p>`;
  let curriculum;
  try {
    curriculum = await api(`/api/academy/${state.userId}/curriculum`);
  } catch (err) {
    list.innerHTML = `<p class="recommendations-empty">No se pudo generar el plan de estudios: ${err.message}</p>`;
    return;
  }
  list.innerHTML = "";
  const completedIds = new Set(progress.completed_course_ids);
  curriculum.courses.forEach((course, i) => {
    const done = completedIds.has(course.id);
    const row = document.createElement("button");
    row.className = `course-item ${done ? "completed" : ""}`;
    row.innerHTML = `
      <span class="course-item-check">${done ? iconSvg("check") : i + 1}</span>
      <div>
        <p class="course-item-title">${course.title}</p>
        <p class="course-item-desc">${course.description}</p>
      </div>
    `;
    row.addEventListener("click", () => openCourse(course.id, course.title));
    list.appendChild(row);
  });
}

async function openCourse(courseId, title) {
  _academyState.currentCourseId = courseId;
  showScreen("#screen-course");
  $("#course-title").textContent = title;
  $("#course-faculty-byline").innerHTML = "";
  const modulesEl = $("#course-modules");
  modulesEl.innerHTML = `<p class="recommendations-empty">Generando tu curso…</p>`;
  try {
    const course = await api(`/api/academy/${state.userId}/courses/${courseId}`);
    modulesEl.innerHTML = "";
    if (course.faculty) {
      const byline = $("#course-faculty-byline");
      byline.innerHTML = `
        <div class="persona-avatar-slot faculty-avatar"></div>
        <p class="course-faculty-byline-text">Impartido por <strong>${course.faculty.name}</strong>, ${course.faculty.title.toLowerCase()}</p>
      `;
      renderPersonaAvatar(byline.querySelector(".persona-avatar-slot"), course.faculty);
    }
    for (const mod of course.modules) {
      const section = document.createElement("div");
      section.innerHTML = `
        <h3 class="course-module-title">${mod.title}</h3>
        <p class="course-module-content">${mod.content}</p>
      `;
      modulesEl.appendChild(section);
    }
    if (course.sources && course.sources.length) {
      const sourcesEl = document.createElement("div");
      sourcesEl.className = "course-sources";
      sourcesEl.innerHTML = `
        <p class="course-sources-label"><svg class="icon"><use href="#icon-book"/></svg> Contenido basado en fuentes educativas abiertas reales</p>
        <ul class="course-sources-list">
          ${course.sources
            .map((s) => `<li><a href="${s.url}" target="_blank" rel="noopener noreferrer">${s.title}</a></li>`)
            .join("")}
        </ul>
      `;
      modulesEl.appendChild(sourcesEl);
    }
  } catch (err) {
    modulesEl.innerHTML = `<p class="recommendations-empty">No se pudo generar el curso: ${err.message}</p>`;
  }
}

async function completeCurrentCourse() {
  if (!_academyState.currentCourseId) return;
  const progress = await api(`/api/academy/${state.userId}/courses/${_academyState.currentCourseId}/complete`, {
    method: "POST",
  });
  showScreen("#screen-main");
  showAcademyCurriculum(progress);
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
      if (btn.dataset.tab === "talk") setupTalkTab();
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
  renderDemoModeBanner(container);

  const promptEl = document.createElement("div");
  promptEl.className = "exercise-prompt";
  promptEl.textContent = ex.prompt || "Traduce / responde:";
  container.appendChild(promptEl);

  const instructionEl = document.createElement("p");
  instructionEl.className = "subtitle exercise-instruction";
  instructionEl.textContent = exerciseInstructionFor(ex.type, state.user.native_lang, state.user.target_lang);
  container.appendChild(instructionEl);

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
          tutor_persona_id: state.user.tutor_persona_id || "",
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
  renderPersonaAvatar($("#complete-avatar-slot"), currentPersona());
  showScreen("#screen-complete");
}

$("#complete-continue").addEventListener("click", async () => {
  state.lesson = null;
  showScreen("#screen-main");
  state.user = await api(`/api/users/${state.userId}`);
  await Promise.all([loadPath(), loadProgress()]);
});

// ---------- Conversation ("Talk Live") ----------

function setupTalkTab() {
  const persona = currentPersona();
  if (!persona) {
    renderPersonaPicker();
    $("#persona-picker").classList.remove("hidden");
    $("#call-frame").classList.add("hidden");
    return;
  }
  $("#persona-picker").classList.add("hidden");
  $("#call-frame").classList.remove("hidden");
  renderPersonaAvatar($("#talk-avatar-slot"), persona);
  applyTalkDemoModeUI();
  ensureConversationSocket();
}

// Voice input can never succeed without HF_TOKEN (see backend/routers/
// conversation.py's speech_to_text demo-mode check) — rather than let the
// learner record audio and always hit the same failure, the mic button is
// disabled up front with an accurate explanation, and text input is the
// one path guaranteed to work.
function applyTalkDemoModeUI() {
  const micBtn = $("#mic-btn");
  const existingBanner = $("#call-frame .demo-mode-banner");
  if (existingBanner) existingBanner.remove();
  if (state.demoMode) {
    renderDemoModeBanner($("#call-frame"));
    micBtn.disabled = true;
    micBtn.title = "La voz no está disponible en modo demo — escribe tu mensaje abajo.";
  } else {
    micBtn.disabled = false;
    micBtn.title = "";
  }
}

function renderPersonaPicker() {
  const grid = $("#persona-picker-grid");
  grid.innerHTML = "";
  for (const persona of state.personas) {
    const accent = accentColorFor(persona);
    const card = document.createElement("div");
    card.className = "persona-card";
    card.style.setProperty("--persona-accent", accent);
    card.innerHTML = `
      <div class="persona-avatar-slot"></div>
      <p class="persona-card-name">${persona.name}</p>
      <p class="persona-card-title">${persona.title}</p>
      <p class="persona-card-philosophy">${persona.philosophy}</p>
      <button type="button" class="persona-card-preview">${iconSvg("volume")} Escuchar voz</button>
    `;
    renderPersonaAvatar(card.querySelector(".persona-avatar-slot"), persona);
    card.querySelector(".persona-card-preview").addEventListener("click", (e) => {
      e.stopPropagation();
      previewPersonaVoice(persona);
    });
    card.addEventListener("click", () => choosePersona(persona));
    grid.appendChild(card);
  }
}

async function choosePersona(persona) {
  state.user = await api(`/api/users/${state.userId}`, {
    method: "PATCH",
    body: JSON.stringify({ tutor_persona_id: persona.id }),
  });
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }
  setupTalkTab();
}

async function previewPersonaVoice(persona) {
  try {
    const res = await fetch("/api/content/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "Hola — seré tu maestro. Vamos a corregir cada detalle hasta que hables con confianza.",
        target_lang: state.user?.target_lang || "es",
        tutor_persona_id: persona.id,
      }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    new Audio(URL.createObjectURL(blob)).play();
  } catch (err) {
    console.error("No se pudo reproducir la vista previa de voz", err);
  }
}

$("#change-tutor-btn").addEventListener("click", () => {
  renderPersonaPicker();
  $("#persona-picker").classList.remove("hidden");
  $("#call-frame").classList.add("hidden");
});

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
      const critiqueEl = renderCritiqueMetrics(msg.critique_metrics);
      if (critiqueEl) $("#transcript").appendChild(critiqueEl);
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

// Structured record of one turn's corrections (see backend hf_client.
// conversation_reply's critique_metrics) — a separate, scannable list of
// what was actually flagged, distinct from the natural spoken reply above it.
const CRITIQUE_LABELS = {
  grammar: "Gramática",
  pronunciation: "Pronunciación",
  comprehension: "Comprensión",
  knowledge: "Conocimiento",
};

function renderCritiqueMetrics(critiqueMetrics) {
  if (!critiqueMetrics) return null;
  const items = [];
  for (const [key, label] of Object.entries(CRITIQUE_LABELS)) {
    for (const entry of critiqueMetrics[key] || []) {
      const detail = entry.error || entry.issue || entry.claim || "";
      const fix = entry.correction || entry.fix || "";
      if (!detail && !fix) continue;
      items.push(`<li><strong>${label}:</strong> ${detail}${fix ? ` → ${fix}` : ""}</li>`);
    }
  }
  if (!items.length) return null;
  const div = document.createElement("div");
  div.className = "critique-metrics";
  div.innerHTML = `<p class="critique-metrics-label">Correcciones de este turno</p><ul>${items.join("")}</ul>`;
  return div;
}

function addTranscriptBubble(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  $("#transcript").appendChild(div);
  const transcript = $("#transcript");
  if (role === "assistant") {
    typewriteInto(div, text, transcript);
  } else {
    div.textContent = text;
    transcript.scrollTop = transcript.scrollHeight;
  }
}

// A tutor reply appearing all at once, mid-conversation, reads as a canned
// response — typing it out (like a real person composing a reply) is part
// of what makes the persona feel like it's actually there, not a static
// text dump.
function typewriteInto(el, text, scrollContainer, charsPerTick = 2, tickMs = 18) {
  el.classList.add("typing");
  let i = 0;
  const timer = setInterval(() => {
    i = Math.min(text.length, i + charsPerTick);
    el.textContent = text.slice(0, i);
    if (scrollContainer) scrollContainer.scrollTop = scrollContainer.scrollHeight;
    if (i >= text.length) {
      clearInterval(timer);
      el.classList.remove("typing");
    }
  }, tickMs);
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

// ---------- Profile / account settings ----------

function openProfile() {
  const u = state.user;
  $("#profile-name").value = u.display_name || "";
  $("#profile-native").value = u.native_lang;
  $("#profile-target").value = u.target_lang;
  $("#profile-interests").value = (u.interests || []).join(", ");
  $("#profile-daily-goal").value = String(u.daily_goal_minutes || 15);
  $("#profile-saved-msg").classList.add("hidden");
  $("#profile-delete-confirm").classList.add("hidden");
  showScreen("#screen-profile");
}

function setupProfile() {
  $("#open-profile-btn").addEventListener("click", openProfile);
  $("#profile-exit").addEventListener("click", () => showScreen("#screen-main"));

  $("#profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      state.user = await api(`/api/users/${state.userId}`, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: $("#profile-name").value.trim(),
          native_lang: $("#profile-native").value,
          target_lang: $("#profile-target").value,
          interests: $("#profile-interests").value.split(",").map((s) => s.trim()).filter(Boolean),
          daily_goal_minutes: parseInt($("#profile-daily-goal").value, 10) || 15,
        }),
      });
      $("#profile-saved-msg").classList.remove("hidden");
    } catch (err) {
      alert("No se pudo guardar el perfil: " + err.message);
    } finally {
      btn.disabled = false;
    }
  });

  $("#profile-logout-btn").addEventListener("click", signOut);

  $("#profile-delete-btn").addEventListener("click", () => {
    $("#profile-delete-confirm").classList.remove("hidden");
  });
  $("#profile-delete-cancel-btn").addEventListener("click", () => {
    $("#profile-delete-confirm").classList.add("hidden");
  });
  $("#profile-delete-confirm-btn").addEventListener("click", async () => {
    const btn = $("#profile-delete-confirm-btn");
    btn.disabled = true;
    try {
      await api(`/api/users/${state.userId}`, { method: "DELETE" });
      state.userId = null;
      state.user = null;
      if (state.ws) state.ws.close();
      location.href = "/";
    } catch (err) {
      alert("No se pudo eliminar la cuenta: " + err.message);
      btn.disabled = false;
    }
  });
}

// ---------- Boot ----------

async function boot() {
  populateLangSelects();
  $("#onboarding-form").addEventListener("submit", handleOnboardingSubmit);
  setupTabs();
  setupMic();
  setupDevLogin();
  setupProfile();
  await checkDemoMode();
  await checkSession();
}

boot();
