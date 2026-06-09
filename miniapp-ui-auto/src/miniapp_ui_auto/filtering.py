from __future__ import annotations

from dataclasses import dataclass

from miniapp_ui_auto.models import TestCase


@dataclass(frozen=True)
class CaseFilter:
    tags: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    drivers: tuple[str, ...] = ()


def filter_cases(cases: list[TestCase], case_filter: CaseFilter) -> list[TestCase]:
    return [case for case in cases if _matches(case, case_filter)]


def _matches(case: TestCase, case_filter: CaseFilter) -> bool:
    if case_filter.tags and not set(case_filter.tags).issubset(case.tags):
        return False
    if case_filter.priorities and case.priority not in case_filter.priorities:
        return False
    if case_filter.modules and case.module not in case_filter.modules:
        return False
    if case_filter.platforms and case.platform not in case_filter.platforms:
        return False
    if case_filter.drivers and case.driver not in case_filter.drivers:
        return False
    return True
