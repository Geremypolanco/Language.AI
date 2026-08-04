import path from 'node:path';
import { env } from '../../config/env.js';

export const ASSET_SUBFOLDERS = ['images', 'videos', 'audio', 'diagrams', 'illustrations'];

const COMBINING_DIACRITICS_RE = new RegExp('[\\u0300-\\u036f]', 'g');

export function slugify(text) {
  return text
    .toString()
    .toLowerCase()
    .normalize('NFD')
    .replace(COMBINING_DIACRITICS_RE, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

export function libraryRoot() {
  return path.resolve(process.cwd(), env.assetLibraryRoot);
}

export function lessonDir(discipline, courseId, lessonId) {
  return path.join(libraryRoot(), slugify(discipline), slugify(courseId), slugify(lessonId));
}

export function versionDir(discipline, courseId, lessonId, version) {
  return path.join(lessonDir(discipline, courseId, lessonId), 'versions', `v${version}`);
}

export function currentPointerPath(discipline, courseId, lessonId) {
  return path.join(lessonDir(discipline, courseId, lessonId), 'current.json');
}

export function indexFilePath() {
  return path.join(libraryRoot(), '_index.json');
}

function extensionForAsset(format) {
  if (format === 'mermaid') return 'mmd';
  return format;
}

export function assetSubfolderFor(resourceType) {
  const map = {
    image: 'images',
    gallery: 'images',
    video: 'videos',
    audio: 'audio',
    diagram: 'diagrams',
    illustration: 'illustrations',
  };
  // Non-media resource types (flashcards, glossary, table, formula, example, interactive)
  // are stored as JSON/HTML directly under assets/ — they aren't binary media.
  return map[resourceType] || '.';
}

export function assetFileName(assetId, format) {
  return `${assetId}.${extensionForAsset(format)}`;
}
