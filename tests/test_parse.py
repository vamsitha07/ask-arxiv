from datetime import date

import pytest

from askarxiv.parse import OaiError, parse_complete_list_size, parse_list_records


def test_parses_records_and_token(page1):
    papers, token = parse_list_records(page1)
    # Three <record> elements: two live, one tombstone. The tombstone is skipped.
    assert [p.arxiv_id for p in papers] == ["2603.01234", "2603.05555"]
    assert token == "TOKEN-PAGE-2"


def test_unwraps_text_wrapped_by_the_feed(page1):
    papers, _ = parse_list_records(page1)
    paper = papers[0]
    assert paper.title == "Parent-Child Retrieval for Long Scientific Documents"
    assert "\n" not in paper.abstract
    assert paper.abstract.startswith("We study section-aware chunking")


def test_primary_category_is_the_first_listed(page1):
    papers, _ = parse_list_records(page1)
    assert papers[0].primary_category == "cs.AI"
    assert papers[0].has_category("cs.IR")
    assert not papers[1].has_category("cs.AI")


def test_optional_fields_survive_being_absent(page1):
    papers, _ = parse_list_records(page1)
    with_doi, without_doi = papers
    assert with_doi.doi == "10.1000/example.2603.01234"
    assert with_doi.updated == date(2026, 3, 11)
    assert without_doi.doi is None
    assert without_doi.updated is None
    assert without_doi.authors[0].display() == "Mehta"


def test_empty_resumption_token_means_finished(page2):
    """An empty <resumptionToken/> ends the feed. Reading it as a token loops forever."""
    papers, token = parse_list_records(page2)
    assert len(papers) == 1
    assert token is None


def test_oai_error_is_raised_not_swallowed(oai_error):
    with pytest.raises(OaiError, match="badResumptionToken"):
        parse_list_records(oai_error)


def test_complete_list_size_is_read_from_the_first_page(page1):
    assert parse_complete_list_size(page1) == 1372
