from miniapp_ui_auto.filtering import CaseFilter, filter_cases
from miniapp_ui_auto.models import TestCase


def make_case(case_id: str, tags: tuple[str, ...], priority: str, module: str, driver: str = "dry-run"):
    return TestCase(
        id=case_id,
        title=case_id,
        platform="miniapp",
        driver=driver,
        module=module,
        priority=priority,
        tags=tags,
        owner="qa",
        version=1,
        preconditions=(),
        depends_on_previous=False,
        steps=(),
        assertions=(),
        source_path=f"{case_id}.yaml",
    )


def test_filter_by_tag_priority_module_and_driver():
    cases = [
        make_case("case_1", ("smoke",), "P0", "login"),
        make_case("case_2", ("regression",), "P1", "order"),
        make_case("case_3", ("smoke",), "P0", "login", driver="minium"),
    ]

    selected = filter_cases(
        cases,
        CaseFilter(tags=("smoke",), priorities=("P0",), modules=("login",), drivers=("dry-run",)),
    )

    assert [case.id for case in selected] == ["case_1"]


def test_empty_filter_returns_all_cases():
    cases = [
        make_case("case_1", ("smoke",), "P0", "login"),
        make_case("case_2", ("regression",), "P1", "order"),
    ]

    selected = filter_cases(cases, CaseFilter())

    assert [case.id for case in selected] == ["case_1", "case_2"]
