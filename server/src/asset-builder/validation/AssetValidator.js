import crypto from 'node:crypto';
import { LICENSE_ALLOWLIST } from '../schemas.js';
import { readImageDimensions } from './imageDimensions.js';
import { ValidationResult, ValidationReport } from '../../domain/editorial/index.js';

const FORMATS_BY_TYPE = {
  image: ['jpg', 'jpeg', 'png', 'webp', 'gif'],
  gallery: ['jpg', 'jpeg', 'png', 'webp'],
  illustration: ['svg', 'png', 'jpg', 'jpeg', 'mermaid'],
  diagram: ['svg', 'mermaid', 'html'],
  video: ['mp4', 'webm'],
  audio: ['mp3', 'wav', 'ogg', 'm4a'],
  flashcards: ['json'],
  glossary: ['json'],
  table: ['json', 'html'],
  formula: ['json', 'svg', 'latex'],
  example: ['json', 'html'],
  interactive: ['html', 'json'],
};

const RASTER_FORMATS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif']);
const MIN_RASTER_DIMENSION = 200; // reject thumbnails too small to be useful in a lesson

const LICENSE_BONUS = {
  CC0: 1,
  'public-domain': 1,
  'proprietary-generated': 1,
  'CC-BY': 0.9,
  'CC-BY-SA': 0.85,
};

function tokenize(text) {
  return (text.toLowerCase().match(/[a-zà-öø-ÿ]+/g) || []).filter((w) => w.length > 2);
}

function computeRelevance(candidate, planItem, analysis) {
  const targetTerms = new Set(
    tokenize(
      [...(planItem.searchTerms.length ? planItem.searchTerms : analysis.keywords), analysis.mainTopic].join(' ')
    )
  );
  if (targetTerms.size === 0) return 0.5; // nothing to compare against — neutral score, don't punish

  const candidateTerms = new Set(tokenize([candidate.title, ...(candidate.keywords || [])].join(' ')));
  let hits = 0;
  for (const term of targetTerms) if (candidateTerms.has(term)) hits += 1;
  return Math.min(1, hits / targetTerms.size);
}

function computeQuality(candidate, dimensions) {
  let score = ['local-library', 'diagram-generator', 'text-extractor'].includes(candidate.provider) ? 0.85 : 0.6;

  if (dimensions && RASTER_FORMATS.has(candidate.format)) {
    if (dimensions.width >= 1200) score += 0.15;
    else if (dimensions.width >= 600) score += 0.08;
  }
  if (candidate.format === 'svg' || candidate.format === 'mermaid') score += 0.05; // vector/scale-free bonus

  return Math.max(0, Math.min(1, score));
}

/**
 * Runs every acceptance check the spec requires before a candidate may be
 * persisted: format, resolution, license, relevance, duplicate, and a
 * composite quality/educational score. Each check produces a typed
 * ValidationResult (not a string pushed onto an array); they're aggregated
 * into a ValidationReport, and a single blocking (error-severity) failure
 * rejects the candidate outright — the priority chain then simply tries
 * the next one.
 *
 * `isDuplicateChecksum(sha256) => boolean` is injected so the validator
 * doesn't depend on the filesystem/persistence layer directly.
 */
export function createAssetValidator({ isDuplicateChecksum, minRelevance = 0.12, minQuality = 0.35 }) {
  return async function validate(candidate, planItem, analysis) {
    const results = [];
    const check = (id, passed, message, severity = 'error') =>
      results.push(new ValidationResult({ check: id, passed, message, severity }));

    const allowedFormats = FORMATS_BY_TYPE[candidate.resourceType] || [];
    check(
      'format',
      allowedFormats.includes(candidate.format),
      `format "${candidate.format}" not allowed for resourceType "${candidate.resourceType}"`
    );

    // Local-library reuse candidates carry a filePath instead of bytes — that's fine, not a failure.
    check(
      'content-present',
      Boolean((candidate.bytes && candidate.bytes.length > 0) || candidate.filePath),
      'candidate has no content (empty bytes) and no reusable file path'
    );

    check(
      'license-allowlist',
      LICENSE_ALLOWLIST.includes(candidate.license),
      `license "${candidate.license}" is not on the allow-list`
    );

    let dimensions = null;
    if (candidate.bytes && RASTER_FORMATS.has(candidate.format)) {
      dimensions = readImageDimensions(candidate.bytes, candidate.format);
      if (dimensions) {
        check(
          'resolution',
          dimensions.width >= MIN_RASTER_DIMENSION && dimensions.height >= MIN_RASTER_DIMENSION,
          `resolution ${dimensions.width}x${dimensions.height} below minimum ${MIN_RASTER_DIMENSION}px`
        );
      }
    } else if (candidate.bytes && candidate.format === 'svg') {
      dimensions = readImageDimensions(candidate.bytes, candidate.format);
    }

    let checksum;
    if (candidate.bytes) {
      checksum = crypto.createHash('sha256').update(candidate.bytes).digest('hex');
      const isDuplicate = candidate.provider !== 'local-library' && (await isDuplicateChecksum(checksum));
      check('duplicate', !isDuplicate, 'duplicate of an already-persisted asset (identical content)');
    }

    const relevanceScore = computeRelevance(candidate, planItem, analysis);
    check(
      'relevance',
      relevanceScore >= minRelevance,
      `relevance score ${relevanceScore.toFixed(2)} below minimum ${minRelevance}`
    );

    const qualityScore = computeQuality(candidate, dimensions);
    check(
      'quality',
      qualityScore >= minQuality,
      `quality score ${qualityScore.toFixed(2)} below minimum ${minQuality}`
    );

    const licenseBonus = LICENSE_BONUS[candidate.license] ?? 0.7;
    const educationalScore = Math.max(0, Math.min(1, 0.5 * relevanceScore + 0.3 * qualityScore + 0.2 * licenseBonus));

    const report = new ValidationReport({
      targetId: candidate.title || candidate.resourceType,
      targetType: candidate.resourceType,
      results,
    });

    return {
      report,
      scores: { relevance: relevanceScore, quality: qualityScore, educational: educationalScore },
      dimensions,
      checksum,
    };
  };
}
