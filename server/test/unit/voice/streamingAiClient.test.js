import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { streamAiReply, collectAiReply } from '../../../src/services/voice/streamingAiClient.js';

// No AI_PROVIDER_API_KEY/BASE_URL is set in the test environment, so these
// exercise the dev-mock streaming path exclusively — no real inference,
// no network call, matching "usa mocks cuando sea necesario" for AI checks.

describe('streamAiReply (dev-mock fallback, no provider configured)', () => {
  test('streams multiple text chunks referencing the last user message', async () => {
    const chunks = [];
    for await (const chunk of streamAiReply({
      systemPrompt: 'sys',
      messages: [{ role: 'user', content: 'hola mundo' }],
    })) {
      chunks.push(chunk);
    }
    assert.ok(chunks.length > 1, 'should stream more than one token');
    assert.ok(chunks.join('').includes('hola mundo'));
  });

  test('an already-aborted signal stops the stream immediately with AbortError', async () => {
    const controller = new AbortController();
    controller.abort();

    await assert.rejects(async () => {
      for await (const _chunk of streamAiReply({
        systemPrompt: 'sys',
        messages: [{ role: 'user', content: 'test' }],
        signal: controller.signal,
      })) {
        // no-op — should never receive a chunk
      }
    }, /AbortError/);
  });

  test('aborting mid-stream stops further chunks (the barge-in primitive)', async () => {
    const controller = new AbortController();
    let received = 0;

    await assert.rejects(async () => {
      for await (const _chunk of streamAiReply({
        systemPrompt: 'sys',
        messages: [{ role: 'user', content: 'a fairly long message to stream' }],
        signal: controller.signal,
      })) {
        received += 1;
        if (received === 2) controller.abort();
      }
    }, /AbortError/);

    assert.equal(received, 2); // stopped right after the abort, not at the end
  });

  test('collectAiReply joins the full stream into one string', async () => {
    const full = await collectAiReply({ systemPrompt: 'sys', messages: [{ role: 'user', content: 'test message' }] });
    assert.equal(typeof full, 'string');
    assert.ok(full.length > 0);
  });
});
