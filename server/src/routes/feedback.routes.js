import { Router } from 'express';
import { feedbackSchema } from '../schemas/aiSchemas.js';

export const feedbackRouter = Router();

// In-memory store as a placeholder — replace with a real persistence layer
// (Postgres, etc.) in production. Kept isolated here so swapping storage
// doesn't touch validation or routing.
const feedbackStore = [];

feedbackRouter.post('/', (req, res) => {
  const parsed = feedbackSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: 'invalid_feedback', details: parsed.error.flatten() });
  }

  feedbackStore.push({ ...parsed.data, receivedAt: new Date().toISOString() });
  res.status(201).json({ ok: true });
});
