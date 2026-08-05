import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  Progress,
  Exercise,
  Assignment,
  CourseContent,
  Curriculum,
  Dashboard,
} from '../../../src/domain/runtime/index.js';

describe('Progress', () => {
  test('recordCompletion transitions not-started -> in-progress -> completed', () => {
    const p = new Progress({ id: 'p1', learnerId: 'l1', targetType: 'lesson', targetId: 'lesson-1' });
    p.recordCompletion(0.4);
    assert.equal(p.status, 'in-progress');
    p.recordCompletion(1);
    assert.equal(p.status, 'completed');
    assert.ok(p.completedAt);
  });

  test('masteryLevel buckets a numeric score categorically', () => {
    const p = new Progress({ id: 'p1', learnerId: 'l1', targetType: 'lesson', targetId: 'lesson-1' });
    assert.equal(p.masteryLevel(), 'unassessed');
    p.recordMastery(0.9);
    assert.equal(p.masteryLevel(), 'advanced');
    p.recordMastery(0.65);
    assert.equal(p.masteryLevel(), 'proficient');
  });
});

describe('Exercise (runtime attempt)', () => {
  test('submit/recordGrade tracks attempts and correctness', () => {
    const attempt = new Exercise({ id: 'a1', learnerId: 'l1', exercisePackageId: 'ex-pkg-1', maxAttempts: 2 });
    attempt.submit('my answer');
    assert.equal(attempt.attempts, 1);
    attempt.recordGrade(false);
    assert.equal(attempt.attemptsRemaining(), 1);
    assert.equal(attempt.canRetry(), true);
  });

  test('cannot retry once correct, even with attempts left', () => {
    const attempt = new Exercise({ id: 'a1', learnerId: 'l1', exercisePackageId: 'ex-pkg-1', maxAttempts: 5 });
    attempt.submit('answer').recordGrade(true);
    assert.equal(attempt.canRetry(), false);
  });

  test('submit throws once attempts are exhausted', () => {
    const attempt = new Exercise({ id: 'a1', learnerId: 'l1', exercisePackageId: 'ex-pkg-1', maxAttempts: 1 });
    attempt.submit('x').recordGrade(false);
    assert.throws(() => attempt.submit('y'), /no attempts remaining/);
  });

  test('never imports an editorial class — references the package only by id', () => {
    const attempt = new Exercise({ id: 'a1', learnerId: 'l1', exercisePackageId: 'ex-pkg-1' });
    assert.equal(typeof attempt.exercisePackageId, 'string');
  });
});

describe('Assignment', () => {
  test('isOverdue is computed from the current time, not stored', () => {
    const overdue = new Assignment({
      id: 'a1',
      learnerId: 'l1',
      targetType: 'exercise',
      targetId: 'ex1',
      dueDate: new Date(Date.now() - 86400000).toISOString(),
    });
    assert.equal(overdue.isOverdue(), true);

    const future = new Assignment({
      id: 'a2',
      learnerId: 'l1',
      targetType: 'exercise',
      targetId: 'ex1',
      dueDate: new Date(Date.now() + 86400000).toISOString(),
    });
    assert.equal(future.isOverdue(), false);
  });

  test('a submitted assignment is never overdue even past its due date', () => {
    const a = new Assignment({
      id: 'a3',
      learnerId: 'l1',
      targetType: 'exercise',
      targetId: 'ex1',
      dueDate: new Date(Date.now() - 86400000).toISOString(),
    });
    a.submit();
    assert.equal(a.isOverdue(), false);
  });

  test('grade() requires submission first', () => {
    const a = new Assignment({ id: 'a4', learnerId: 'l1', targetType: 'exercise', targetId: 'ex1' });
    assert.throws(() => a.grade(0.8), /cannot be graded before/);
    a.submit();
    a.grade(0.8);
    assert.equal(a.status, 'graded');
    assert.equal(a.score, 0.8);
  });
});

describe('CourseContent / Curriculum / Dashboard', () => {
  function courseContentAt(percent) {
    const totalLessons = 4;
    const completedCount = Math.round(percent * totalLessons);
    const lessonProgress = Array.from({ length: completedCount }, (_, i) =>
      new Progress({ id: `p${i}`, learnerId: 'l1', targetType: 'lesson', targetId: `lesson-${i}` }).recordCompletion(1)
    );
    return new CourseContent({
      id: `cc-${percent}`,
      learnerId: 'l1',
      coursePackageId: 'course-1',
      totalLessons,
      lessonProgress,
    });
  }

  test('completionPercentage divides completed lessons by total', () => {
    const cc = courseContentAt(0.5);
    assert.equal(cc.completionPercentage(), 0.5);
  });

  test('nextIncompleteLessonId follows the declared lesson order', () => {
    const p0 = new Progress({ id: 'p0', learnerId: 'l1', targetType: 'lesson', targetId: 'lesson-0' }).recordCompletion(
      1
    );
    const cc = new CourseContent({
      id: 'cc1',
      learnerId: 'l1',
      coursePackageId: 'course-1',
      totalLessons: 2,
      lessonOrder: ['lesson-0', 'lesson-1'],
      lessonProgress: [p0],
    });
    assert.equal(cc.nextIncompleteLessonId(), 'lesson-1');
  });

  test('Curriculum.overallProgress averages its CourseContent completion', () => {
    const curriculum = new Curriculum({
      id: 'curr1',
      learnerId: 'l1',
      curriculumPackageId: 'curr-pkg-1',
      courseContents: [courseContentAt(1), courseContentAt(0)],
    });
    assert.equal(curriculum.overallProgress(), 0.5);
  });

  test('Dashboard.summary/upcoming/overdue/atRisk aggregate real records', () => {
    const dueSoon = new Assignment({
      id: 'a1',
      learnerId: 'l1',
      targetType: 'exercise',
      targetId: 'ex1',
      dueDate: new Date(Date.now() + 2 * 86400000).toISOString(),
    });
    const overdue = new Assignment({
      id: 'a2',
      learnerId: 'l1',
      targetType: 'exercise',
      targetId: 'ex2',
      dueDate: new Date(Date.now() - 86400000).toISOString(),
    });
    const dashboard = new Dashboard({
      learnerId: 'l1',
      courseContents: [courseContentAt(0.25), courseContentAt(1)],
      assignments: [dueSoon, overdue],
    });

    const summary = dashboard.summary();
    assert.equal(summary.totalCourses, 2);
    assert.equal(summary.upcomingAssignmentsCount, 1);
    assert.equal(summary.overdueAssignmentsCount, 1);
    assert.deepEqual(
      dashboard.atRiskCourses(0.3).map((c) => c.id),
      ['cc-0.25']
    );
  });
});
