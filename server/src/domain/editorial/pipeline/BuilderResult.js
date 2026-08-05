import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { BuilderMetrics } from '../valueObjects/BuilderMetrics.js';
import { BuildLog } from '../valueObjects/BuildLog.js';

/**
 * The outcome of one builder stage's run (e.g. the Academic Asset Builder
 * building one lesson's assets). Formalizes what buildLessonAssets()
 * previously returned as a bare `{lessonId, version, published, ...}`
 * object.
 */
export class BuilderResult extends DomainEntity {
  static schema = z.object({
    success: z.boolean(),
    targetId: z.string().min(1),
    metrics: z.instanceof(BuilderMetrics),
    logs: z.array(z.instanceof(BuildLog)).default([]),
    errors: z.array(z.string()).default([]),
  });

  addLog(log) {
    this.logs.push(log);
    return this;
  }

  hasErrors() {
    return this.errors.length > 0 || this.logs.some((l) => l.isError());
  }
}
