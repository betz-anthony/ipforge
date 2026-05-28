import pytest
from sqlalchemy.exc import IntegrityError

from app.models.custom_field import CustomFieldDef, CustomFieldValue, Tag, TagAssignment


def test_create_field_def(db):
    f = CustomFieldDef(entity_type="subnet", name="owner", label="Owner", field_type="text")
    db.add(f)
    db.commit()
    assert f.id is not None
    assert f.options is None


def test_field_def_name_unique_per_entity_type(db):
    db.add(CustomFieldDef(entity_type="subnet", name="owner", label="Owner", field_type="text"))
    db.commit()
    # same name allowed for a different entity type
    db.add(CustomFieldDef(entity_type="address", name="owner", label="Owner", field_type="text"))
    db.commit()
    # duplicate within same entity type rejected
    db.add(CustomFieldDef(entity_type="subnet", name="owner", label="Dup", field_type="text"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_value_unique_per_field_and_entity(db):
    f = CustomFieldDef(entity_type="subnet", name="env", label="Env", field_type="text")
    db.add(f)
    db.flush()
    db.add(CustomFieldValue(field_id=f.id, entity_id=1, value="prod"))
    db.commit()
    db.add(CustomFieldValue(field_id=f.id, entity_id=1, value="dup"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_tag_name_unique(db):
    db.add(Tag(name="critical"))
    db.commit()
    db.add(Tag(name="critical"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_tag_assignment_unique(db):
    t = Tag(name="critical")
    db.add(t)
    db.flush()
    db.add(TagAssignment(tag_id=t.id, entity_type="subnet", entity_id=1))
    db.commit()
    db.add(TagAssignment(tag_id=t.id, entity_type="subnet", entity_id=1))
    with pytest.raises(IntegrityError):
        db.commit()
