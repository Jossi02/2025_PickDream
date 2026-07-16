# Room identity schema

PickDream separates Firestore document identity from the classroom identity shown to users.

- `rooms/{documentId}`: the Firestore document key. It may be opaque and is used to address the room document and by the existing `User.favoriteRooms` list.
- `rooms.roomID`: the canonical four-digit classroom ID, such as `7202`.
- `Reservations.roomID` and `Reviews.roomID`: canonical four-digit classroom IDs only.
- `PendingReservations.room`: canonical four-digit classroom ID while an AI flow is pending.

New writes must use a value matching `[1-9][0-9]{3}`. A three-digit room number such as `202` is a search term, not a globally unique identity. It may be migrated only when the room catalog yields exactly one matching classroom.

Android may derive `rooms.roomID` from existing room metadata while old documents are being backfilled, but it never writes a derived three-digit value. Functions resolve document IDs, names, and building aliases through the room catalog and return the canonical `roomID`.

## Existing-data audit and backfill

The migration tool is dry-run by default:

```powershell
.\scripts\migrate-room-schema.ps1 -CredentialPath .\.secrets\pickdreamtest-service-account.json
```

Review every unresolved or ambiguous record. Apply only the unambiguous changes with:

```powershell
.\scripts\migrate-room-schema.ps1 -CredentialPath .\.secrets\pickdreamtest-service-account.json -Apply
```

The apply step refuses to run when multiple room documents resolve to the same canonical `roomID`; resolve those duplicate catalog entries first.

The script does not modify `User.favoriteRooms`; those values intentionally remain room document IDs for compatibility.
