import { z } from 'zod';

/**
 * Contract the Academic Asset Builder expects from whatever upstream
 * builder produced the lesson (Content/Curriculum/Course/Lesson/Exercise/
 * Assessment Builder — out of scope here). Analysis is required to read the
 * *full* content, not the title, so `sections` carries the actual body.
 */
export const lessonContentSchema = z.object({
  lessonId: z.string().min(1),
  courseId: z.string().min(1),
  discipline: z.string().min(1), // e.g. 'mathematics', 'biology', 'history', 'languages'
  language: z.string().min(2).max(10).default('es'),
  level: z.enum(['beginner', 'intermediate', 'advanced']).default('beginner'),
  title: z.string().min(1),
  objectives: z.array(z.string()).default([]),
  sections: z
    .array(
      z.object({
        heading: z.string().min(1),
        body: z.string().min(1),
      })
    )
    .min(1),
});

export const RESOURCE_TYPES = Object.freeze([
  'image',
  'gallery',
  'diagram',
  'illustration',
  'video',
  'audio',
  'flashcards',
  'glossary',
  'table',
  'formula',
  'example',
  'interactive',
]);

export const LICENSE_ALLOWLIST = Object.freeze([
  'CC0',
  'CC-BY',
  'CC-BY-SA',
  'public-domain',
  'proprietary-generated', // content we generated ourselves (diagrams, audio, AI images) — no third-party license needed
]);

/**
 * Every persisted asset carries this metadata — enforced at persistence
 * time so nothing enters the library without it.
 */
export const assetMetadataSchema = z.object({
  id: z.string().uuid(),
  lesson_id: z.string().min(1),
  course_id: z.string().min(1),
  language: z.string().min(2).max(10),
  resource_type: z.enum(RESOURCE_TYPES),
  provider: z.string().min(1),
  version: z.number().int().positive(),
  license: z.enum(LICENSE_ALLOWLIST),
  keywords: z.array(z.string()).default([]),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
  quality_score: z.number().min(0).max(1),
  educational_score: z.number().min(0).max(1),
  // Practical fields validation/serving need, additive to the required set above.
  format: z.string().min(1),
  file_path: z.string().min(1), // path relative to the library root (ASSET_LIBRARY_ROOT)
  source_url: z.string().url().optional(),
  width: z.number().int().positive().optional(),
  height: z.number().int().positive().optional(),
  duration_seconds: z.number().positive().optional(),
  checksum_sha256: z.string().length(64).optional(),
  relevance_score: z.number().min(0).max(1),
});

export const assetPlanItemSchema = z.object({
  resourceType: z.enum(RESOURCE_TYPES),
  quantity: z.number().int().positive(),
  priority: z.enum(['required', 'recommended', 'optional']),
  preferredFormat: z.string().optional(), // e.g. 'mermaid', 'svg', 'photo'
  rationale: z.string(),
  searchTerms: z.array(z.string()).default([]),
});
