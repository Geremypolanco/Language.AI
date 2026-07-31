import { createApp } from './app.js';
import { env } from './config/env.js';

const app = createApp();

app.listen(env.port, () => {
  console.log(`[server] Language.AI API listening on port ${env.port} (${env.nodeEnv})`);
});
