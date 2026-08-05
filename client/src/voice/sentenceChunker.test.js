import { describe, test, expect } from 'vitest';
import { SentenceChunker } from './sentenceChunker.js';

describe('SentenceChunker', () => {
  test('returns null while a sentence is incomplete', () => {
    const chunker = new SentenceChunker();
    expect(chunker.push('Hello')).toBeNull();
    expect(chunker.push(' there')).toBeNull();
  });

  test('flushes a completed sentence and resets the buffer', () => {
    const chunker = new SentenceChunker();
    chunker.push('Hello there');
    const sentence = chunker.push('.');
    expect(sentence).toBe('Hello there.');
    expect(chunker.push(' Next')).toBeNull();
  });

  test('recognizes !, ?, and ellipsis as sentence terminators', () => {
    const chunker = new SentenceChunker();
    expect(chunker.push('Really?')).toBe('Really?');

    const chunker2 = new SentenceChunker();
    expect(chunker2.push('Wow!')).toBe('Wow!');

    const chunker3 = new SentenceChunker();
    expect(chunker3.push('Well…')).toBe('Well…');
  });

  test('handles multiple sentences arriving as separate tokens', () => {
    const chunker = new SentenceChunker();
    expect(chunker.push('One.')).toBe('One.');
    expect(chunker.push(' Two.')).toBe('Two.');
  });

  test('flush() returns and clears any remaining partial sentence', () => {
    const chunker = new SentenceChunker();
    chunker.push('trailing partial');
    expect(chunker.flush()).toBe('trailing partial');
    expect(chunker.flush()).toBeNull();
  });

  test('flush() returns null when the buffer is empty', () => {
    const chunker = new SentenceChunker();
    expect(chunker.flush()).toBeNull();
  });
});
