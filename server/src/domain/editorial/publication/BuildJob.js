import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { BuildStatus } from '../enums.js';

const TARGET_TYPES = ['content', 'curriculum', 'course', 'lesson', 'exercise', 'assessment', 'academic-asset'];

/** One request to build/rebuild a package — the unit the pipeline actually executes. */
export class BuildJob extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    targetType: z.enum(TARGET_TYPES),
    targetId: z.string().min(1),
    requestedAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
    requestedBy: z.string().optional(),
    status: z.instanceof(BuildStatus).default(() => new BuildStatus(BuildStatus.PENDING)),
    startedAt: z.string().datetime().optional(),
    finishedAt: z.string().datetime().optional(),
    errorMessage: z.string().optional(),
  });

  start() {
    return new BuildJob({
      ...this,
      status: this.status.transitionTo(BuildStatus.RUNNING),
      startedAt: new Date().toISOString(),
    });
  }

  succeed() {
    return new BuildJob({
      ...this,
      status: this.status.transitionTo(BuildStatus.SUCCEEDED),
      finishedAt: new Date().toISOString(),
    });
  }

  fail(errorMessage) {
    return new BuildJob({
      ...this,
      status: this.status.transitionTo(BuildStatus.FAILED),
      finishedAt: new Date().toISOString(),
      errorMessage,
    });
  }

  cancel() {
    return new BuildJob({
      ...this,
      status: this.status.transitionTo(BuildStatus.CANCELLED),
      finishedAt: new Date().toISOString(),
    });
  }

  durationMs() {
    if (!this.startedAt || !this.finishedAt) return null;
    return new Date(this.finishedAt).getTime() - new Date(this.startedAt).getTime();
  }
}
