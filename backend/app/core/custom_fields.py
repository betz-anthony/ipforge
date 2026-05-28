"""CUSTOM-FIELDS-001 — load/save custom field values and tags for entities."""
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.custom_field import CustomFieldDef, CustomFieldValue, Tag, TagAssignment


def load_custom_fields_bulk(db: Session, entity_type: str, ids: list[int]) -> dict[int, dict[str, str]]:
    if not ids:
        return {}
    defs = {d.id: d.name for d in db.query(CustomFieldDef).filter_by(entity_type=entity_type).all()}
    if not defs:
        return {i: {} for i in ids}
    rows = (
        db.query(CustomFieldValue)
        .filter(CustomFieldValue.field_id.in_(defs.keys()))
        .filter(CustomFieldValue.entity_id.in_(ids))
        .all()
    )
    out: dict[int, dict[str, str]] = {i: {} for i in ids}
    for r in rows:
        name = defs.get(r.field_id)
        if name is not None and r.entity_id in out:
            out[r.entity_id][name] = r.value
    return out


def load_tags_bulk(db: Session, entity_type: str, ids: list[int]) -> dict[int, list[str]]:
    if not ids:
        return {}
    rows = (
        db.query(TagAssignment.entity_id, Tag.name)
        .join(Tag, Tag.id == TagAssignment.tag_id)
        .filter(TagAssignment.entity_type == entity_type)
        .filter(TagAssignment.entity_id.in_(ids))
        .all()
    )
    out: dict[int, list[str]] = {i: [] for i in ids}
    for entity_id, name in rows:
        out[entity_id].append(name)
    for v in out.values():
        v.sort()
    return out


def filter_entity_ids(
    db: Session,
    entity_type: str,
    tag: str | None = None,
    cf_filters: dict[str, str] | None = None,
) -> set[int] | None:
    """Return the entity ids matching the given tag and custom-field filters
    (intersection). Returns None when no filters are supplied (no restriction)."""
    cf_filters = cf_filters or {}
    if tag is None and not cf_filters:
        return None

    matched: set[int] | None = None

    if tag is not None:
        rows = (
            db.query(TagAssignment.entity_id)
            .join(Tag, Tag.id == TagAssignment.tag_id)
            .filter(TagAssignment.entity_type == entity_type)
            .filter(Tag.name.ilike(tag))
            .all()
        )
        matched = {r.entity_id for r in rows}

    if cf_filters:
        defs = {d.name: d.id for d in db.query(CustomFieldDef).filter_by(entity_type=entity_type).all()}
        for name, value in cf_filters.items():
            fid = defs.get(name)
            if fid is None:
                ids: set[int] = set()
            else:
                rows = (
                    db.query(CustomFieldValue.entity_id)
                    .filter_by(field_id=fid, value=value)
                    .all()
                )
                ids = {r.entity_id for r in rows}
            matched = ids if matched is None else (matched & ids)

    return matched if matched is not None else set()


def load_custom_fields(db: Session, entity_type: str, entity_id: int) -> dict[str, str]:
    return load_custom_fields_bulk(db, entity_type, [entity_id]).get(entity_id, {})


def load_tags(db: Session, entity_type: str, entity_id: int) -> list[str]:
    return load_tags_bulk(db, entity_type, [entity_id]).get(entity_id, [])


def set_custom_fields(db: Session, entity_type: str, entity_id: int, values: dict[str, str]) -> None:
    """Upsert the given {name: value} pairs. Unknown names are rejected;
    select values are validated against the field options. An empty string
    clears the value."""
    defs = {d.name: d for d in db.query(CustomFieldDef).filter_by(entity_type=entity_type).all()}
    for name, value in values.items():
        d = defs.get(name)
        if d is None:
            raise HTTPException(400, f"Unknown custom field {name!r} for {entity_type}")
        existing = db.query(CustomFieldValue).filter_by(field_id=d.id, entity_id=entity_id).first()
        if value is None or value == "":
            if existing:
                db.delete(existing)
            continue
        if d.field_type == "select":
            options = json.loads(d.options) if d.options else []
            if value not in options:
                raise HTTPException(400, f"{value!r} is not a valid option for {name!r}")
        if existing:
            existing.value = value
        else:
            db.add(CustomFieldValue(field_id=d.id, entity_id=entity_id, value=value))


def set_tags(db: Session, entity_type: str, entity_id: int, names: list[str]) -> None:
    """Replace the entity's tag set with the given names, creating tags as needed."""
    wanted = {n.strip() for n in names if n.strip()}
    by_lower = {t.name.lower(): t for t in db.query(Tag).all()}
    tag_ids: set[int] = set()
    for n in wanted:
        t = by_lower.get(n.lower())
        if t is None:
            t = Tag(name=n)
            db.add(t)
            db.flush()
            by_lower[n.lower()] = t
        tag_ids.add(t.id)

    existing = db.query(TagAssignment).filter_by(entity_type=entity_type, entity_id=entity_id).all()
    have = {a.tag_id: a for a in existing}
    for tid, a in have.items():
        if tid not in tag_ids:
            db.delete(a)
    for tid in tag_ids:
        if tid not in have:
            db.add(TagAssignment(tag_id=tid, entity_type=entity_type, entity_id=entity_id))
