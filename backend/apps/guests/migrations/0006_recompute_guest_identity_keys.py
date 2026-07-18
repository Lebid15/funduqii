"""DATA migration: recompute the normalized guest-identity keys with the NEW
folding rules, and apply the owner's national-id unification decision.

Why this migration is the real failure point
--------------------------------------------
The partial constraint ``unique_guest_national_id_per_hotel`` already exists
(added in ``0004``) on ``national_id_normalized``. Re-folding non-Latin digits
can turn two rows that previously had different (or empty) keys into the SAME
key, which would violate that constraint at write time. So BEFORE writing a
single row, this migration:

  1. Recomputes ``phone_normalized`` / ``national_id_normalized`` /
     ``document_number_normalized`` for every row using an INLINE, frozen copy of
     the folding logic (never importing ``apps.guests.normalize`` — a migration
     must not depend on today's app code).
  2. Applies Decision 3 for ``document_type='national_id'`` rows: backfill
     ``Guest.national_id`` ONLY when it is empty; unify silently when it equals
     the document number after normalization; and STOP the whole migration with a
     PII-masked report when they DIFFER — never auto-pick a winner, never merge,
     never delete.
  3. Detects any recomputed ``national_id_normalized`` collision within a hotel
     and STOPS with a PII-masked report BEFORE any write (a clean error instead
     of a raw IntegrityError).

reverse = noop: the recompute is idempotent and the pre-existing keys are not
meaningfully restorable; re-running the forward step reproduces the same values.
"""
import re

from django.db import migrations

# --- Frozen folding logic (inline copy — DO NOT import apps.guests.normalize) --
_NON_DIGIT = re.compile(r"[^0-9]")
_NON_ALNUM = re.compile(r"[^0-9A-Z]")

_DIGIT_FOLD_MAP = {}
for _i in range(10):
    _DIGIT_FOLD_MAP[0x0660 + _i] = str(_i)  # Arabic-Indic ٠..٩
    _DIGIT_FOLD_MAP[0x06F0 + _i] = str(_i)  # Extended / Persian ۰..۹
del _i


def _fold(value):
    return str(value).translate(_DIGIT_FOLD_MAP)


def _norm_id(value):
    if not value:
        return ""
    return _NON_ALNUM.sub("", _fold(value).upper())


def _norm_doc(value):
    return _norm_id(value)


def _norm_phone(value):
    if not value:
        return ""
    raw = _fold(value).strip()
    digits = _NON_DIGIT.sub("", raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        return f"+{digits}"
    if raw.startswith("00"):
        return f"+{digits[2:]}"
    return digits


# --- PII masking for the stop-reports (never print a full identifier) ---------
def _mask(value):
    s = (value or "").strip()
    if not s:
        return "∅"  # ∅ (empty)
    if len(s) <= 2:
        return "••"
    return "••••" + s[-2:]


def _decision3_report(conflicts):
    lines = [
        "Guest identity migration 0006 STOPPED — a guest's national_id and its "
        "national_id-type document number DIFFER after normalization. No row was "
        "changed. Each case must be resolved manually (never auto-merged, never "
        "auto-picked):",
    ]
    for hotel_id, guest_id, nid, doc in conflicts:
        lines.append(
            f"  hotel={hotel_id} guest={guest_id} "
            f"national_id={_mask(nid)} document_number={_mask(doc)}"
        )
    return "\n".join(lines)


def _collision_report(collisions):
    lines = [
        "Guest identity migration 0006 STOPPED — recomputed national_id keys "
        "collide within a hotel (would violate unique_guest_national_id_per_hotel). "
        "No row was changed. De-duplicate these guests manually first:",
    ]
    for (hotel_id, nid), guest_ids in collisions.items():
        ids = ",".join(str(i) for i in sorted(guest_ids))
        lines.append(f"  hotel={hotel_id} national_id={_mask(nid)} guests=[{ids}]")
    return "\n".join(lines)


def _forward(apps, schema_editor):
    Guest = apps.get_model("guests", "Guest")

    rows = list(
        Guest.objects.all().only(
            "id",
            "hotel_id",
            "phone",
            "national_id",
            "document_type",
            "document_number",
            "phone_normalized",
            "national_id_normalized",
            "document_number_normalized",
        )
    )

    decision3_conflicts = []
    planned = []  # (guest, new_phone, new_nid, new_doc, final_national_id)
    for g in rows:
        new_phone = _norm_phone(g.phone)
        new_doc = _norm_doc(g.document_number)
        final_national_id = g.national_id
        if g.document_type == "national_id" and (g.document_number or "").strip():
            doc_key = new_doc
            current_nid_key = _norm_id(g.national_id)
            if not (g.national_id or "").strip():
                # national_id empty -> adopt the document's number (backfill).
                final_national_id = g.document_number
            elif current_nid_key == doc_key:
                # Equal after normalization -> unify, keep national_id (the legal
                # source of truth). No change needed.
                final_national_id = g.national_id
            else:
                # DIFFER -> a real conflict. Collect; stop after the full pass so
                # the operator sees every case at once.
                decision3_conflicts.append(
                    (g.hotel_id, g.id, g.national_id, g.document_number)
                )
        new_nid = _norm_id(final_national_id)
        planned.append((g, new_phone, new_nid, new_doc, final_national_id))

    if decision3_conflicts:
        raise RuntimeError(_decision3_report(decision3_conflicts))

    # Pre-write per-hotel national_id_normalized collision detection.
    first_seen = {}  # (hotel_id, nid) -> first guest id
    collisions = {}  # (hotel_id, nid) -> set of guest ids
    for g, _phone, nid, _doc, _fn in planned:
        if not nid:
            continue
        key = (g.hotel_id, nid)
        if key in first_seen and first_seen[key] != g.id:
            collisions.setdefault(key, {first_seen[key]}).add(g.id)
        else:
            first_seen.setdefault(key, g.id)
    if collisions:
        raise RuntimeError(_collision_report(collisions))

    # --- Safe to write. The FINAL data state is identical to a single bulk pass;
    # only the write STRATEGY changes to defend national_id_normalized against a
    # TRANSIENT collision (DATA-F1).
    #
    # The partial unique index ``unique_guest_national_id_per_hotel`` (added in
    # 0004, on national_id_normalized WHERE it is non-empty) already exists here.
    # In a SINGLE bulk UPDATE that re-folds many keys at once, PostgreSQL checks
    # uniqueness per row mid-statement, so a row's NEW value can transiently equal
    # ANOTHER row's still-OLD value even though the FINAL state is conflict-free
    # (already proven above). SQLite hides this; PostgreSQL raises a spurious
    # IntegrityError. So national_id_normalized is written in TWO phases.
    #
    # The other three columns carry NO unique index at THIS point in history —
    # document_number_normalized / phone_normalized get their constraints later in
    # 0007, and the 0001 document constraint is on the RAW document_number (not the
    # normalized column, untouched here) — so they update in one ordinary pass and
    # cannot transiently collide.

    # 1) phone_normalized + document_number_normalized + the backfilled
    #    national_id in one pass (no unique index involved).
    to_update = []
    for g, new_phone, _new_nid, new_doc, final_national_id in planned:
        g.phone_normalized = new_phone
        g.document_number_normalized = new_doc
        g.national_id = final_national_id
        to_update.append(g)
    if to_update:
        Guest.objects.bulk_update(
            to_update,
            [
                "phone_normalized",
                "document_number_normalized",
                "national_id",
            ],
            batch_size=500,
        )

    # 2) national_id_normalized in two phases, over ONLY the rows whose key is
    #    actually changing.
    #    Phase A — clear the changing rows to '' so they LEAVE the partial index
    #      (empty keys are not indexed, so this phase can never collide).
    #    Phase B — set their final NON-EMPTY keys. Every changing row now starts
    #      from '' and the final state is unique, so no NEW value can equal any
    #      value still present in the index: no transient collision is possible.
    nid_changing = [
        (g, new_nid)
        for g, _phone, new_nid, _doc, _fn in planned
        if new_nid != (g.national_id_normalized or "")
    ]
    if nid_changing:
        for g, _new in nid_changing:
            g.national_id_normalized = ""
        Guest.objects.bulk_update(
            [g for g, _ in nid_changing],
            ["national_id_normalized"],
            batch_size=500,
        )
        nid_final = [(g, new_nid) for g, new_nid in nid_changing if new_nid]
        for g, new_nid in nid_final:
            g.national_id_normalized = new_nid
        if nid_final:
            Guest.objects.bulk_update(
                [g for g, _ in nid_final],
                ["national_id_normalized"],
                batch_size=500,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("guests", "0005_guest_document_number_normalized"),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
    ]
