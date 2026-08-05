import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { z } from 'zod';
import { DomainEntity } from '../../../src/domain/shared/DomainEntity.js';

class Widget extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    count: z.number().int().min(0).default(0),
  });

  describe() {
    return `Widget(${this.id}, ${this.count})`;
  }
}

class NoSchema extends DomainEntity {}

describe('DomainEntity', () => {
  test('validates and assigns fields on construction', () => {
    const w = new Widget({ id: 'w1', count: 3 });
    assert.equal(w.id, 'w1');
    assert.equal(w.count, 3);
  });

  test('applies Zod defaults for omitted fields', () => {
    const w = new Widget({ id: 'w1' });
    assert.equal(w.count, 0);
  });

  test('rejects invalid data with a ZodError', () => {
    assert.throws(
      () => new Widget({ id: '', count: -1 }),
      (err) => err.name === 'ZodError'
    );
  });

  test('rejects missing required fields', () => {
    assert.throws(() => new Widget({}));
  });

  test('subclass methods work alongside validated fields (not anemic)', () => {
    const w = new Widget({ id: 'w1', count: 5 });
    assert.equal(w.describe(), 'Widget(w1, 5)');
  });

  test('toJSON returns a plain serializable object', () => {
    const w = new Widget({ id: 'w1', count: 2 });
    const json = JSON.parse(JSON.stringify(w));
    assert.deepEqual(json, { id: 'w1', count: 2 });
  });

  test('a subclass without a static schema throws immediately', () => {
    assert.throws(() => new NoSchema({}), /must declare a static "schema"/);
  });
});
