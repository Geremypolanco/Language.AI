/**
 * Base class every domain model (editorial and runtime) extends. It is the
 * one piece of shared machinery in the whole domain layer, and it exists to
 * make three requirements structural instead of a matter of discipline:
 *
 *  1. Every model validates itself on construction (consistency, types,
 *     restrictions) — you cannot build an invalid ContentPackage, Progress
 *     record, etc. `new Foo(bad data)` throws a ZodError, full stop.
 *  2. Every model is a real class, not a JSON blob — subclasses add
 *     behavior methods alongside the validated fields, so "no anemic
 *     models" is the default rather than something each file has to
 *     remember to do.
 *  3. Every model can serialize back to a plain object (`toJSON`) so it
 *     drops in wherever `res.json()`/`JSON.stringify` already expects plain
 *     data — existing API contracts don't need to change to adopt this.
 *
 * Subclasses declare `static schema = z.object({...})` and get validated
 * property assignment for free:
 *
 *   class Concept extends DomainEntity {
 *     static schema = z.object({ id: z.string(), name: z.string() });
 *     describe() { return `Concept: ${this.name}`; }
 *   }
 */
export class DomainEntity {
  constructor(props) {
    const schema = new.target.schema;
    if (!schema) {
      throw new Error(`${new.target.name} must declare a static "schema" (Zod schema).`);
    }
    const parsed = schema.parse(props);
    Object.assign(this, parsed);
  }

  toJSON() {
    return { ...this };
  }
}
