import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { PublicationVersion, BuildJob, Publication } from '../../../src/domain/editorial/index.js';

describe('PublicationVersion', () => {
  test('knows version, date, status, and compatibility', () => {
    const v = new PublicationVersion({ versionNumber: 1, compatibleSchemaVersion: '1.4' });
    assert.equal(v.versionNumber, 1);
    assert.ok(v.createdAt);
    assert.equal(v.status.value, 'draft');
    assert.equal(v.isCompatibleWith('1.9'), true); // same major
    assert.equal(v.isCompatibleWith('2.0'), false); // different major
  });

  test('publish() sets publishedAt and transitions status', () => {
    const v = new PublicationVersion({ versionNumber: 1 });
    const published = v.publish();
    assert.equal(published.status.isLive(), true);
    assert.ok(published.publishedAt);
    assert.equal(v.status.value, 'draft'); // original instance untouched
  });

  test('isCurrent is only true for the matching, live version', () => {
    const v1 = new PublicationVersion({ versionNumber: 1 }).publish();
    assert.equal(v1.isCurrent(1), true);
    assert.equal(v1.isCurrent(2), false);
  });
});

describe('BuildJob', () => {
  test('runs through the full pending -> running -> succeeded lifecycle', () => {
    const job = new BuildJob({ id: 'job1', targetType: 'lesson', targetId: 'lesson-1' });
    const running = job.start();
    assert.equal(running.status.value, 'running');
    assert.ok(running.startedAt);
    const done = running.succeed();
    assert.equal(done.status.value, 'succeeded');
    assert.ok(typeof done.durationMs() === 'number');
  });

  test('fail() records the error message', () => {
    const job = new BuildJob({ id: 'job2', targetType: 'lesson', targetId: 'lesson-1' }).start();
    const failed = job.fail('provider timed out');
    assert.equal(failed.status.value, 'failed');
    assert.equal(failed.errorMessage, 'provider timed out');
  });

  test('a succeeded job cannot be started again', () => {
    const job = new BuildJob({ id: 'job3', targetType: 'lesson', targetId: 'lesson-1' }).start().succeed();
    assert.throws(() => job.start(), /Cannot transition/);
  });
});

describe('Publication', () => {
  test('publish() makes the version current and preserves history', () => {
    const pub = new Publication({ id: 'pub1', targetType: 'lesson', targetId: 'lesson-1' });
    pub.publish(new PublicationVersion({ versionNumber: 1 }));
    assert.equal(pub.currentVersion.versionNumber, 1);
    assert.equal(pub.isLive(), true);

    pub.publish(new PublicationVersion({ versionNumber: 2 }));
    assert.equal(pub.currentVersion.versionNumber, 2);
    assert.equal(pub.versionHistory.length, 1);
    assert.equal(pub.versionHistory[0].versionNumber, 1);
  });

  test('rollbackTo republishes a historical version', () => {
    const pub = new Publication({ id: 'pub1', targetType: 'lesson', targetId: 'lesson-1' });
    pub.publish(new PublicationVersion({ versionNumber: 1 }));
    pub.publish(new PublicationVersion({ versionNumber: 2 }));

    pub.rollbackTo(1);
    assert.equal(pub.currentVersion.versionNumber, 1);
    assert.equal(pub.currentVersion.status.isLive(), true);
  });

  test('rollbackTo throws for a version that was never published', () => {
    const pub = new Publication({ id: 'pub1', targetType: 'lesson', targetId: 'lesson-1' });
    pub.publish(new PublicationVersion({ versionNumber: 1 }));
    assert.throws(() => pub.rollbackTo(99), /no historical version/);
  });
});
