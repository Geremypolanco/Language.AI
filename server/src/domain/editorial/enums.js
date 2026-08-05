/**
 * Status value objects for the editorial pipeline. These are not plain
 * strings passed around ad-hoc — each one owns its own transition rules, so
 * "can a BuildJob go from failed back to pending?" has exactly one place it
 * is answered, and an illegal transition throws instead of silently
 * corrupting state.
 */

const BUILD_TRANSITIONS = {
  pending: ['running', 'cancelled'],
  running: ['succeeded', 'failed', 'cancelled'],
  succeeded: [],
  failed: ['pending'], // retry re-queues it
  cancelled: [],
};

export class BuildStatus {
  static PENDING = 'pending';
  static RUNNING = 'running';
  static SUCCEEDED = 'succeeded';
  static FAILED = 'failed';
  static CANCELLED = 'cancelled';
  static VALUES = Object.freeze(Object.keys(BUILD_TRANSITIONS));

  constructor(value = BuildStatus.PENDING) {
    if (!BuildStatus.VALUES.includes(value)) {
      throw new Error(`Invalid BuildStatus "${value}". Expected one of: ${BuildStatus.VALUES.join(', ')}`);
    }
    this.value = value;
  }

  canTransitionTo(next) {
    return (BUILD_TRANSITIONS[this.value] || []).includes(next);
  }

  transitionTo(next) {
    if (!this.canTransitionTo(next)) {
      throw new Error(`Cannot transition BuildStatus from "${this.value}" to "${next}".`);
    }
    return new BuildStatus(next);
  }

  isTerminal() {
    return BUILD_TRANSITIONS[this.value].length === 0;
  }

  equals(other) {
    return other instanceof BuildStatus ? this.value === other.value : this.value === other;
  }

  toString() {
    return this.value;
  }

  toJSON() {
    return this.value;
  }
}

const PUBLICATION_TRANSITIONS = {
  draft: ['published'],
  published: ['deprecated', 'retracted'],
  deprecated: ['published', 'retracted'], // rollback-then-republish is a valid path
  retracted: [],
};

export class PublicationStatus {
  static DRAFT = 'draft';
  static PUBLISHED = 'published';
  static DEPRECATED = 'deprecated';
  static RETRACTED = 'retracted';
  static VALUES = Object.freeze(Object.keys(PUBLICATION_TRANSITIONS));

  constructor(value = PublicationStatus.DRAFT) {
    if (!PublicationStatus.VALUES.includes(value)) {
      throw new Error(`Invalid PublicationStatus "${value}". Expected one of: ${PublicationStatus.VALUES.join(', ')}`);
    }
    this.value = value;
  }

  canTransitionTo(next) {
    return (PUBLICATION_TRANSITIONS[this.value] || []).includes(next);
  }

  transitionTo(next) {
    if (!this.canTransitionTo(next)) {
      throw new Error(`Cannot transition PublicationStatus from "${this.value}" to "${next}".`);
    }
    return new PublicationStatus(next);
  }

  isLive() {
    return this.value === PublicationStatus.PUBLISHED;
  }

  equals(other) {
    return other instanceof PublicationStatus ? this.value === other.value : this.value === other;
  }

  toString() {
    return this.value;
  }

  toJSON() {
    return this.value;
  }
}
