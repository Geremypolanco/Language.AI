import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  ExercisePackage,
  AssessmentPackage,
  LessonPackage,
  CoursePackage,
  CurriculumPackage,
  ContentPackage,
  Competency,
  LearningObjective,
  CourseDependency,
} from '../../../src/domain/editorial/index.js';

function multipleChoiceExercise(id = 'ex1') {
  return new ExercisePackage({
    id,
    lessonId: 'lesson1',
    prompt: '2x = 10, x = ?',
    type: 'multiple-choice',
    options: [
      { id: 'a', text: '5', correct: true },
      { id: 'b', text: '10', correct: false },
    ],
  });
}

describe('ExercisePackage', () => {
  test('checkAnswer grades multiple-choice correctly', () => {
    const ex = multipleChoiceExercise();
    assert.equal(ex.checkAnswer('a'), true);
    assert.equal(ex.checkAnswer('b'), false);
  });

  test('checkAnswer grades open-ended answers case/whitespace-insensitively', () => {
    const ex = new ExercisePackage({
      id: 'ex2',
      lessonId: 'lesson1',
      prompt: 'Capital of France?',
      type: 'open-ended',
      correctAnswer: 'Paris',
    });
    assert.equal(ex.checkAnswer('  paris '), true);
    assert.equal(ex.checkAnswer('London'), false);
  });

  test('checkAnswer returns null (not false) for an ungradable open-ended item', () => {
    const ex = new ExercisePackage({ id: 'ex3', lessonId: 'lesson1', prompt: 'Reflect on X', type: 'open-ended' });
    assert.equal(ex.checkAnswer('anything'), null);
  });

  test('rejects an invalid exercise type', () => {
    assert.throws(() => new ExercisePackage({ id: 'x', lessonId: 'l', prompt: 'p', type: 'not-a-type' }));
  });
});

describe('AssessmentPackage', () => {
  test('evaluate() computes a real score from exercise results', () => {
    const assessment = new AssessmentPackage({
      id: 'a1',
      lessonId: 'lesson1',
      title: 'Quiz',
      exercises: [multipleChoiceExercise('ex1'), multipleChoiceExercise('ex2')],
      passingScore: 0.5,
    });
    const result = assessment.evaluate({ ex1: 'a', ex2: 'b' }); // one right, one wrong
    assert.equal(result.score, 0.5);
    assert.equal(result.passed, true); // 0.5 >= passingScore 0.5
    assert.equal(result.results.length, 2);
  });

  test('evaluate() excludes ungradable exercises from the score', () => {
    const openEnded = new ExercisePackage({ id: 'oe', lessonId: 'lesson1', prompt: 'Discuss', type: 'open-ended' });
    const assessment = new AssessmentPackage({
      id: 'a2',
      lessonId: 'lesson1',
      title: 'Mixed',
      exercises: [multipleChoiceExercise('ex1'), openEnded],
    });
    const result = assessment.evaluate({ ex1: 'a', oe: 'some reflection' });
    assert.equal(result.score, 1); // only ex1 counted, and it was correct
    assert.equal(result.ungradableCount, 1);
  });

  test('rejects passingScore outside 0..1', () => {
    assert.throws(() => new AssessmentPackage({ id: 'x', lessonId: 'l', title: 't', passingScore: 1.5 }));
  });
});

describe('LessonPackage', () => {
  const baseLesson = {
    lessonId: 'algebra-1',
    courseId: 'course-1',
    discipline: 'Álgebra',
    language: 'es',
    level: 'beginner',
    title: 'Ecuaciones',
    objectives: ['Resolver ecuaciones'],
    sections: [{ heading: 'Intro', body: 'texto' }],
  };

  test('toLessonContent() adapts back to the plain asset-builder contract', () => {
    const lesson = new LessonPackage(baseLesson);
    const content = lesson.toLessonContent();
    assert.deepEqual(Object.keys(content).sort(), [
      'courseId',
      'discipline',
      'language',
      'lessonId',
      'level',
      'objectives',
      'sections',
      'title',
    ]);
    assert.equal(content.lessonId, 'algebra-1');
  });

  test('isReadyForPublication is false without learning objectives', () => {
    const lesson = new LessonPackage(baseLesson);
    assert.equal(lesson.isReadyForPublication(), false);
  });

  test('isReadyForPublication is true once it has a learning objective and no asset gaps', () => {
    const lesson = new LessonPackage({
      ...baseLesson,
      learningObjectives: [new LearningObjective({ id: 'o1', statement: 'Resolver ecuaciones', bloomLevel: 'apply' })],
    });
    assert.equal(lesson.isReadyForPublication(), true);
  });

  test('objectiveCoverageByBloomLevel tallies objectives per Bloom level', () => {
    const lesson = new LessonPackage({
      ...baseLesson,
      learningObjectives: [
        new LearningObjective({ id: 'o1', statement: 'a', bloomLevel: 'apply' }),
        new LearningObjective({ id: 'o2', statement: 'b', bloomLevel: 'apply' }),
        new LearningObjective({ id: 'o3', statement: 'c', bloomLevel: 'analyze' }),
      ],
    });
    const coverage = lesson.objectiveCoverageByBloomLevel();
    assert.equal(coverage.apply, 2);
    assert.equal(coverage.analyze, 1);
    assert.equal(coverage.remember, 0);
  });
});

describe('CoursePackage / CurriculumPackage', () => {
  function lessonWithObjective(lessonId, competencyId) {
    return new LessonPackage({
      lessonId,
      courseId: 'course-1',
      discipline: 'Álgebra',
      language: 'es',
      level: 'beginner',
      title: lessonId,
      objectives: [],
      sections: [{ heading: 'h', body: 'b' }],
      learningObjectives: [
        new LearningObjective({ id: `${lessonId}-obj`, statement: 's', relatedCompetencyIds: [competencyId] }),
      ],
    });
  }

  test('CurriculumPackage.coverage() reflects real competency satisfaction', () => {
    const course = new CoursePackage({
      id: 'course-1',
      title: 'Algebra I',
      discipline: 'Álgebra',
      lessons: [lessonWithObjective('l1', 'comp1')],
    });
    const curriculum = new CurriculumPackage({
      id: 'curr1',
      title: 'Math',
      discipline: 'Matemáticas',
      courses: [course],
      competencies: [
        new Competency({ id: 'comp1', name: 'Solve equations' }),
        new Competency({ id: 'comp2', name: 'Unrelated' }),
      ],
    });
    assert.equal(curriculum.coverage(), 0.5); // comp1 satisfied, comp2 not
    assert.deepEqual(
      curriculum.uncoveredCompetencies().map((c) => c.id),
      ['comp2']
    );
  });

  test('hasCyclicCourseDependencies detects a real cycle (A depends on B depends on A)', () => {
    const courseA = new CoursePackage({
      id: 'A',
      title: 'A',
      discipline: 'x',
      dependencies: [new CourseDependency({ courseId: 'A', dependsOnCourseId: 'B' })],
    });
    const courseB = new CoursePackage({
      id: 'B',
      title: 'B',
      discipline: 'x',
      dependencies: [new CourseDependency({ courseId: 'B', dependsOnCourseId: 'A' })],
    });
    const curriculum = new CurriculumPackage({ id: 'c', title: 'C', discipline: 'x', courses: [courseA, courseB] });
    assert.equal(curriculum.hasCyclicCourseDependencies(), true);
  });

  test('coursePublicationOrder respects a real (acyclic) dependency chain', () => {
    const courseA = new CoursePackage({ id: 'A', title: 'A', discipline: 'x' });
    const courseB = new CoursePackage({
      id: 'B',
      title: 'B',
      discipline: 'x',
      dependencies: [new CourseDependency({ courseId: 'B', dependsOnCourseId: 'A' })],
    });
    const curriculum = new CurriculumPackage({ id: 'c', title: 'C', discipline: 'x', courses: [courseB, courseA] });
    const order = curriculum.coursePublicationOrder().map((c) => c.id);
    assert.deepEqual(order, ['A', 'B']); // A (the dependency) must publish before B
  });

  test('ContentPackage aggregates totals across curricula/courses/lessons', () => {
    const course = new CoursePackage({
      id: 'course-1',
      title: 'Algebra I',
      discipline: 'x',
      lessons: [lessonWithObjective('l1', 'comp1'), lessonWithObjective('l2', 'comp1')],
    });
    const curriculum = new CurriculumPackage({ id: 'curr1', title: 'Math', discipline: 'x', courses: [course] });
    const content = new ContentPackage({ id: 'content1', title: 'Math Content', curricula: [curriculum] });
    assert.equal(content.totalCourses(), 1);
    assert.equal(content.totalLessons(), 2);
  });
});
