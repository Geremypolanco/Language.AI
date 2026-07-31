import { z } from 'zod';

export const consentPreferencesSchema = z.object({
  analytics: z.boolean().default(false),
  marketing: z.boolean().default(false),
});
