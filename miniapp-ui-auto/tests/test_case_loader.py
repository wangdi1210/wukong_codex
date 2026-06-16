from pathlib import Path

import pytest

from miniapp_ui_auto.case_loader import CaseValidationError, load_cases


def test_load_valid_case_from_directory():
    cases = load_cases(Path("cases"), Path("schemas/case.schema.json"))

    assert len(cases) >= 1
    case = next(item for item in cases if item.id == "airtest_case_20260609180554")
    assert case.id
    assert case.platform == "miniapp"
    assert case.driver == "airtest"
    assert case.steps[0].action == "open_app"
    assert case.assertions
    assert case.depends_on_previous is False


def test_load_case_dependency_flag():
    cases = load_cases(Path("cases"), Path("schemas/case.schema.json"))

    case = next(item for item in cases if item.id == "airtest_case_20260615214104")

    assert case.depends_on_previous is True


def test_invalid_case_reports_file_and_schema_message(tmp_path):
    case_dir = tmp_path / "cases"
    case_dir.mkdir()
    invalid_case = case_dir / "bad.yaml"
    invalid_case.write_text(
        "id: bad_case\n"
        "title: Missing required fields\n",
        encoding="utf-8",
    )

    with pytest.raises(CaseValidationError) as error:
        load_cases(case_dir, Path("schemas/case.schema.json"))

    assert "bad.yaml" in str(error.value)
    assert "required property" in str(error.value)
