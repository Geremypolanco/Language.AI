import { describe, test, expect } from 'vitest';
import { MemoryManager } from './MemoryManager.js';

describe('MemoryManager', () => {
  test('add() appends entries with a role, text, and timestamp', () => {
    const memory = new MemoryManager();
    memory.add('user', 'hello');
    const [entry] = memory.getAll();
    expect(entry.role).toBe('user');
    expect(entry.text).toBe('hello');
    expect(typeof entry.ts).toBe('number');
  });

  test('getAll() returns entries in insertion order and is a defensive copy', () => {
    const memory = new MemoryManager();
    memory.add('user', 'one');
    memory.add('assistant', 'two');
    const all = memory.getAll();
    expect(all.map((e) => e.text)).toEqual(['one', 'two']);
    all.push({ role: 'user', text: 'mutated', ts: 0 });
    expect(memory.getAll()).toHaveLength(2);
  });

  test('getLastByRole() finds the most recent entry for a role', () => {
    const memory = new MemoryManager();
    memory.add('user', 'first');
    memory.add('assistant', 'reply one');
    memory.add('user', 'second');
    memory.add('assistant', 'reply two');
    expect(memory.getLastByRole('user').text).toBe('second');
    expect(memory.getLastByRole('assistant').text).toBe('reply two');
  });

  test('getLastByRole() returns null when the role never appeared', () => {
    const memory = new MemoryManager();
    memory.add('user', 'hi');
    expect(memory.getLastByRole('assistant')).toBeNull();
  });

  test('evicts the oldest entry once maxEntries is exceeded', () => {
    const memory = new MemoryManager({ maxEntries: 3 });
    memory.add('user', 'a');
    memory.add('user', 'b');
    memory.add('user', 'c');
    memory.add('user', 'd');
    expect(memory.getAll().map((e) => e.text)).toEqual(['b', 'c', 'd']);
  });

  test('clear() empties the transcript', () => {
    const memory = new MemoryManager();
    memory.add('user', 'hi');
    memory.clear();
    expect(memory.getAll()).toEqual([]);
  });
});
