import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { planLessonAssets } from '../../../src/asset-builder/planner/AssetPlanner.js';

function analysisFor(disciplineFamily, extra = {}) {
  return {
    lessonId: 'l1',
    courseId: 'c1',
    language: 'es',
    level: 'beginner',
    discipline: 'x',
    disciplineFamily,
    contentType: 'conceptual',
    mainTopic: 'Topic',
    subtopics: ['Sub A', 'Sub B'],
    concepts: ['concept-a', 'concept-b'],
    objectives: [],
    keywords: ['keyword-a', 'keyword-b'],
    ...extra,
  };
}

describe('planLessonAssets', () => {
  test('mathematics never plans photographs, per the spec ("no asumir que todas las lecciones necesitan fotografías")', () => {
    const plan = planLessonAssets(analysisFor('mathematics'));
    const photoLikeItems = plan.filter((p) => p.resourceType === 'image' || p.resourceType === 'gallery');
    assert.equal(photoLikeItems.length, 0);
  });

  test('mathematics plans formula/example/diagram/table resources', () => {
    const plan = planLessonAssets(analysisFor('mathematics'));
    const types = plan.map((p) => p.resourceType);
    assert.ok(types.includes('formula'));
    assert.ok(types.includes('example'));
    assert.ok(types.includes('diagram'));
  });

  test('languages requires audio and flashcards for real vocabulary practice', () => {
    const plan = planLessonAssets(analysisFor('languages'));
    const required = plan.filter((p) => p.priority === 'required').map((p) => p.resourceType);
    assert.ok(required.includes('audio'));
    assert.ok(required.includes('flashcards'));
  });

  test('history requires a timeline-format diagram and recommends period photographs', () => {
    const plan = planLessonAssets(analysisFor('history'));
    const timeline = plan.find((p) => p.resourceType === 'diagram');
    assert.equal(timeline.preferredFormat, 'timeline-svg');
    const image = plan.find((p) => p.resourceType === 'image');
    assert.equal(image.preferredFormat, 'historical-photo');
  });

  test('engineering prefers mermaid diagrams over photographs for technical concepts', () => {
    const plan = planLessonAssets(analysisFor('engineering'));
    const diagram = plan.find((p) => p.resourceType === 'diagram');
    assert.equal(diagram.preferredFormat, 'mermaid');
    assert.equal(diagram.priority, 'required');
    assert.equal(
      plan.some((p) => p.resourceType === 'image'),
      false
    );
  });

  test('science treats real photographs as optional, illustrations as required', () => {
    const plan = planLessonAssets(analysisFor('science'));
    const illustration = plan.find((p) => p.resourceType === 'illustration');
    const image = plan.find((p) => p.resourceType === 'image');
    assert.equal(illustration.priority, 'required');
    assert.equal(image.priority, 'optional');
  });

  test('an unrecognized discipline family falls back to the generic rule set without crashing', () => {
    const plan = planLessonAssets(analysisFor('generic'));
    assert.ok(plan.length > 0);
  });

  test('every plan item has a positive quantity (zero-quantity items are filtered out)', () => {
    for (const family of ['mathematics', 'languages', 'science', 'engineering', 'history', 'arts', 'generic']) {
      const plan = planLessonAssets(analysisFor(family));
      assert.ok(plan.every((p) => p.quantity > 0));
    }
  });
});
