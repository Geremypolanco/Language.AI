import { z } from 'zod';

/**
 * Inbound chat request. Length caps and stripped control characters shrink
 * the prompt-injection and payload-flood surface before the message ever
 * reaches the sanitizer/guardrail layer.
 */
export const aiChatRequestSchema = z.object({
  message: z.string().min(1, 'message cannot be empty').max(4000, 'message exceeds maximum length of 4000 characters'),
  conversationId: z.string().uuid().optional(),
});

/**
 * Structured, schema-validated shape every AI response must conform to
 * before it is forwarded to the client. Rejecting anything that doesn't
 * parse prevents malformed/unstructured model output (a common vector for
 * both hallucination amplification and downstream injection) from reaching
 * the browser.
 */
export const aiChatResponseSchema = z.object({
  reply: z.string().max(8000),
  confidence: z.enum(['low', 'medium', 'high']).default('medium'),
  citations: z.array(z.string().url()).max(10).default([]),
  flagged: z.boolean().default(false),
});

export const feedbackSchema = z
  .object({
    conversationId: z.string().uuid().optional(),
    messageId: z.string().min(1).max(200),
    rating: z.enum(['up', 'down']).optional(),
    reportReason: z.string().max(1000).optional(),
  })
  .refine((data) => data.rating || data.reportReason, {
    message: 'Either rating or reportReason must be provided',
  });
