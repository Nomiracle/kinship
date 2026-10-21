# Archive redesign: local validation and release contract

## User-visible semantics

- A wardrobe item is a long-lived archive entry, not an event. `/wardrobe/items/new`
  has no event date. It requires an explicit owner, name and category; photos,
  color, tags and notes are optional. Saving must not create an event or wear.
- `/wardrobe/new` still means **record an outfit**. Existing `person` and `item`
  query deep links retain their meaning. Only a saved outfit changes wear history.
- Mobile main navigation is Overview / Records / Wardrobe / People. Todos remain
  reachable from Overview; Gallery remains its own route under Records, and
  Relationships under People. Existing URLs are retained.
- Header scope changes are page-local. `person=all` explicitly overrides a saved
  default person. Only “设为默认” persists the default; a form never guesses the
  first person as its owner.
- Record date and optional time are separate. Existing midnight-as-date-only
  storage semantics remain compatible; historical timestamps are not rewritten.
- There is one record composer for create and edit. Outfit picker changes are
  drafts only; cancel does not write. Changing owner must not reuse another
  person's garment references.
- A saved record with failed photos is not a failed record creation. Its ID and
  failed uploads remain available; retry must not create another record or resend
  successful attachments. Uncertain responses reuse the same persistent
  idempotency key and immutable request, not a newly generated key.
- Private drafts and File objects stay in session memory, not durable localStorage.
  Refresh/logout clears in-memory drafts. Existing authentication/preferences
  storage is not a draft store.
- “暂无穿着记录” describes absent recorded history, not proof an item was never worn.
  Unmerge restores an archive marker, **not** moved wear relations; it is not a
  full undo. Do not automatically delete historical events suspected to be fake.

## Safe validation

`npm run build` defaults to `frontend/dist`. It does not publish to a live path.
API regression tests must create an isolated database and a scratch deployment
root before importing backend settings. Never run the old smoke scripts against
production to verify this change. Use generated people and images only.

The implementation adds an incremental Alembic migration for persistent
idempotency. Before an approved release, validate on an isolated database:
upgrade from the previous head, compare original record IDs/relations/timestamps,
exercise retry, downgrade only the new table, re-upgrade. New production records
must survive a frontend rollback.

## Production release requires separate approval

No commit, push, tag, DB migration, service restart or frontend publication is
implied by local implementation. Before any approved production change:

1. Back up the database, media, and currently served `deploy/dist` together; record
   a restore point and validate the backup without exposing private data.
2. Validate the additive migration against an isolated restored DB; confirm
   record/media counts, IDs, relationships and historical dates unchanged.
3. Run the reviewed frontend and API regression gates and real-browser tests on
   the exact source tree being released.
4. Apply the backward-compatible backend migration and deploy backend first.
   Do not expose a client relying on persistent idempotency to an old backend.
5. Publish the reviewed `frontend/dist` artifact explicitly to the served
   `deploy/dist`, with old assets retained until clients have refreshed. An
   explicit build to that path is a release operation, never a test command.
6. Read back health/auth behavior and artifact hashes at origin and public domain.
   A public Basic Auth 401 is evidence of the outer gate only, not logged-in E2E.
7. On rollback, retain the new additive DB table and new records. Revert only
   code/assets unless an independently reviewed data rollback is required.

## Known validation boundary

The initial baseline build rebuilt existing-version served assets because the
original Vite configuration pointed to `../../deploy/dist`. The build default
was then changed to local `dist`; no service restart was performed. Subsequent
implementation builds must not touch the served directory. This is not evidence
of a redesign deployment.
