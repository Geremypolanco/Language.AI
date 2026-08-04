export { AssetProvider } from './AssetProvider.js';
export { LocalLibraryProvider } from './LocalLibraryProvider.js';
export { DiagramProvider } from './DiagramProvider.js';
export { TextResourceProvider } from './TextResourceProvider.js';
export { OpenEducationalResourcesProvider } from './OpenEducationalResourcesProvider.js';
export { WikimediaCommonsProvider } from './WikimediaCommonsProvider.js';
export { GoogleImagesProvider } from './GoogleImagesProvider.js';
export { AIGenerationProvider } from './AIGenerationProvider.js';
export { AudioProvider } from './AudioProvider.js';
export { ResourcePriorityChain } from './ResourcePriorityChain.js';

import { LocalLibraryProvider } from './LocalLibraryProvider.js';
import { DiagramProvider } from './DiagramProvider.js';
import { TextResourceProvider } from './TextResourceProvider.js';
import { OpenEducationalResourcesProvider } from './OpenEducationalResourcesProvider.js';
import { WikimediaCommonsProvider } from './WikimediaCommonsProvider.js';
import { GoogleImagesProvider } from './GoogleImagesProvider.js';
import { AIGenerationProvider } from './AIGenerationProvider.js';
import { AudioProvider } from './AudioProvider.js';
import { ResourcePriorityChain } from './ResourcePriorityChain.js';

/**
 * Assembles the priority chain in the exact order the spec requires: local
 * library -> persisted repository -> open educational resources -> Wikimedia
 * Commons -> Google Images -> AI generation. AudioProvider is separate since
 * no other provider here handles audio, but it's included so 'audio' plan
 * items resolve through the same chain machinery.
 *
 * `queryIndex` wires LocalLibraryProvider to the persisted AssetLibrary
 * (see persistence/AssetLibrary.js) — the pipeline is the one place that
 * imports both and connects them, keeping providers decoupled from the
 * filesystem layer.
 */
export function createDefaultProviderChain({ queryIndex }) {
  return new ResourcePriorityChain([
    new LocalLibraryProvider({ queryIndex }),
    new DiagramProvider(),
    new TextResourceProvider(),
    new OpenEducationalResourcesProvider(),
    new WikimediaCommonsProvider(),
    new GoogleImagesProvider(),
    new AIGenerationProvider(),
    new AudioProvider(),
  ]);
}
