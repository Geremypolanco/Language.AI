import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { BuildLog } from '../valueObjects/BuildLog.js';
import { BuilderResult } from './BuilderResult.js';

/** One end-to-end run of the pipeline (Analyzer -> Planner -> Providers -> Validation -> Persistence -> Publication) for a single target. */
export class PipelineExecution extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    targetId: z.string().min(1),
    startedAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
    finishedAt: z.string().datetime().optional(),
    logs: z.array(z.instanceof(BuildLog)).default([]),
    stageResults: z.array(z.instanceof(BuilderResult)).default([]),
  });

  addLog(log) {
    this.logs.push(log);
    return this;
  }

  addStageResult(result) {
    this.stageResults.push(result);
    return this;
  }

  finish() {
    this.finishedAt = new Date().toISOString();
    return this;
  }

  isComplete() {
    return Boolean(this.finishedAt);
  }

  durationMs() {
    if (!this.finishedAt) return null;
    return new Date(this.finishedAt).getTime() - new Date(this.startedAt).getTime();
  }

  failedStages() {
    return this.stageResults.filter((r) => !r.success);
  }

  succeeded() {
    return this.isComplete() && this.failedStages().length === 0;
  }
}
