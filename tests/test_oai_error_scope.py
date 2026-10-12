"""Only the OAI-PMH <error> child of the root is a protocol error (stress test,
12 October 2026).

_oai_error walked the whole tree, so a harvested record whose metadata carried
any element named "error" (a field in another schema, say) turned a good page
of records into OAI_ERROR "unknown: ..." and the records were discarded.
"""
import xml.etree.ElementTree as ET

from korea_scholarship_mcp import server as S

NS = "http://www.openarchives.org/OAI/2.0/"


def _page(body):
    return ET.fromstring(
        f'<OAI-PMH xmlns="{NS}"><responseDate>2026-10-12T00:00:00Z</responseDate>'
        f'<request verb="ListRecords">x</request>{body}</OAI-PMH>')


RECORD_WITH_ERROR_FIELD = (
    '<ListRecords><record><header><identifier>oai:x:1</identifier></header>'
    '<metadata><dc xmlns="urn:example:other"><title>T</title>'
    '<error>measurement error</error></dc></metadata></record></ListRecords>')


def test_an_error_field_inside_a_record_is_not_a_protocol_error():
    assert S._oai_error(_page(RECORD_WITH_ERROR_FIELD)) is None


def test_an_oai_error_in_another_namespace_under_the_record_is_ignored():
    body = RECORD_WITH_ERROR_FIELD.replace('xmlns="urn:example:other"', f'xmlns="{NS}"')
    assert S._oai_error(_page(body)) is None


def test_the_root_error_is_still_reported():
    d = S._oai_error(_page('<error code="badArgument">bad from</error>'))
    assert d["code"] == "OAI_ERROR" and "badArgument" in d["message"]


def test_no_records_match_is_still_info():
    d = S._oai_error(_page('<error code="noRecordsMatch">none</error>'))
    assert d["code"] == "OAI_NO_RECORDS"
