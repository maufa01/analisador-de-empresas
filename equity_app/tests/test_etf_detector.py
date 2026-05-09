from analysis.etf_detector import detect_fund, is_fund_quick


def test_known_etfs_are_detected():
    for t in ["SPY", "QQQ", "VOO", "ARKK", "TLT"]:
        assert is_fund_quick(t), f"{t} should be detected"


def test_operating_companies_not_flagged():
    for t in ["AAPL", "MSFT", "GOOG", "AMZN", "JNJ", "KO", "JPM"]:
        assert not is_fund_quick(t), f"{t} should NOT be flagged as fund"


def test_fmp_isEtf_flag_wins():
    fmp_profile = {"isEtf": True, "companyName": "Some Mystery Ticker"}
    result = detect_fund("XYZ", fmp_profile=fmp_profile)
    assert result.is_fund is True
    assert result.confidence == 1.0
    assert result.method == "fmp_isEtf"


def test_yf_quoteType_etf():
    yf_info = {"quoteType": "ETF", "longName": "Some ETF Inc"}
    result = detect_fund("XYZ", yf_info=yf_info)
    assert result.is_fund is True
    assert result.confidence == 1.0


def test_name_heuristic_lower_confidence():
    yf_info = {"longName": "Fancy Sector Index Trust"}
    result = detect_fund("FSIT", yf_info=yf_info)
    assert result.is_fund is True
    assert result.confidence < 1.0


def test_aapl_not_flagged_with_real_data():
    fmp_profile = {
        "companyName": "Apple Inc.",
        "isEtf": False,
        "isFund": False,
    }
    yf_info = {"quoteType": "EQUITY", "longName": "Apple Inc."}
    result = detect_fund("AAPL", fmp_profile=fmp_profile, yf_info=yf_info)
    assert result.is_fund is False
