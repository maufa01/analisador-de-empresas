# Equity Research App

Análisis fundamental + DCF + múltiplos comparables + optimización Markowitz.

## Quick start

```bash

pip install -r requirements.txt

# Demo CLI
python main.py
python main.py --ticker MSFT --peers GOOGL,AAPL,META

# Dashboard Streamlit
streamlit run app.py
```

## Arquitectura

```
fetcher.py       Capa de acceso a datos (yfinance encapsulado)
ratios.py        Cálculo de ratios + alias resolver
dcf.py           DCF de dos etapas + WACC + sensibilidad
comparables.py   Múltiplos de peers + precio implícito
scoring.py       Score 0-100 + rating BUY/HOLD/SELL
markowitz.py     Frontera eficiente + max Sharpe + min vol
config.py        Defaults y supuestos centralizados
app.py           Streamlit dashboard
main.py          Demo CLI
```

Diseño plano (un archivo = un módulo). Cada módulo es **independiente**: podés
cambiar `fetcher.py` para usar Alpha Vantage o FMP sin tocar nada más.

## Supuestos explícitos

Centralizados en `config.py`:

| Parámetro              | Default | Justificación                          |
|------------------------|---------|----------------------------------------|
| Risk-free rate         | 4.5%    | 10Y Treasury aprox.                    |
| Equity Risk Premium    | 5.5%    | ERP histórico USA (Damodaran)          |
| Tax rate               | 25%     | Blended corporate USA                  |
| Cost of debt (pre-tax) | 5%      | Investment grade corporate aprox.      |
| Weight equity / debt   | 70/30   | Capital structure típica               |
| Beta default           | 1.0     | Override con `info.beta` si está       |
| Terminal growth        | 2.5%    | ~Inflación LP USA                      |
| Years de proyección    | 5       | Estándar equity research               |
| Growth cap             | [-5%, +20%] | Evita extrapolar booms transitorios |

**Cálculos clave:**

- `FCF = Operating Cash Flow + Capex` (capex viene negativo en yfinance)
- `Net Debt = Total Debt − Cash & Equivalents`
- `WACC = (E/V)·Re + (D/V)·Rd·(1−t)` con `Re = Rf + β·ERP` (CAPM)
- `Terminal Value = FCF_n+1 / (WACC − g)` (Gordon)
- `Markowitz`: log-retornos diarios anualizados ×252; SLSQP de scipy

**Resolver de aliases:** yfinance no es consistente con los nombres de
cuentas (e.g. `Stockholders Equity` vs `Total Stockholder Equity`).
`ratios.py` busca por aliases ordenados por preferencia.

## Manejo de errores y casos borde

- FCF negativo → DCF se rechaza con mensaje claro (usar comparables o
  normalizar FCF manualmente)
- WACC ≤ g terminal → ValueError (Gordon explota)
- Cuentas faltantes → la columna se omite, no crashea
- Peer rate-limited → se skipea y se sigue con los que respondieron
- `t.info` falla por rate-limit → degradamos a precio del history
- shares outstanding ausente → DCF imposible, se reporta

## Extensibilidad

**Cambiar provider de datos:** edita `fetcher.py`. Mientras devuelvas un
`CompanyData` con income/balance/cash en formato pandas DataFrame
(índice datetime, columnas = cuentas), todo lo demás sigue funcionando.

**Sumar un múltiplo nuevo:** agregalo en `comparables.compute_multiples()`
y en la lista `multiples_cols` de `comparables_model()`.

**Calibrar scoring por sector:** los rangos de `_normalize()` en
`scoring.py` están hardcoded. Para producción real, calibrá por sector
(e.g. ROE > 25% es excelente para retail pero típico en software).

**Sumar un nuevo modelo de valuación** (e.g. residual income, DDM):
agregá un módulo nuevo, calculá un intrínseco, y promedialo en `app.py`.
