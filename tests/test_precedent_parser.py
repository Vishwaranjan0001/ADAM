"""Tests for Hindi and English legal precedent citation parsing."""

from datetime import date
import pytest

from adam.extract.precedents import PrecedentCitationParser


def test_hindi_continuation_precedent():
    text = """
    कृपया उपर्युक्त विषयक शासनादेश संख्या 123/XXVII(7)/2022 दिनांक 15 मार्च 2022 के क्रम में
    मुझे यह कहने का निदेश हुआ है कि उल्लिखित व्यवस्था को यथावत लागू रखा जाए।
    """
    citations = PrecedentCitationParser.extract_citations(text)
    assert len(citations) >= 1

    c = citations[0]
    assert c.relation_type == "IN_CONTINUATION_OF"
    assert "123/XXVII(7)/2022" in c.cited_order_number
    assert c.cited_date == date(2022, 3, 15)


def test_hindi_supersession_precedent():
    text = """
    शासन द्वारा सम्यक विचारोपरांत शासनादेश संख्या 45/FD-2/2020 दिनांक 10 जनवरी 2020 को अधिक्रमित करते हुए
    नवीन दरें तत्काल प्रभाव से लागू की जाती हैं।
    """
    citations = PrecedentCitationParser.extract_citations(text)
    assert len(citations) >= 1

    c = citations[0]
    assert c.relation_type == "SUPERSEDES"
    assert "45/FD-2/2020" in c.cited_order_number
    assert c.cited_date == date(2020, 1, 10)


def test_english_continuation_and_supersession():
    text = """
    In supersession of Government Order No. 88/RD/2019 dated 15th August 2019,
    and in continuation of GO No. 92/RD/2021 dated 10th October 2021,
    the Governor is pleased to sanction the revised allocation.
    """
    citations = PrecedentCitationParser.extract_citations(text)
    assert len(citations) == 2

    c_super = next(c for c in citations if c.relation_type == "SUPERSEDES")
    assert "88/RD/2019" in c_super.cited_order_number
    assert c_super.cited_date == date(2019, 8, 15)

    c_cont = next(c for c in citations if c.relation_type == "IN_CONTINUATION_OF")
    assert "92/RD/2021" in c_cont.cited_order_number
    assert c_cont.cited_date == date(2021, 10, 10)


def test_statutory_read_with_precedent():
    text = """
    These guidelines are issued in exercise of powers read with Uttarakhand Procurement Rules 2017
    and Financial Handbook Volume 5.
    """
    citations = PrecedentCitationParser.extract_citations(text)
    assert len(citations) >= 1

    c_rule = next(c for c in citations if c.relation_type == "READ_WITH")
    assert "Uttarakhand Procurement Rules 2017" in c_rule.cited_act_or_rule
