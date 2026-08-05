import fs from 'node:fs/promises';
import path from 'node:path';
import { indexFilePath } from './paths.js';
import { PublicationIndex, AssetMetadata } from '../../domain/editorial/index.js';

/**
 * Persistence for the cross-lesson reuse index — every currently published
 * asset in the library, backed by a single JSON file. The actual query/
 * dedup/upsert *logic* lives on the domain model (PublicationIndex); this
 * module is only responsible for loading that model from disk, delegating
 * to it, and saving it back — no scoring or filtering happens here anymore.
 *
 * At true "millions of assets" scale this file would load from a real
 * database/search index (Postgres + a keyword/vector index, Elasticsearch,
 * etc.) instead of a JSON file — swap the load()/save() functions below for
 * that backend without changing anything upstream, since providers and the
 * pipeline only ever call `queryIndex`/`isDuplicateChecksum`/`upsertLessonEntries`.
 */

let cache = null;

async function load() {
  if (cache) return cache;
  try {
    const raw = await fs.readFile(indexFilePath(), 'utf8');
    const parsed = JSON.parse(raw);
    cache = new PublicationIndex({ entries: parsed.map((e) => new AssetMetadata(e)) });
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
    cache = new PublicationIndex({});
  }
  return cache;
}

async function save(index) {
  cache = index;
  await fs.mkdir(path.dirname(indexFilePath()), { recursive: true }).catch(() => {});
  await fs.writeFile(indexFilePath(), JSON.stringify(index.entries, null, 2), 'utf8');
}

/** Replaces this lesson's index entries with `newEntries` — called at Publication time. */
export async function upsertLessonEntries(lessonId, newEntries) {
  const index = await load();
  const instances = newEntries.map((e) => (e instanceof AssetMetadata ? e : new AssetMetadata(e)));
  index.upsertLessonEntries(lessonId, instances);
  await save(index);
}

export async function queryIndex({ resourceType, keywords, language, limit = 5 }) {
  const index = await load();
  return index.findReusable({ resourceType, keywords, language, limit });
}

export async function isDuplicateChecksum(checksum) {
  const index = await load();
  return index.hasChecksum(checksum);
}

/** Same duplicate check, but ignores one specific asset id — used when regenerating a replacement for that exact asset. */
export async function isDuplicateChecksumExcluding(checksum, excludeAssetId) {
  const index = await load();
  return index.hasChecksumExcluding(checksum, excludeAssetId);
}

/** Every currently published asset — used by the maintenance job's broken-link sweep. */
export async function getAllEntries() {
  const index = await load();
  return [...index.entries];
}

/** Test/CLI helper to force a re-read from disk instead of the in-memory cache. */
export function invalidateCache() {
  cache = null;
}
