import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { createAssetValidator } from '../../../src/asset-builder/validation/AssetValidator.js';
import { makePngBuffer } from '../../fixtures/imageFixtures.js';

const analysis = {
  mainTopic: 'Ecuaciones lineales',
  keywords: ['ecuacion', 'lineal', 'algebra'],
};
const planItem = { resourceType: 'diagram', searchTerms: ['ecuacion', 'lineal'] };

function baseCandidate(overrides = {}) {
  return {
    provider: 'diagram-generator',
    resourceType: 'diagram',
    format: 'svg',
    title: 'Ecuaciones lineales — diagram',
    license: 'proprietary-generated',
    keywords: ['ecuacion', 'lineal'],
    bytes: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"></svg>', 'utf8'),
    ...overrides,
  };
}

function validatorFor({ duplicates = new Set() } = {}) {
  return createAssetValidator({ isDuplicateChecksum: async (checksum) => duplicates.has(checksum) });
}

describe('createAssetValidator', () => {
  test('accepts a well-formed, relevant, licensed candidate', async () => {
    const validate = validatorFor();
    const result = await validate(baseCandidate(), planItem, analysis);
    assert.equal(result.report.isValid(), true);
    assert.ok(result.scores.relevance > 0);
    assert.ok(result.checksum);
  });

  test('rejects a format not allowed for the resourceType', async () => {
    const validate = validatorFor();
    const result = await validate(baseCandidate({ format: 'mp3' }), planItem, analysis);
    assert.equal(result.report.isValid(), false);
    assert.ok(result.report.blockingFailures().some((r) => r.check === 'format'));
  });

  test('rejects a license not on the allow-list', async () => {
    const validate = validatorFor();
    const result = await validate(baseCandidate({ license: 'GPL-3.0' }), planItem, analysis);
    assert.equal(result.report.isValid(), false);
    assert.ok(result.report.blockingFailures().some((r) => r.check === 'license-allowlist'));
  });

  test('rejects a candidate with neither bytes nor a reusable file path', async () => {
    const validate = validatorFor();
    const result = await validate(baseCandidate({ bytes: undefined }), planItem, analysis);
    assert.equal(result.report.isValid(), false);
    assert.ok(result.report.blockingFailures().some((r) => r.check === 'content-present'));
  });

  test('a local-library reuse candidate (filePath, no bytes) is accepted without a content-present failure', async () => {
    const validate = validatorFor();
    const result = await validate(
      baseCandidate({ bytes: undefined, provider: 'local-library', filePath: 'x/y/z.svg' }),
      planItem,
      analysis
    );
    assert.equal(result.report.results.find((r) => r.check === 'content-present').passed, true);
  });

  test('rejects a duplicate of already-persisted content for a non-reuse provider', async () => {
    const candidate = baseCandidate({ provider: 'wikimedia-commons' });
    const crypto = await import('node:crypto');
    const checksum = crypto.createHash('sha256').update(candidate.bytes).digest('hex');
    const validate = validatorFor({ duplicates: new Set([checksum]) });
    const result = await validate(candidate, planItem, analysis);
    assert.equal(result.report.isValid(), false);
    assert.ok(result.report.blockingFailures().some((r) => r.check === 'duplicate'));
  });

  test('local-library candidates are exempt from the duplicate check (they ARE the reuse)', async () => {
    const candidate = baseCandidate({ provider: 'local-library' });
    const crypto = await import('node:crypto');
    const checksum = crypto.createHash('sha256').update(candidate.bytes).digest('hex');
    // Even though this exact checksum is "already known", a local-library
    // candidate is the canonical copy being reused, not a fresh duplicate.
    const validate = validatorFor({ duplicates: new Set([checksum]) });
    const result = await validate(candidate, planItem, analysis);
    assert.equal(result.report.results.find((r) => r.check === 'duplicate').passed, true);
  });

  test('rejects a raster image below the minimum useful resolution', async () => {
    const validate = validatorFor();
    const candidate = {
      provider: 'wikimedia-commons',
      resourceType: 'image',
      format: 'png',
      title: 'thumbnail',
      license: 'CC-BY',
      keywords: ['ecuacion'],
      bytes: makePngBuffer(50, 50),
    };
    const result = await validate(candidate, { resourceType: 'image', searchTerms: ['ecuacion'] }, analysis);
    assert.equal(result.report.isValid(), false);
    assert.ok(result.report.blockingFailures().some((r) => r.check === 'resolution'));
  });

  test('rejects a candidate with no keyword overlap with the target (low relevance)', async () => {
    const validate = validatorFor();
    const candidate = baseCandidate({ keywords: ['completamente', 'no-relacionado', 'aleatorio'], title: 'unrelated' });
    const result = await validate(candidate, planItem, analysis);
    assert.equal(result.report.isValid(), false);
    assert.ok(result.report.blockingFailures().some((r) => r.check === 'relevance'));
  });

  test('scores are always within the 0..1 bounds', async () => {
    const validate = validatorFor();
    const result = await validate(baseCandidate(), planItem, analysis);
    for (const score of Object.values(result.scores)) {
      assert.ok(score >= 0 && score <= 1);
    }
  });
});
