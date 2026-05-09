from analysis.bank_detector import detect_bank, is_bank_quick


def test_known_banks_detected():
    for t in ["JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC"]:
        assert is_bank_quick(t), f"{t} should be detected as bank"


def test_never_block_overrides_known():
    """V (Visa) and friends must be whitelisted."""
    for t in ["V", "MA", "PYPL", "BLK", "BX", "ICE", "CME", "BRK.B"]:
        assert not is_bank_quick(t), f"{t} should NOT be flagged as bank"


def test_industry_bank_diversified():
    yf_info = {"industry": "Banks - Diversified"}
    result = detect_bank("UNKNOWN", yf_info=yf_info)
    assert result.is_bank is True
    assert result.confidence == 1.0


def test_industry_capital_markets_not_bank():
    yf_info = {"industry": "Capital Markets"}
    result = detect_bank("UNKNOWN", yf_info=yf_info)
    assert result.is_bank is False


def test_aapl_not_bank():
    fmp_profile = {"sector": "Technology", "industry": "Consumer Electronics"}
    result = detect_bank("AAPL", fmp_profile=fmp_profile)
    assert result.is_bank is False


def test_visa_not_bank_via_industry():
    fmp_profile = {"sector": "Financial Services", "industry": "Credit Services"}
    result = detect_bank("V", fmp_profile=fmp_profile)
    assert result.is_bank is False  # V está en NEVER_BLOCK_AS_BANK
