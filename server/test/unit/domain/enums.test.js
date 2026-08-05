import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { BuildStatus, PublicationStatus } from '../../../src/domain/editorial/enums.js';

describe('BuildStatus', () => {
  test('defaults to pending', () => {
    assert.equal(new BuildStatus().value, 'pending');
  });

  test('allows pending -> running -> succeeded', () => {
    const s = new BuildStatus('pending').transitionTo('running').transitionTo('succeeded');
    assert.equal(s.value, 'succeeded');
    assert.equal(s.isTerminal(), true);
  });

  test('allows a retry from failed back to pending', () => {
    const s = new BuildStatus('failed');
    assert.equal(s.canTransitionTo('pending'), true);
  });

  test('rejects an illegal transition (succeeded -> running)', () => {
    const s = new BuildStatus('succeeded');
    assert.throws(() => s.transitionTo('running'), /Cannot transition/);
  });

  test('rejects an unknown status value', () => {
    assert.throws(() => new BuildStatus('bogus'), /Invalid BuildStatus/);
  });
});

describe('PublicationStatus', () => {
  test('defaults to draft and can publish', () => {
    const s = new PublicationStatus().transitionTo('published');
    assert.equal(s.isLive(), true);
  });

  test('deprecated can be republished (rollback-then-republish)', () => {
    const s = new PublicationStatus('deprecated');
    assert.equal(s.canTransitionTo('published'), true);
  });

  test('retracted is terminal', () => {
    const s = new PublicationStatus('retracted');
    assert.equal(s.canTransitionTo('published'), false);
    assert.equal(s.canTransitionTo('deprecated'), false);
  });

  test('draft cannot go straight to retracted', () => {
    const s = new PublicationStatus('draft');
    assert.equal(s.canTransitionTo('retracted'), false);
  });
});
