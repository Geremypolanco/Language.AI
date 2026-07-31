from backend import academy, db
from scripts.export_faculty_directory import export_faculty_directory


def test_export_faculty_directory_covers_every_field():
    count = export_faculty_directory()
    assert count == len(academy.all_fields())

    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM faculty_directory")
        assert cur.fetchone()["n"] == len(academy.all_fields())


def test_export_faculty_directory_is_idempotent_on_re_run():
    export_faculty_directory()
    export_faculty_directory()  # re-running should update in place, not duplicate

    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM faculty_directory")
        assert cur.fetchone()["n"] == len(academy.all_fields())


def test_export_faculty_directory_row_matches_the_live_persona():
    from backend import personas

    export_faculty_directory()
    field = academy.all_fields()[0]
    expected = personas.build_field_faculty(field)

    with db.cursor() as cur:
        cur.execute("SELECT * FROM faculty_directory WHERE field_id=?", (field.id,))
        row = db.row_to_dict(cur.fetchone())

    assert row["persona_name"] == expected.name
    assert row["voice_description"] == expected.voice_description
    assert row["sampling_temperature"] == expected.sampling_temperature
    assert row["oer_namespace"] == field.id
