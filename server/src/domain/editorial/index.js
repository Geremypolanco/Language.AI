// Editorial domain (Content Production) — every model the publication
// pipeline produces, from raw content through to a live Publication.
// Never imported by runtime/student-facing code (see ../runtime/index.js).

export { BuildStatus, PublicationStatus } from './enums.js';

// Value objects
export { Concept } from './valueObjects/Concept.js';
export { LearningObjective, BLOOM_LEVELS } from './valueObjects/LearningObjective.js';
export { Prerequisite } from './valueObjects/Prerequisite.js';
export { CourseDependency } from './valueObjects/CourseDependency.js';
export { ValidationResult } from './valueObjects/ValidationResult.js';
export { ValidationReport } from './valueObjects/ValidationReport.js';
export { BuildLog } from './valueObjects/BuildLog.js';
export { BuilderMetrics } from './valueObjects/BuilderMetrics.js';
export { AssetMetadata } from './valueObjects/AssetMetadata.js';
export { KnowledgeNode } from './valueObjects/KnowledgeNode.js';

// Knowledge
export { Competency } from './knowledge/Competency.js';
export { KnowledgeGraph } from './knowledge/KnowledgeGraph.js';

// Pipeline
export { BuilderResult } from './pipeline/BuilderResult.js';
export { PipelineExecution } from './pipeline/PipelineExecution.js';

// Publication
export { PublicationVersion } from './publication/PublicationVersion.js';
export { BuildJob } from './publication/BuildJob.js';
export { PublicationManifest } from './publication/PublicationManifest.js';
export { PublicationIndex } from './publication/PublicationIndex.js';
export { CacheManifest } from './publication/CacheManifest.js';
export { Publication } from './publication/Publication.js';

// Packages (the authoring hierarchy)
export { AssetManifest } from './packages/AssetManifest.js';
export { ExercisePackage } from './packages/ExercisePackage.js';
export { AssessmentPackage } from './packages/AssessmentPackage.js';
export { AcademicAssetPackage } from './packages/AcademicAssetPackage.js';
export { LessonPackage } from './packages/LessonPackage.js';
export { CoursePackage } from './packages/CoursePackage.js';
export { CurriculumPackage } from './packages/CurriculumPackage.js';
export { ContentPackage } from './packages/ContentPackage.js';
