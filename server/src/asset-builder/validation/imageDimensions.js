/**
 * Reads pixel dimensions straight from format magic bytes/headers — no
 * image-processing dependency needed just to validate resolution.
 * Returns null (not a guess) for formats/variants it can't confidently
 * parse; the validator treats that as "resolution unknown" rather than a
 * hard failure.
 */

function readPng(buffer) {
  const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  if (buffer.length < 24 || !buffer.subarray(0, 8).equals(PNG_SIGNATURE)) return null;
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

function readGif(buffer) {
  if (buffer.length < 10) return null;
  const header = buffer.toString('ascii', 0, 6);
  if (header !== 'GIF87a' && header !== 'GIF89a') return null;
  return { width: buffer.readUInt16LE(6), height: buffer.readUInt16LE(8) };
}

function readJpeg(buffer) {
  if (buffer.length < 4 || buffer[0] !== 0xff || buffer[1] !== 0xd8) return null;
  let offset = 2;
  while (offset < buffer.length - 9) {
    if (buffer[offset] !== 0xff) {
      offset += 1;
      continue;
    }
    const marker = buffer[offset + 1];
    const isStartOfFrame = marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;
    if (isStartOfFrame) {
      return { height: buffer.readUInt16BE(offset + 5), width: buffer.readUInt16BE(offset + 7) };
    }
    const segmentLength = buffer.readUInt16BE(offset + 2);
    offset += 2 + segmentLength;
  }
  return null;
}

function readWebp(buffer) {
  if (buffer.length < 30 || buffer.toString('ascii', 0, 4) !== 'RIFF' || buffer.toString('ascii', 8, 12) !== 'WEBP') {
    return null;
  }
  const chunkFormat = buffer.toString('ascii', 12, 16);
  if (chunkFormat === 'VP8X') {
    // 24-bit little-endian width-1 / height-1 at offsets 24 and 27.
    const width = 1 + (buffer[24] | (buffer[25] << 8) | (buffer[26] << 16));
    const height = 1 + (buffer[27] | (buffer[28] << 8) | (buffer[29] << 16));
    return { width, height };
  }
  if (chunkFormat === 'VP8 ') {
    // Lossy bitstream: 14-bit width/height follow a 3-byte frame tag + sync code at offset 26.
    const width = buffer.readUInt16LE(26) & 0x3fff;
    const height = buffer.readUInt16LE(28) & 0x3fff;
    return { width, height };
  }
  return null; // VP8L (lossless) bit-packing not worth implementing without a real need for it
}

function readSvg(buffer) {
  const text = buffer.toString('utf8', 0, Math.min(buffer.length, 2000));
  const widthMatch = text.match(/width="(\d+(\.\d+)?)"/);
  const heightMatch = text.match(/height="(\d+(\.\d+)?)"/);
  if (widthMatch && heightMatch) {
    return { width: Math.round(Number(widthMatch[1])), height: Math.round(Number(heightMatch[1])) };
  }
  const viewBoxMatch = text.match(/viewBox="[\d.\s-]*?\s([\d.]+)\s+([\d.]+)"/);
  if (viewBoxMatch) return { width: Math.round(Number(viewBoxMatch[1])), height: Math.round(Number(viewBoxMatch[2])) };
  return null;
}

export function readImageDimensions(buffer, format) {
  try {
    switch (format) {
      case 'png':
        return readPng(buffer);
      case 'jpg':
      case 'jpeg':
        return readJpeg(buffer);
      case 'gif':
        return readGif(buffer);
      case 'webp':
        return readWebp(buffer);
      case 'svg':
        return readSvg(buffer);
      default:
        return null;
    }
  } catch {
    return null; // malformed/truncated file — treat as unknown, not a crash
  }
}
