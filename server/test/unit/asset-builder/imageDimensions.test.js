import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readImageDimensions } from '../../../src/asset-builder/validation/imageDimensions.js';
import { makePngBuffer, makeGifBuffer, makeJpegBuffer, makeSvgBuffer } from '../../fixtures/imageFixtures.js';

describe('readImageDimensions', () => {
  test('reads real width/height from a PNG IHDR chunk', () => {
    const dims = readImageDimensions(makePngBuffer(800, 600), 'png');
    assert.deepEqual(dims, { width: 800, height: 600 });
  });

  test('reads real width/height from a GIF header', () => {
    const dims = readImageDimensions(makeGifBuffer(320, 240), 'gif');
    assert.deepEqual(dims, { width: 320, height: 240 });
  });

  test('reads real width/height from a JPEG SOF0 segment', () => {
    const dims = readImageDimensions(makeJpegBuffer(1024, 768), 'jpg');
    assert.deepEqual(dims, { width: 1024, height: 768 });
  });

  test('reads width/height from SVG attributes', () => {
    const dims = readImageDimensions(makeSvgBuffer(420, 420), 'svg');
    assert.deepEqual(dims, { width: 420, height: 420 });
  });

  test('returns null for a truncated/malformed PNG instead of throwing', () => {
    const dims = readImageDimensions(Buffer.from([0x89, 0x50, 0x4e]), 'png');
    assert.equal(dims, null);
  });

  test('returns null for a buffer that does not match the claimed format', () => {
    const dims = readImageDimensions(Buffer.from('not an image'), 'png');
    assert.equal(dims, null);
  });

  test('returns null for an unsupported format rather than guessing', () => {
    const dims = readImageDimensions(makePngBuffer(100, 100), 'bmp');
    assert.equal(dims, null);
  });
});
