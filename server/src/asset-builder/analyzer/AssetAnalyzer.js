import { STOPWORDS } from './stopwords.js';
import { classifyDisciplineFamily } from './disciplineTaxonomy.js';
import { aiEnhanceAnalysis } from '../lib/aiEnhance.js';

const WORD_RE = /[a-zà-öø-ÿ]+/gi;
const FORMULA_SIGNAL_RE = /[=+\-^]|\\frac|\bsin\b|\bcos\b|\btan\b|\bln\b|\blog\b|∑|∫|√/i;
const YEAR_RE = /\b(1[0-9]{3}|20[0-9]{2})\b/g;
// A short run containing a variable, an operator, and a '=' — e.g. "3x + 5 = 20".
// Deliberately conservative (real matches, no fabrication) over recall.
const FORMULA_EXPRESSION_RE = /\b\d*[a-zA-Z]\w*\s*[+\-*/^]\s*[\w.]+\s*=\s*[\w.+\-*/^]+/g;
const EXAMPLE_HEADING_RE = /ejemplo|example|worked/i;

function tokenize(text) {
  return (text.match(WORD_RE) || []).map((w) => w.toLowerCase());
}

function splitSentences(text) {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Maps each term to the first sentence in the lesson that actually contains it — real excerpts, not generated definitions. */
function buildExcerptIndex(fullText, terms) {
  const sentences = splitSentences(fullText);
  const index = {};
  for (const term of terms) {
    const needle = term.toLowerCase();
    const match = sentences.find((s) => s.toLowerCase().includes(needle));
    if (match) index[term] = match;
  }
  return index;
}

function extractFormulas(fullText) {
  return dedupe(fullText.match(FORMULA_EXPRESSION_RE) || []).slice(0, 10);
}

function extractWorkedExamples(sections) {
  return sections.filter((s) => EXAMPLE_HEADING_RE.test(s.heading)).map((s) => ({ heading: s.heading, body: s.body }));
}

function topKeywordsByFrequency(text, limit = 15) {
  const counts = new Map();
  for (const word of tokenize(text)) {
    if (word.length < 4 || STOPWORDS.has(word)) continue;
    counts.set(word, (counts.get(word) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([word]) => word);
}

/**
 * Heuristic content-type classification from real signals in the body text
 * (formula density, date density, discipline family) rather than guessing
 * from the title alone.
 */
function classifyContentType(fullText, disciplineFamily) {
  const formulaHits = (fullText.match(new RegExp(FORMULA_SIGNAL_RE, 'gi')) || []).length;
  const yearHits = (fullText.match(YEAR_RE) || []).length;
  const wordCount = tokenize(fullText).length || 1;

  if (disciplineFamily === 'languages') return 'vocabulary';
  if (formulaHits / wordCount > 0.01) return 'quantitative';
  if (yearHits >= 3) return 'historical-narrative';
  if (disciplineFamily === 'science') return 'scientific';
  if (disciplineFamily === 'engineering') return 'technical-engineering';
  return 'conceptual';
}

/**
 * Extracts topic, subtopics, concepts, keywords, level, discipline and
 * content type from the lesson's *full* content — never from the title
 * alone. Runs first in the pipeline so every downstream stage (Planner,
 * Providers, Validator) works off real signal instead of assumptions.
 */
export async function analyzeLesson(lesson) {
  const fullText = [lesson.title, ...lesson.objectives, ...lesson.sections.flatMap((s) => [s.heading, s.body])].join(
    '\n'
  );

  const disciplineFamily = classifyDisciplineFamily(lesson.discipline);
  const contentType = classifyContentType(fullText, disciplineFamily);
  const heuristicKeywords = topKeywordsByFrequency(fullText);
  const subtopics = lesson.sections.map((s) => s.heading);

  const aiResult = await aiEnhanceAnalysis(fullText);

  const keywords = dedupe([...(aiResult?.keywords ?? []), ...heuristicKeywords]).slice(0, 20);
  const concepts = dedupe(aiResult?.concepts ?? []);
  const enrichedSubtopics = dedupe([...(aiResult?.subtopics ?? []), ...subtopics]);
  const excerpts = buildExcerptIndex(fullText, dedupe([...keywords, ...concepts]));
  const formulas = extractFormulas(fullText);
  const workedExamples = extractWorkedExamples(lesson.sections);

  return {
    lessonId: lesson.lessonId,
    courseId: lesson.courseId,
    language: lesson.language,
    level: lesson.level,
    discipline: lesson.discipline,
    disciplineFamily,
    contentType,
    mainTopic: lesson.title,
    subtopics: enrichedSubtopics,
    concepts,
    objectives: lesson.objectives,
    keywords,
    excerpts,
    formulas,
    workedExamples,
  };
}

function dedupe(arr) {
  const seen = new Set();
  const out = [];
  for (const item of arr) {
    const key = item.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(item.trim());
  }
  return out;
}
