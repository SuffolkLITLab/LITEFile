import re

from efile.services.filing_code_search import path_alias_tokens, search_tokens


def _form_search_term(key):
    return "concept" + re.sub(r"[^a-z0-9]", "", key)


def test_vermont_rfa_form_alias_is_exact_and_case_scoped():
    expected_search_term = _form_search_term("vt_form_400_00151")
    assert expected_search_term in path_alias_tokens("vermont", True, "Family", "Relief from Abuse", "Affidavit")
    assert expected_search_term not in path_alias_tokens(
        "vermont", False, "Family", "Relief from Abuse on Behalf of a Minor", "Affidavit"
    )
    assert expected_search_term not in path_alias_tokens(
        "vermont", True, "Civil", "Small Claims over $1,001", "Affidavit"
    )
    assert expected_search_term not in path_alias_tokens("vermont", True, "Family", "Divorce", "Affidavit")

    minor_search_term = _form_search_term("vt_form_400_00151m")
    assert minor_search_term in path_alias_tokens(
        "vermont", False, "Family", "Relief from Abuse on Behalf of a Minor", "Affidavit"
    )
    assert minor_search_term not in path_alias_tokens("vermont", True, "Family", "Relief from Abuse", "Affidavit")

    assert expected_search_term in search_tokens("400-00151", "vermont", query=True, path_query=True)
    assert expected_search_term not in search_tokens("400-00151M", "vermont", query=True, path_query=True)
    assert expected_search_term in search_tokens(
        "Affidavit in Support of Relief from Abuse Complaint", "vermont", query=True, path_query=True
    )
    assert expected_search_term not in search_tokens("affidavit", "vermont", query=True, path_query=True)
    assert minor_search_term in search_tokens(
        "Affidavit in Support of Relief from Abuse Complaint for Child", "vermont", query=True, path_query=True
    )
    assert minor_search_term in search_tokens("400-00151M", "vermont", query=True, path_query=True)


def test_vermont_small_claims_postjudgment_form_stays_subsequent_only():
    expected_search_term = _form_search_term("vt_form_100_00127")
    assert expected_search_term in path_alias_tokens(
        "vermont", False, "Civil", "Small Claims $1,000 or less", "Small Claims - Financial Disclosure Affidavit"
    )
    assert expected_search_term not in path_alias_tokens(
        "vermont", True, "Civil", "Small Claims $1,000 or less", "Small Claims - Financial Disclosure Affidavit"
    )
    assert expected_search_term not in path_alias_tokens(
        "vermont", False, "Family", "Relief from Abuse", "Small Claims - Financial Disclosure Affidavit"
    )
    assert expected_search_term in search_tokens("100-00127", "vermont", query=True, path_query=True)
    assert expected_search_term not in search_tokens("financial affidavit", "vermont", query=True, path_query=True)


def test_vermont_self_represented_notice_alias_is_subsequent_and_title_specific():
    expected_search_term = _form_search_term("vt_form_400_00831")
    assert expected_search_term in path_alias_tokens(
        "vermont", False, "Family", "Divorce", "Notice of Pro Se Appearance"
    )
    assert expected_search_term not in path_alias_tokens(
        "vermont", True, "Family", "Divorce", "Notice of Pro Se Appearance"
    )
    assert expected_search_term not in search_tokens("notice of appearance", "vermont", query=True, path_query=True)
    assert expected_search_term in search_tokens("400-00831", "vermont", query=True, path_query=True)


def test_vermont_civil_notice_id_is_not_mistaken_for_a_certificate():
    expected_search_term = _form_search_term("vt_form_100_00265")
    assert expected_search_term in path_alias_tokens(
        "vermont", False, "Civil", "Collection - Non-Credit Card", "Notice of Pro Se Appearance"
    )
    assert expected_search_term not in path_alias_tokens(
        "vermont", False, "Civil", "Collection - Non-Credit Card", "Certificate of Service"
    )
    assert expected_search_term not in path_alias_tokens(
        "vermont", True, "Civil", "Collection - Non-Credit Card", "Notice of Pro Se Appearance"
    )
    assert expected_search_term in search_tokens("100-00265", "vermont", query=True, path_query=True)
    title_search_term = _form_search_term("vt_form_self_rep_notice_title")
    assert title_search_term in search_tokens(
        "Notice of Appearance for Self-Represented Party", "vermont", query=True, path_query=True
    )
    assert title_search_term in path_alias_tokens(
        "vermont", False, "Civil", "Collection - Non-Credit Card", "Notice of Pro Se Appearance"
    )
    assert title_search_term in path_alias_tokens("vermont", False, "Family", "Divorce", "Notice of Pro Se Appearance")


def test_vermont_small_claims_answer_is_subsequent_and_small_claims_scoped():
    expected_search_term = _form_search_term("vt_form_100_00126")
    assert expected_search_term in path_alias_tokens("vermont", False, "Civil", "Small Claims $1,000 or less", "Answer")
    assert expected_search_term not in path_alias_tokens(
        "vermont", True, "Civil", "Small Claims $1,000 or less", "Answer"
    )
    assert expected_search_term not in path_alias_tokens(
        "vermont", False, "Civil", "Collection - Credit Card", "Answer"
    )
    assert expected_search_term in search_tokens("100-00126", "vermont", query=True, path_query=True)
    assert expected_search_term not in search_tokens("answer", "vermont", query=True, path_query=True)
