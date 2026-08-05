import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { buildSystemPrompt } from '../../../src/services/voice/promptTemplates.js';

describe('buildSystemPrompt', () => {
  test('general mode produces a base conversational prompt', () => {
    const prompt = buildSystemPrompt({ mode: 'general', language: 'es' });
    assert.match(prompt, /voice call/i);
    assert.match(prompt, /es/);
  });

  test('language-learning mode instructs correction behavior without breaking conversational flow', () => {
    const prompt = buildSystemPrompt({ mode: 'language-learning', language: 'en' });
    assert.match(prompt, /correct/i);
    assert.match(prompt, /role-play|roleplay/i);
  });

  test('university mode instructs checking understanding and guided problem-solving', () => {
    const prompt = buildSystemPrompt({ mode: 'university', language: 'es' });
    assert.match(prompt, /tutor/i);
    assert.match(prompt, /understanding/i);
  });

  test('an unknown mode falls back to general rather than throwing', () => {
    const prompt = buildSystemPrompt({ mode: 'not-a-real-mode', language: 'es' });
    assert.match(prompt, /helpful conversational assistant/i);
  });

  test('includes a personality instruction only when one is provided', () => {
    const withPersonality = buildSystemPrompt({ mode: 'general', language: 'es', personality: 'cheerful and concise' });
    const withoutPersonality = buildSystemPrompt({ mode: 'general', language: 'es' });
    assert.match(withPersonality, /cheerful and concise/);
    assert.ok(!withoutPersonality.includes('Personality/tone'));
  });

  test('every generated prompt instructs spoken-style output (no markdown, short sentences)', () => {
    for (const mode of ['general', 'language-learning', 'university']) {
      const prompt = buildSystemPrompt({ mode, language: 'es' });
      assert.match(prompt, /no markdown/i);
    }
  });
});
