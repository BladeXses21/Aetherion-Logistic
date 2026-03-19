from enum import StrEnum


class ErrorCode(StrEnum):
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    LTSID_MISSING = "LTSID_MISSING"
    LTSID_FETCH_FAILED = "LTSID_FETCH_FAILED"


class ChromeStartupError(Exception):
    pass


class LtsidFetchError(Exception):
    pass
