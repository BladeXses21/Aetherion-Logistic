from enum import StrEnum


class ErrorCode(StrEnum):
    INTERNAL_ERROR = "INTERNAL_ERROR"
    LARDI_TIMEOUT = "LARDI_TIMEOUT"
    LARDI_DETAIL_UNAVAILABLE = "LARDI_DETAIL_UNAVAILABLE"
    CARGO_NOT_FOUND = "CARGO_NOT_FOUND"
    LTSID_REFRESH_FAILED = "LTSID_REFRESH_FAILED"
    LTSID_REFRESH_TIMEOUT = "LTSID_REFRESH_TIMEOUT"
    QUEUE_UNAVAILABLE = "QUEUE_UNAVAILABLE"
    INVALID_FILTER_TYPE = "INVALID_FILTER_TYPE"


class LardiConnectionError(Exception):
    pass


class LardiRateLimitError(Exception):
    pass


class LtsidExpiredError(Exception):
    pass
