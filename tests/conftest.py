from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def page1() -> str:
    return (FIXTURES / "oai_listrecords_page1.xml").read_text()


@pytest.fixture
def page2() -> str:
    return (FIXTURES / "oai_listrecords_page2.xml").read_text()


@pytest.fixture
def oai_error() -> str:
    return (FIXTURES / "oai_error_badresumption.xml").read_text()
