/**
 * Maps a free-text discipline string (as authored upstream, e.g.
 * "Álgebra Lineal", "Biología Celular") to a coarse family the Planner's
 * rule table keys off of. Matching is substring-based on purpose — course
 * authors won't use a controlled vocabulary.
 */
const FAMILY_KEYWORDS = {
  languages: ['idioma', 'language', 'vocabulary', 'vocabulario', 'grammar', 'gramática', 'pronunciation', 'pronunciación'],
  mathematics: ['math', 'matemátic', 'álgebra', 'algebra', 'cálculo', 'calculus', 'geometr', 'trigonometr', 'estadística', 'statistics'],
  science: ['biolog', 'química', 'chemistry', 'física', 'physics', 'ciencia', 'science', 'anatom', 'ecolog'],
  engineering: ['ingenier', 'engineering', 'programación', 'programming', 'software', 'circuit', 'mecánica', 'mechanics', 'arquitectura de'],
  history: ['historia', 'history', 'social studies', 'ciencias sociales', 'geografía', 'geography'],
  arts: ['arte', 'art', 'música', 'music', 'literatura', 'literature', 'diseño', 'design'],
};

export function classifyDisciplineFamily(disciplineText) {
  const normalized = disciplineText.toLowerCase();
  for (const [family, keywords] of Object.entries(FAMILY_KEYWORDS)) {
    if (keywords.some((kw) => normalized.includes(kw))) return family;
  }
  return 'generic';
}
