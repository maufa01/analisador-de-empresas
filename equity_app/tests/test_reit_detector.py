from analysis.reit_detector import detect_reit, is_reit_quick


def test_known_reits_detected():
    for t in ["AMT", "PLD", "EQIX", "WELL", "PSA", "O", "VICI", "SPG"]:
        assert is_reit_quick(t), f"{t} should be detected as REIT"


def test_industry_signal():
    fmp_profile = {"industry": "REIT - Industrial"}
    result = detect_reit("UNKNOWN", fmp_profile=fmp_profile)
    assert result.is_reit is True
    assert result.confidence == 1.0


def test_sector_real_estate_signal():
    yf_info = {"sector": "Real Estate", "marketCap": 50_000_000_000}
    result = detect_reit("UNKNOWN", yf_info=yf_info)
    assert result.is_reit is True
    assert result.confidence >= 0.9


def test_aapl_not_reit():
    fmp_profile = {"sector": "Technology", "industry": "Consumer Electronics"}
    result = detect_reit("AAPL", fmp_profile=fmp_profile)
    assert result.is_reit is False


def test_residential_construction_not_reit():
    """DHI / LEN are real estate developers, not REITs."""
    fmp_profile = {"sector": "Consumer Cyclical", "industry": "Residential Construction"}
    result = detect_reit("DHI", fmp_profile=fmp_profile)
    assert result.is_reit is False
