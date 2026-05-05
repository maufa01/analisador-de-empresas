"""
Demo programático: análisis fundamental de Apple.

Run:
    python main.py
    python main.py --ticker MSFT --peers GOOGL,AAPL,META
"""
import argparse
import sys

import pandas as pd

from fetcher import fetch_data, fetch_peers
from ratios import calculate_ratios
from dcf import dcf_model, build_dcf_inputs_from_company, calculate_wacc
from comparables import comparables_model
from scoring import scoring_model


def run(ticker: str = "AAPL", peers: list[str] | None = None) -> dict:
    peers = peers or ["MSFT", "GOOGL", "META"]
    
    print(f"\n{'='*70}")
    print(f"Análisis Fundamental — {ticker}")
    print(f"Peers: {', '.join(peers)}")
    print(f"{'='*70}")

    target = fetch_data(ticker)
    peers_data = list(fetch_peers(peers).values())
    print(f"✔ Data fetched (target + {len(peers_data)} peers)")

    # 1) Ratios
    ratios = calculate_ratios(target.income_stmt, target.balance_sheet, target.cash_flow)
    print(f"\n--- RATIOS (últimos {min(3, len(ratios))} períodos) ---")
    print(ratios.tail(3).to_string())

    # 2) WACC + DCF
    beta = target.beta or 1.20
    wacc = calculate_wacc(
        beta=beta, risk_free=0.045, market_premium=0.055,
        cost_of_debt=0.05, tax_rate=0.21,
        weight_equity=0.85, weight_debt=0.15,
    )
    print(f"\n--- WACC ---")
    print(f"Beta usado: {beta:.2f}")
    print(f"WACC: {wacc:.2%}")

    dcf_inputs = build_dcf_inputs_from_company(
        target, wacc=wacc, terminal_growth=0.025, projection_years=5,
    )
    dcf_res = dcf_model(dcf_inputs)
    print(f"\n--- DCF ---")
    print(f"Growth aplicado: {dcf_res.growth_used:.2%}")
    print(f"Enterprise Value:  ${dcf_res.enterprise_value/1e9:>10,.1f}B")
    print(f"Equity Value:      ${dcf_res.equity_value/1e9:>10,.1f}B")
    print(f"Intrínseco/acción: ${dcf_res.intrinsic_per_share:>10,.2f}")

    # 3) Comparables
    comps = comparables_model(target, peers_data)
    print(f"\n--- COMPARABLES ---")
    print("Múltiplos del peer group (median):")
    print(comps["peer_stats"].T.round(2).to_string())
    print("\nPrecios implícitos:")
    print(comps["implied_prices"].round(2).to_string())
    print(f"Promedio implícito: ${comps['average_implied']:.2f}")

    # 4) Intrínseco promedio + scoring
    intrinsic_avg = (dcf_res.intrinsic_per_share + comps["average_implied"]) / 2
    score = scoring_model(ratios, target.current_price, intrinsic_avg)

    print(f"\n--- VEREDICTO ---")
    print(f"Precio actual:        ${target.current_price:>8,.2f}")
    print(f"Intrínseco DCF:       ${dcf_res.intrinsic_per_share:>8,.2f}")
    print(f"Intrínseco comps:     ${comps['average_implied']:>8,.2f}")
    print(f"Intrínseco promedio:  ${intrinsic_avg:>8,.2f}")
    print(f"Upside:               {score['upside']*100:>+8,.1f}%")
    print(f"Score:                {score['score']:>8.1f} / 100")
    print(f"  - Growth:           {score['components']['growth']:>8.1f}")
    print(f"  - Profitability:    {score['components']['profitability']:>8.1f}")
    print(f"  - Solvency:         {score['components']['solvency']:>8.1f}")
    print(f"  - Valuation:        {score['components']['valuation']:>8.1f}")
    print(f"\nRATING: {score['rating']}")
    print(f"{'='*70}\n")

    return {
        "ratios": ratios,
        "dcf": dcf_res,
        "comparables": comps,
        "scoring": score,
        "intrinsic_avg": intrinsic_avg,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument(
        "--peers", default="MSFT,GOOGL,META",
        help="Lista de peers separada por comas",
    )
    args = parser.parse_args()
    peers = [p.strip().upper() for p in args.peers.split(",") if p.strip()]
    
    try:
        run(args.ticker, peers)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
