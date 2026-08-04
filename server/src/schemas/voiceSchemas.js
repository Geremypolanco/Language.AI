import { z } from 'zod';
import { SUPPORTED_MODES } from '../services/voice/promptTemplates.js';

export const createVoiceSessionSchema = z.object({
  mode: z.enum(SUPPORTED_MODES).default('general'),
  language: z.string().min(2).max(10).default('es'),
  personality: z.string().max(300).optional(),
});

export const voiceTurnSchema = z.object({
  sessionId: z.string().uuid(),
  message: z.string().min(1).max(4000),
  language: z.string().min(2).max(10).optional(),
});
