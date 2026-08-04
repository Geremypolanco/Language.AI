import fs from 'node:fs/promises';
import path from 'node:path';
import { indexFilePath } from './paths.js';

/**
 * Flat, in-memory-cached index of every *currently published* asset in the
 * library, backed by a single JSON file. This is what makes cross-lesson
 * reuse (LocalLibraryProvider) and duplicate detection O(index size) local
 * lookups instead of a filesystem walk or a live search-service call — the
 * mechanism the spec asks for to keep external-call volume flat as the
 * catalog grows.
 *
 * At true "millions of assets" scale this file would become a real
 * database/search index (Postgres + a keyword/vector index, Elasticsearch,
 * etc.) — swap the read/write/query functions below for that backend
 * without changing anything upstream, since providers and the pipeline only
 * ever call `queryIndex`/`isDuplicateChecksum`/`upsertEntries`.
 */

let cache = null;

async function load() {
  if (cache) return cache;
  try {
    const raw = await fs.readFile(indexFilePath(), 'utf8');
    cache = JSON.parse(raw);
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
    cache = [];
  }
  return cache;
}

async function save(entries) {
  cache = entries;
  await fs.mkdir(path.dirname(indexFilePath()), { recursive: true }).catch(() => {});
  await fs.writeFile(indexFilePath(), JSON.stringify(entries, null, 2), 'utf8');
}

function tokenize(text) {
  return (text.toLowerCase().match(/[a-zà-öø-ÿ]+/g) || []).filter((w) => w.length > 2);
}

/** Replaces this lesson's index entries with `newEntries` — called at Publication time. */
export async function upsertLessonEntries(lessonId, newEntries) {
  const entries = await load();
  const withoutLesson = entries.filter((e) => e.lesson_id !== lessonId);
  const updated = [...withoutLesson, ...newEntries];
  await save(updated);
}

export async function queryIndex({ resourceType, keywords, language, limit = 5 }) {
  const entries = await load();
  const targetTerms = new Set(tokenize(keywords.join(' ')));

  const scored = entries
    .filter((e) => e.resource_type === resourceType && e.language === language)
    .map((e) => {
      const entryTerms = new Set(tokenize([e.title, ...(e.keywords || [])].join(' ')));
      let hits = 0;
      for (const term of targetTerms) if (entryTerms.has(term)) hits += 1;
      const score = targetTerms.size ? hits / targetTerms.size : 0;
      return { entry: e, score };
    })
    .filter((s) => s.score > 0.2)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return scored.map((s) => s.entry);
}

export async function isDuplicateChecksum(checksum) {
  if (!checksum) return false;
  const entries = await load();
  return entries.some((e) => e.checksum_sha256 === checksum);
}

/** Every currently published asset — used by the maintenance job's broken-link sweep. */
export async function getAllEntries() {
  return [...(await load())];
}

/** Test/CLI helper to force a re-read from disk instead of the in-memory cache. */
export function invalidateCache() {
  cache = null;
}
