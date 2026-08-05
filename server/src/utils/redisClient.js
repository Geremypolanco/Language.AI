import { createClient } from 'redis';
import { env } from '../config/env.js';

let client;
let connecting;

/**
 * Lazily creates a single shared Redis connection. Rate-limit state must live
 * in Redis (not in-process memory) so limits hold correctly across multiple
 * server instances behind a load balancer.
 */
export async function getRedisClient() {
  if (client) return client;
  if (!connecting) {
    client = createClient({ url: env.redisUrl });
    client.on('error', (err) => console.error('[redis] connection error', err));
    connecting = client.connect().then(() => client);
  }
  await connecting;
  return client;
}

/**
 * Closes the shared connection. The client otherwise lives for the process
 * lifetime (by design, for connection reuse) — callers that boot their own
 * short-lived process around getRedisClient() (e.g. the test suite spinning
 * up a server per file) must call this or the open socket keeps the event
 * loop alive and the process never exits.
 */
export async function closeRedisClient() {
  if (!client) return;
  const closing = client;
  client = undefined;
  connecting = undefined;
  await closing.quit();
}
