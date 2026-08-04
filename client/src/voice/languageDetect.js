const LANGUAGE_MARKERS = {
  es: ['que', 'de', 'la', 'el', 'y', 'es', 'por', 'para', 'con', 'como', 'que', 'esta', 'hola'],
  en: ['the', 'is', 'and', 'you', 'to', 'of', 'that', 'what', 'how', 'are', 'hello'],
  fr: ['le', 'la', 'de', 'et', 'est', 'que', 'vous', 'pour', 'avec', 'comment', 'bonjour'],
  pt: ['que', 'de', 'para', 'com', 'nao', 'voce', 'esta', 'como', 'ola'],
  de: ['der', 'die', 'das', 'und', 'ist', 'nicht', 'was', 'wie', 'hallo'],
  it: ['che', 'di', 'per', 'come', 'con', 'sono', 'questo', 'ciao'],
};

const LOCALE_TAGS = { es: 'es-ES', en: 'en-US', fr: 'fr-FR', pt: 'pt-BR', de: 'de-DE', it: 'it-IT' };

const COMBINING_DIACRITICS_RE = new RegExp('[\\u0300-\\u036f]', 'g');

function stripAccents(text) {
  return text.normalize('NFD').replace(COMBINING_DIACRITICS_RE, '');
}

/**
 * Coarse heuristic language guess from function-word frequency — enough to
 * auto-steer STT/TTS locale mid-call without a heavyweight NLP dependency.
 * Not a substitute for a real language-ID model; swap this for one (or a
 * server-side detector) if higher accuracy is needed.
 */
export function detectLanguage(text) {
  const words = stripAccents(text.toLowerCase()).match(/[a-z]+/g) || [];
  if (words.length < 2) return null; // too short to guess reliably

  let bestLang = null;
  let bestScore = 0;
  for (const [lang, markers] of Object.entries(LANGUAGE_MARKERS)) {
    const score = words.filter((w) => markers.includes(w)).length;
    if (score > bestScore) {
      bestScore = score;
      bestLang = lang;
    }
  }

  if (!bestLang || bestScore === 0) return null;
  return { code: bestLang, locale: LOCALE_TAGS[bestLang] };
}

export function localeForLanguageCode(code) {
  return LOCALE_TAGS[code] || code;
}
