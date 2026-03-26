"""
test_constants_filters.py — тести констант фільтрів пошуку вантажів.

Перевіряє коректність маппінгу:
  - DOCUMENT_UA_TO_CODE (українські назви → Lardi коди)
  - VALID_DOCUMENT_CODES (множина допустимих кодів)
  - CARGO_BODY_MODIFIER_UA_TO_NAME (назви модифікаторів кузова)
  - PAYMENT_FORM_UA_TO_ID (форми оплати)
  - PAYMENT_CURRENCY_UA_TO_ID (валюти оплати)
  - PAYMENT_VALUE_TYPE_UA_TO_CODE (типи ставки)
  - resolve_* функції
"""
from __future__ import annotations

import pytest

from app.constants import (
    CARGO_BODY_MODIFIER_UA_TO_NAME,
    DOCUMENT_UA_TO_CODE,
    PAYMENT_CURRENCY_UA_TO_ID,
    PAYMENT_FORM_UA_TO_ID,
    PAYMENT_VALUE_TYPE_UA_TO_CODE,
    VALID_DOCUMENT_CODES,
    resolve_body_modifier,
    resolve_document_code,
    resolve_payment_currency_id,
    resolve_payment_form_id,
    resolve_payment_value_type,
)


# --- Тести: VALID_DOCUMENT_CODES ---

def test_valid_document_codes_contains_all_lardi_codes():
    """VALID_DOCUMENT_CODES містить всі підтверджені коди Lardi."""
    expected = {"cmr", "t1", "tir", "ekmt", "frc", "cmrInsurance"}
    assert expected == VALID_DOCUMENT_CODES


def test_valid_document_codes_is_frozenset():
    """VALID_DOCUMENT_CODES є frozenset (незмінна)."""
    assert isinstance(VALID_DOCUMENT_CODES, frozenset)


# --- Тести: DOCUMENT_UA_TO_CODE ---

@pytest.mark.parametrize("input_name, expected_code", [
    ("cmr",                  "cmr"),
    ("CMR",                  "cmr"),
    ("цмр",                  "cmr"),
    ("накладна",             "cmr"),
    ("міжнародна накладна",  "cmr"),
    ("tir",                  "tir"),
    ("TIR",                  "tir"),
    ("тір",                  "tir"),
    ("книжка tir",           "tir"),
    ("t1",                   "t1"),
    ("T1",                   "t1"),
    ("транзит",              "t1"),
    ("митний транзит",       "t1"),
    ("ekmt",                 "ekmt"),
    ("EKMT",                 "ekmt"),
    ("єкмт",                 "ekmt"),
    ("frc",                  "frc"),
    ("FRC",                  "frc"),
    ("страховка cmr",        "cmrInsurance"),
    ("cmr страховка",        "cmrInsurance"),
    ("страховка",            "cmrInsurance"),
])
def test_document_ua_to_code_mapping(input_name, expected_code):
    """DOCUMENT_UA_TO_CODE коректно маппить всі варіанти назв у коди."""
    assert DOCUMENT_UA_TO_CODE.get(input_name.lower().strip()) == expected_code


def test_document_ua_to_code_unknown_returns_none():
    """Невідома назва документа → None."""
    assert DOCUMENT_UA_TO_CODE.get("невідомий документ") is None


# --- Тести: resolve_document_code ---

def test_resolve_document_code_cmr():
    """resolve_document_code('CMR') → 'cmr'."""
    assert resolve_document_code("CMR") == "cmr"


def test_resolve_document_code_tir_lowercase():
    """resolve_document_code('tir') → 'tir'."""
    assert resolve_document_code("tir") == "tir"


def test_resolve_document_code_ukrainian():
    """resolve_document_code('цмр') → 'cmr'."""
    assert resolve_document_code("цмр") == "cmr"


def test_resolve_document_code_unknown_returns_none():
    """resolve_document_code з невідомою назвою → None."""
    assert resolve_document_code("ліцензія") is None


def test_resolve_document_code_strips_whitespace():
    """resolve_document_code обрізає пробіли."""
    assert resolve_document_code("  tir  ") == "tir"


# --- Тести: CARGO_BODY_MODIFIER_UA_TO_NAME ---

@pytest.mark.parametrize("input_name, expected", [
    ("jumbo",          "Jumbo"),
    ("JUMBO",          "Jumbo"),
    ("джамбо",         "Jumbo"),
    ("mega",           "Mega"),
    ("MEGA",           "Mega"),
    ("мега",           "Mega"),
    ("doubledeck",     "Doubledeck"),
    ("DOUBLEDECK",     "Doubledeck"),
    ("дабл",           "Doubledeck"),
    ("двоповерховий",  "Doubledeck"),
    ("двоярусний",     "Doubledeck"),
])
def test_cargo_body_modifier_mapping(input_name, expected):
    """CARGO_BODY_MODIFIER_UA_TO_NAME коректно маппить назви модифікаторів."""
    assert CARGO_BODY_MODIFIER_UA_TO_NAME.get(input_name.lower().strip()) == expected


def test_cargo_body_modifier_unknown_returns_none():
    """Невідомий модифікатор → None."""
    assert CARGO_BODY_MODIFIER_UA_TO_NAME.get("невідомий") is None


# --- Тести: resolve_body_modifier ---

def test_resolve_body_modifier_jumbo():
    """resolve_body_modifier('jumbo') → 'Jumbo'."""
    assert resolve_body_modifier("jumbo") == "Jumbo"


def test_resolve_body_modifier_case_insensitive():
    """resolve_body_modifier регістронезалежний."""
    assert resolve_body_modifier("MEGA") == "Mega"
    assert resolve_body_modifier("Doubledeck") == "Doubledeck"


def test_resolve_body_modifier_unknown_returns_none():
    """resolve_body_modifier з невідомою назвою → None."""
    assert resolve_body_modifier("gigant") is None


# --- Тести: PAYMENT_FORM_UA_TO_ID ---

@pytest.mark.parametrize("name, expected_id", [
    ("готівка",    1),
    ("нал",        1),
    ("нал.",       1),
    ("безготівка", 2),
    ("безнал",     2),
    ("безнал.",    2),
    ("банківський", 2),
    ("перерахунок", 2),
    ("карта",      3),
    ("картка",     3),
])
def test_payment_form_mapping(name, expected_id):
    """PAYMENT_FORM_UA_TO_ID коректно маппить всі форми оплати."""
    assert PAYMENT_FORM_UA_TO_ID.get(name.lower().strip()) == expected_id


def test_resolve_payment_form_gotivka():
    """resolve_payment_form_id('готівка') → 1."""
    assert resolve_payment_form_id("готівка") == 1


def test_resolve_payment_form_bezgotivka():
    """resolve_payment_form_id('безготівка') → 2."""
    assert resolve_payment_form_id("безготівка") == 2


def test_resolve_payment_form_karta():
    """resolve_payment_form_id('карта') → 3."""
    assert resolve_payment_form_id("карта") == 3


def test_resolve_payment_form_unknown_returns_none():
    """resolve_payment_form_id з невідомою назвою → None."""
    assert resolve_payment_form_id("крипта") is None


# --- Тести: PAYMENT_CURRENCY_UA_TO_ID ---

@pytest.mark.parametrize("name, expected_id", [
    ("uah",    4),
    ("UAH",    4),
    ("грн",    4),
    ("гривня", 4),
    ("usd",    1),
    ("USD",    1),
    ("долар",  1),
    ("$",      1),
    ("eur",    2),
    ("EUR",    2),
    ("євро",   2),
    ("€",      2),
    ("інша",   3),
])
def test_payment_currency_mapping(name, expected_id):
    """PAYMENT_CURRENCY_UA_TO_ID коректно маппить всі валюти."""
    assert PAYMENT_CURRENCY_UA_TO_ID.get(name.lower().strip()) == expected_id


def test_resolve_payment_currency_uah():
    """resolve_payment_currency_id('грн') → 4."""
    assert resolve_payment_currency_id("грн") == 4


def test_resolve_payment_currency_usd():
    """resolve_payment_currency_id('USD') → 1."""
    assert resolve_payment_currency_id("USD") == 1


def test_resolve_payment_currency_eur():
    """resolve_payment_currency_id('євро') → 2."""
    assert resolve_payment_currency_id("євро") == 2


def test_resolve_payment_currency_unknown_returns_none():
    """resolve_payment_currency_id з невідомою валютою → None."""
    assert resolve_payment_currency_id("злотий") is None


# --- Тести: PAYMENT_VALUE_TYPE_UA_TO_CODE ---

@pytest.mark.parametrize("name, expected_code", [
    ("всього",      "TOTAL"),
    ("загалом",     "TOTAL"),
    ("за рейс",     "TOTAL"),
    ("total",       "TOTAL"),
    ("за км",       "PER_KM"),
    ("за кілометр", "PER_KM"),
    ("per_km",      "PER_KM"),
    ("per km",      "PER_KM"),
    ("за тонну",    "PER_TON"),
    ("за т",        "PER_TON"),
    ("per_ton",     "PER_TON"),
    ("per ton",     "PER_TON"),
])
def test_payment_value_type_mapping(name, expected_code):
    """PAYMENT_VALUE_TYPE_UA_TO_CODE коректно маппить всі типи ставки."""
    assert PAYMENT_VALUE_TYPE_UA_TO_CODE.get(name.lower().strip()) == expected_code


def test_resolve_payment_value_type_total():
    """resolve_payment_value_type('за рейс') → 'TOTAL'."""
    assert resolve_payment_value_type("за рейс") == "TOTAL"


def test_resolve_payment_value_type_per_km():
    """resolve_payment_value_type('за км') → 'PER_KM'."""
    assert resolve_payment_value_type("за км") == "PER_KM"


def test_resolve_payment_value_type_per_ton():
    """resolve_payment_value_type('за тонну') → 'PER_TON'."""
    assert resolve_payment_value_type("за тонну") == "PER_TON"


def test_resolve_payment_value_type_unknown_returns_none():
    """resolve_payment_value_type з невідомим типом → None."""
    assert resolve_payment_value_type("за літр") is None
