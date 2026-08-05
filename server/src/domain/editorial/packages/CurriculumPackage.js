import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { CoursePackage } from './CoursePackage.js';
import { Competency } from '../knowledge/Competency.js';
import { Prerequisite } from '../valueObjects/Prerequisite.js';
import { KnowledgeGraph } from '../knowledge/KnowledgeGraph.js';
import { KnowledgeNode } from '../valueObjects/KnowledgeNode.js';

/**
 * A curriculum. Per the domain spec this must know its competencies,
 * prerequisites, and coverage — `coverage()` and
 * `hasCyclicCourseDependencies()` are real computed relationships across
 * the whole package tree, not fields someone has to keep in sync by hand.
 */
export class CurriculumPackage extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    title: z.string().min(1),
    discipline: z.string().min(1),
    courses: z.array(z.instanceof(CoursePackage)).default([]),
    competencies: z.array(z.instanceof(Competency)).default([]),
    prerequisites: z.array(z.instanceof(Prerequisite)).default([]),
  });

  allLearningObjectives() {
    return this.courses.flatMap((c) => c.lessons.flatMap((l) => l.learningObjectives));
  }

  /** Fraction of declared competencies actually satisfied by some lesson's learning objectives. */
  coverage() {
    if (this.competencies.length === 0) return 1;
    const objectives = this.allLearningObjectives();
    const satisfied = this.competencies.filter((c) => c.isSatisfiedByObjectives(objectives));
    return satisfied.length / this.competencies.length;
  }

  uncoveredCompetencies() {
    const objectives = this.allLearningObjectives();
    return this.competencies.filter((c) => !c.isSatisfiedByObjectives(objectives));
  }

  buildCourseDependencyGraph() {
    const allDeps = this.courses.flatMap((c) => c.dependencies);
    const nodes = this.courses.map(
      (c) =>
        new KnowledgeNode({
          id: c.id,
          type: 'course',
          label: c.title,
          relatedNodeIds: allDeps.filter((d) => d.courseId === c.id).map((d) => d.dependsOnCourseId),
        })
    );
    return new KnowledgeGraph({ nodes });
  }

  hasCyclicCourseDependencies() {
    return this.buildCourseDependencyGraph().hasCycle();
  }

  /** Course publication order such that every prerequisite is published before what depends on it. Throws if dependencies are cyclic. */
  coursePublicationOrder() {
    return this.buildCourseDependencyGraph()
      .topologicalOrder()
      .map((node) => this.courses.find((c) => c.id === node.id));
  }

  isReadyForPublication() {
    return this.courses.length > 0 && !this.hasCyclicCourseDependencies() && this.courses.every((c) => c.isReadyForPublication());
  }
}
