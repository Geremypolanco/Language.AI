export {
  getCurrentVersion,
  getNextVersionNumber,
  listVersions,
  persistLessonVersion,
  publishVersion,
  readCurrentLesson,
  resolveAssetFilePath,
  replaceAssetInVersion,
} from './AssetLibrary.js';
export { queryIndex, isDuplicateChecksum, getAllEntries, upsertLessonEntries, invalidateCache } from './libraryIndex.js';
export { libraryRoot, lessonDir, versionDir } from './paths.js';
