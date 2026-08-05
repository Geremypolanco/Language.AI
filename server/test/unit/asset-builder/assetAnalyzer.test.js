import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { analyzeLesson } from '../../../src/asset-builder/analyzer/AssetAnalyzer.js';

function lesson(overrides = {}) {
  return {
    lessonId: 'l1',
    courseId: 'c1',
    discipline: 'Álgebra Lineal',
    language: 'es',
    level: 'beginner',
    title: 'Ecuaciones lineales',
    objectives: ['Resolver ecuaciones lineales de una variable'],
    sections: [
      { heading: 'Intro', body: 'Una ecuación lineal tiene la forma 3x + 5 = 20 y se resuelve despejando x.' },
      { heading: 'Ejemplo resuelto', body: 'Consideremos 3x + 5 = 20. Restamos 5: 3x = 15. Dividimos: x = 5.' },
    ],
    ...overrides,
  };
}

describe('analyzeLesson', () => {
  test('classifies discipline family from the discipline string', async () => {
    const analysis = await analyzeLesson(lesson());
    assert.equal(analysis.disciplineFamily, 'mathematics');
  });

  test('classifies content type as quantitative from real formula density, not the title', async () => {
    const analysis = await analyzeLesson(lesson());
    assert.equal(analysis.contentType, 'quantitative');
  });

  test('classifies a language lesson as vocabulary content type', async () => {
    const analysis = await analyzeLesson(lesson({ discipline: 'Vocabulario inglés' }));
    assert.equal(analysis.disciplineFamily, 'languages');
    assert.equal(analysis.contentType, 'vocabulary');
  });

  test('extracts subtopics from section headings', async () => {
    const analysis = await analyzeLesson(lesson());
    assert.ok(analysis.subtopics.includes('Intro'));
    assert.ok(analysis.subtopics.includes('Ejemplo resuelto'));
  });

  test('extracts real formula expressions from the body text', async () => {
    const analysis = await analyzeLesson(lesson());
    assert.ok(analysis.formulas.length > 0);
    assert.ok(analysis.formulas.some((f) => f.includes('=')));
  });

  test('extracts worked examples from sections whose heading says so', async () => {
    const analysis = await analyzeLesson(lesson());
    assert.equal(analysis.workedExamples.length, 1);
    assert.equal(analysis.workedExamples[0].heading, 'Ejemplo resuelto');
  });

  test('builds excerpts mapping keywords to real sentences that contain them', async () => {
    const analysis = await analyzeLesson(lesson());
    for (const [term, excerpt] of Object.entries(analysis.excerpts)) {
      assert.ok(
        excerpt.toLowerCase().includes(term.toLowerCase()),
        `excerpt for "${term}" should actually contain that term`
      );
    }
  });

  test('a lesson with no formulas or example sections produces empty arrays, not fabricated content', async () => {
    const historyLesson = lesson({
      discipline: 'Historia Universal',
      sections: [{ heading: 'Contexto', body: 'La revolución comenzó por causas económicas y sociales diversas.' }],
    });
    const analysis = await analyzeLesson(historyLesson);
    assert.deepEqual(analysis.formulas, []);
    assert.deepEqual(analysis.workedExamples, []);
  });
});
