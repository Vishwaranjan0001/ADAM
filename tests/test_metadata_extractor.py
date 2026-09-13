"""Tests for administrative metadata, authority, and subject extraction."""

from datetime import date
import pytest

from adam.extract.metadata import AdministrativeMetadataExtractor


def test_administrative_metadata_extraction():
    text = """
    संख्या : 441/XXVII(7)/2024
    उत्तराखंड शासन
    वित्त अनुभाग-7
    देहरादून : दिनांक 15 जनवरी, 2024

    कार्यालय ज्ञाप

    विषय : राज्य कर्मचारियों को देय महंगाई भत्ते की दरों में पुनरीक्षण।

    महोदय,
    उपर्युक्त विषय के संबंध में मुझे यह कहने का निदेश हुआ है कि वित्तीय वर्ष 2024-25 हेतु...
    उक्त आदेश तत्काल प्रभाव से लागू होंगे।

    भवदीय,
    ह०/-
    (आनन्द बर्द्धन)
    अपर मुख्य सचिव
    """

    meta = AdministrativeMetadataExtractor.extract(text)

    assert meta.order_number == "441/XXVII(7)/2024"
    assert meta.order_date == date(2024, 1, 15)
    assert meta.subject is not None
    assert "महंगाई भत्ते" in meta.subject
    assert meta.issuing_authority_title == "अपर मुख्य सचिव"
    assert meta.signatory_name == "आनन्द बर्द्धन"
    assert meta.language_distribution["hi_pct"] > 70


def test_english_metadata_extraction():
    text = """
    Order No: 99/ITDA/2023
    Government of Uttarakhand
    Information Technology Development Agency
    Dated: 10th October 2023

    Subject: Implementation of e-Office workflow across all collectorates.

    The Governor of Uttarakhand is pleased to notify...

    Yours faithfully,
    (R. K. Sudhanshu)
    Principal Secretary
    """

    meta = AdministrativeMetadataExtractor.extract(text)

    assert meta.order_number == "99/ITDA/2023"
    assert meta.order_date == date(2023, 10, 10)
    assert "e-Office workflow" in meta.subject
    assert meta.issuing_authority_title == "Principal Secretary"
    assert "Sudhanshu" in meta.signatory_name
    assert meta.language_distribution["en_pct"] > 70
