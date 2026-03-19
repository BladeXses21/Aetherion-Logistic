from enum import StrEnum


class ErrorCode(StrEnum):
    INTERNAL_ERROR = "INTERNAL_ERROR"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    FUEL_PRICE_UNAVAILABLE = "FUEL_PRICE_UNAVAILABLE"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class AgentTimeoutError(Exception):
    pass


class LLMUnavailableError(Exception):
    pass
