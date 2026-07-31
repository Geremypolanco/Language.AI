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
