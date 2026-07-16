import argparse
import re
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import firestore


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "functions"))

from reservation_utils import extract_room_id, is_canonical_room_id, reservation_room_id  # noqa: E402


def resolve_reference(raw_value, catalog_by_document, canonical_ids, duplicate_ids=None):
    duplicate_ids = duplicate_ids or set()
    raw = str(raw_value or "").strip()
    if not raw:
        return None, "blank"
    if raw in catalog_by_document:
        return catalog_by_document[raw], None

    extracted = extract_room_id(raw)
    if extracted and is_canonical_room_id(extracted):
        if extracted in duplicate_ids:
            return None, "ambiguous canonical ID"
        return (extracted, None) if extracted in canonical_ids else (None, "unknown canonical ID")
    if extracted and re.fullmatch(r"\d{3}", extracted):
        candidates = sorted(room_id for room_id in canonical_ids if room_id.endswith(extracted))
        if len(candidates) == 1:
            return candidates[0], None
        if len(candidates) > 1:
            return None, f"ambiguous: {', '.join(candidates)}"
    return None, "unresolved"


def find_duplicate_room_ids(catalog_by_document):
    documents_by_room_id = {}
    for document_id, room_id in catalog_by_document.items():
        documents_by_room_id.setdefault(room_id, []).append(document_id)
    return {
        room_id: sorted(document_ids)
        for room_id, document_ids in documents_by_room_id.items()
        if len(document_ids) > 1
    }


def commit_updates(db, updates):
    for offset in range(0, len(updates), 400):
        batch = db.batch()
        for reference, fields in updates[offset : offset + 400]:
            batch.update(reference, fields)
        batch.commit()


def main():
    parser = argparse.ArgumentParser(description="Audit and backfill PickDream canonical room IDs")
    parser.add_argument("--project", default="pickdreamtest")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": args.project})
    db = firestore.client()

    updates = []
    unresolved = []
    catalog_candidates = {}
    room_data_by_document = {}
    room_document_by_id = {}
    catalog_by_document = {}
    canonical_ids = set()

    room_documents = list(db.collection("rooms").stream())
    for document in room_documents:
        data = document.to_dict() or {}
        room_data_by_document[document.id] = data
        room_document_by_id[document.id] = document
        canonical = reservation_room_id(document.id, data)
        if not is_canonical_room_id(canonical):
            unresolved.append((f"rooms/{document.id}", data.get("roomID"), "cannot derive canonical roomID"))
            continue
        catalog_candidates[document.id] = canonical

    duplicate_ids = find_duplicate_room_ids(catalog_candidates)
    for document_id, canonical in catalog_candidates.items():
        data = room_data_by_document[document_id]
        document = room_document_by_id[document_id]
        if canonical in duplicate_ids:
            duplicate_documents = ", ".join(duplicate_ids[canonical])
            unresolved.append(
                (
                    f"rooms/{document_id}",
                    data.get("roomID"),
                    f"duplicate canonical roomID {canonical}: {duplicate_documents}",
                )
            )
            continue
        catalog_by_document[document_id] = canonical
        canonical_ids.add(canonical)
        if str(data.get("roomID") or "").strip() != canonical:
            updates.append((document.reference, {"roomID": canonical}))

    targets = (
        ("Reservations", "roomID"),
        ("Reviews", "roomID"),
        ("PendingReservations", "room"),
    )
    for collection_name, field_name in targets:
        for document in db.collection(collection_name).stream():
            data = document.to_dict() or {}
            raw = data.get(field_name)
            canonical, reason = resolve_reference(
                raw,
                catalog_by_document,
                canonical_ids,
                duplicate_ids=set(duplicate_ids),
            )
            path = f"{collection_name}/{document.id}"
            if canonical is None:
                unresolved.append((path, raw, reason))
                continue
            if str(raw or "").strip() != canonical:
                updates.append((document.reference, {field_name: canonical}))

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] rooms={len(room_documents)} proposed_updates={len(updates)} unresolved={len(unresolved)}")
    for reference, fields in updates:
        print(f"UPDATE {reference.path}: {fields}")
    for path, value, reason in unresolved:
        print(f"REVIEW {path}: value={value!r} reason={reason}")

    if args.apply and duplicate_ids:
        print("Refusing to apply updates until duplicate canonical room IDs are resolved.", file=sys.stderr)
        return 2
    if args.apply and updates:
        commit_updates(db, updates)
        print(f"Applied {len(updates)} updates.")
    elif not args.apply:
        print("No data was changed. Re-run with --apply after reviewing the report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
