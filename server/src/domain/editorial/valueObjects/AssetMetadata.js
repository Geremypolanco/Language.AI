import { DomainEntity } from '../../shared/DomainEntity.js';
import { assetMetadataSchema, LICENSE_ALLOWLIST } from '../../../asset-builder/schemas.js';

const OPEN_LICENSES = new Set(['CC0', 'public-domain', 'CC-BY', 'CC-BY-SA']);

/**
 * One persisted educational asset. Deliberately reuses
 * asset-builder/schemas.js's existing `assetMetadataSchema` rather than
 * redefining the same 19 fields a second time — this class is the "no
 * anemic models" wrapper around validation that already existed, not a
 * competing definition of it.
 */
export class AssetMetadata extends DomainEntity {
  static schema = assetMetadataSchema;

  /** Third-party assets need attribution; ones we generated ourselves don't. */
  requiresAttribution() {
    return this.license !== 'proprietary-generated';
  }

  isOpenlyLicensed() {
    return OPEN_LICENSES.has(this.license) || this.license === 'proprietary-generated';
  }

  matchesLicenseAllowlist(allowlist = LICENSE_ALLOWLIST) {
    return allowlist.includes(this.license);
  }

  isImageLike() {
    return ['image', 'gallery', 'illustration'].includes(this.resource_type);
  }
}
