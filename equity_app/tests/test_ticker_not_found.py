"""
Tests verifying the LITERAL error message contract.

Requirements section 3, rule #1:
    "perdone, no se agrego la accion"

NO accents. NO suggestions. NO extra text. NO trailing punctuation beyond
what is in the literal. These tests FAIL the build if anyone ever changes
the wording — that is the entire point.
"""
from __future__ import annotations
import re
import pytest

from core.exceptions import TickerNotFoundError
from core.constants import TICKER_NOT_FOUND_MESSAGE


# The literal as specified in the requirements — DO NOT EDIT.
EXPECTED: str = "perdone, no se agrego la accion"


# ============================================================
# Constant
# ============================================================
class TestConstant:

    def test_exact_literal(self):
        assert TICKER_NOT_FOUND_MESSAGE == EXPECTED

    def test_no_accents(self):
        forbidden = set("áéíóúüÁÉÍÓÚÜñÑ¡¿")
        assert not (set(TICKER_NOT_FOUND_MESSAGE) & forbidden), (
            "Constant must contain NO Spanish accents/diacritics"
        )

    def test_no_uppercase_first_letter(self):
        # Specified literal is fully lowercase — preserve.
        assert TICKER_NOT_FOUND_MESSAGE[0].islower()

    def test_no_trailing_punctuation_beyond_literal(self):
        assert not TICKER_NOT_FOUND_MESSAGE.endswith(".")
        assert not TICKER_NOT_FOUND_MESSAGE.endswith("!")
        assert not TICKER_NOT_FOUND_MESSAGE.endswith("?")

    def test_byte_length(self):
        # The exact expected ASCII byte length (defensive against silent
        # invisible characters such as zero-width spaces).
        assert len(TICKER_NOT_FOUND_MESSAGE.encode("utf-8")) == len(EXPECTED)


# ============================================================
# Exception
# ============================================================
class TestTickerNotFoundError:

    def test_str_returns_literal(self):
        err = TickerNotFoundError()
        assert str(err) == EXPECTED

    def test_str_with_internal_ticker_does_not_leak(self):
        # Caller may pass internal context; user-facing str() must NOT
        # include it.
        err = TickerNotFoundError(ticker="ZZZZ-NOT-EXIST")
        assert str(err) == EXPECTED
        assert "ZZZZ" not in str(err)

    def test_str_with_original_does_not_leak(self):
        err = TickerNotFoundError(ticker="X", original=ValueError("internal cause"))
        assert str(err) == EXPECTED
        assert "internal" not in str(err)

    def test_user_message_attribute(self):
        err = TickerNotFoundError()
        assert err.user_message == EXPECTED

    def test_args_first_is_literal(self):
        err = TickerNotFoundError()
        assert err.args[0] == EXPECTED

    def test_no_forbidden_words(self):
        text = str(TickerNotFoundError())
        forbidden = [
            "intente", "intentar", "verifique", "verificar",
            "alternativ", "sugerenc", "ticker", "symbol",
            "por favor", "ayuda", "disculpe",
        ]
        lo = text.lower()
        for f in forbidden:
            assert f not in lo, f"Forbidden token in user message: {f!r}"

    def test_does_not_match_extended_pattern(self):
        # Extra-defensive: any chars beyond the exact literal => fail.
        assert re.fullmatch(re.escape(EXPECTED), str(TickerNotFoundError()))


# ============================================================
# Raise / catch
# ============================================================
def test_can_be_raised_and_caught():
    with pytest.raises(TickerNotFoundError) as exc_info:
        raise TickerNotFoundError(ticker="ZZZZ")
    assert str(exc_info.value) == EXPECTED


def test_inherits_from_equity_app_error():
    from core.exceptions import EquityAppError
    assert issubclass(TickerNotFoundError, EquityAppError)
