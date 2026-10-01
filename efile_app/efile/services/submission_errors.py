"""Stable error codes used by the final submission flow."""


class SubmissionErrorCode:
    """Machine-readable codes for errors returned before filing submission."""

    FILING_UNAVAILABLE = "submission_filing_unavailable"
    CASE_DATA_MISSING = "submission_case_data_missing"
    UPLOAD_DATA_MISSING = "submission_upload_data_missing"
    EFILE_DATA_MISSING = "submission_efile_data_missing"
    EFILE_DATA_INVALID = "submission_efile_data_invalid"
    COURT_ID_MISSING = "submission_court_id_missing"
    PAYLOAD_VALIDATION_FAILED = "submission_payload_validation_failed"
    FEE_QUOTE_STALE = "submission_fee_quote_stale"


PRE_SUBMIT_ERROR_CODES = frozenset(
    {
        SubmissionErrorCode.FILING_UNAVAILABLE,
        SubmissionErrorCode.CASE_DATA_MISSING,
        SubmissionErrorCode.UPLOAD_DATA_MISSING,
        SubmissionErrorCode.EFILE_DATA_MISSING,
        SubmissionErrorCode.EFILE_DATA_INVALID,
        SubmissionErrorCode.COURT_ID_MISSING,
        SubmissionErrorCode.PAYLOAD_VALIDATION_FAILED,
        SubmissionErrorCode.FEE_QUOTE_STALE,
    }
)
