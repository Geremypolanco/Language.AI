/**
 * Minimal synthetic image buffers for testing magic-byte dimension parsing
 * without a real image-processing dependency or binary test fixtures
 * checked into the repo. Each one is just enough bytes for
 * imageDimensions.js's parser to read real width/height from — not a
 * decodable image.
 */

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

export function makePngBuffer(width, height) {
  const buffer = Buffer.alloc(24);
  PNG_SIGNATURE.copy(buffer, 0);
  buffer.writeUInt32BE(width, 16);
  buffer.writeUInt32BE(height, 20);
  return buffer;
}

export function makeGifBuffer(width, height) {
  const buffer = Buffer.alloc(10);
  buffer.write('GIF89a', 0, 'ascii');
  buffer.writeUInt16LE(width, 6);
  buffer.writeUInt16LE(height, 8);
  return buffer;
}

/** A real, minimal baseline JPEG SOF0 segment carrying the given dimensions. */
export function makeJpegBuffer(width, height) {
  const bytes = [
    0xff,
    0xd8, // SOI
    0xff,
    0xc0, // SOF0 marker
    0x00,
    0x11, // segment length (17)
    0x08, // precision
    (height >> 8) & 0xff,
    height & 0xff,
    (width >> 8) & 0xff,
    width & 0xff,
    0x03, // number of components
    0x01,
    0x22,
    0x00,
    0x02,
    0x11,
    0x01,
    0x03,
    0x11,
    0x01,
    0xff,
    0xd9, // EOI
  ];
  return Buffer.from(bytes);
}

export function makeSvgBuffer(width, height) {
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"></svg>`, 'utf8');
}
