"""Static reference data: instrument universe, fund domiciles, WHT treaty matrix.

All synthetic. Real-looking tickers are used for recognizability; all prices,
holdings and corporate actions are randomly generated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


# ----------------------------------------------------------------------------
# Instrument universe
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class InstrumentRef:
    instrument_id: str
    ticker: str
    name: str
    type: str           # EQUITY | BOND
    ccy: str
    country: str        # ISO-2
    sector: str
    universe_tag: str
    coupon_rate: float | None = None
    coupon_freq: int | None = None
    maturity_date: date | None = None
    face_value: float | None = None
    initial_price: float = 100.0  # equity start price; bonds use clean price


# Sectors: TECH, FIN, HC, COND (cons disc), CONS (cons staples), IND, ENG,
# MAT, UTL, COMM, RE
US_LARGE: tuple[InstrumentRef, ...] = (
    InstrumentRef("EQ_US_AAPL",  "AAPL",  "Apple Inc",                "EQUITY", "USD", "US", "TECH",  "US_LARGE", initial_price=185.20),
    InstrumentRef("EQ_US_MSFT",  "MSFT",  "Microsoft Corp",           "EQUITY", "USD", "US", "TECH",  "US_LARGE", initial_price=412.50),
    InstrumentRef("EQ_US_GOOGL", "GOOGL", "Alphabet Inc Class A",     "EQUITY", "USD", "US", "COMM",  "US_LARGE", initial_price=145.80),
    InstrumentRef("EQ_US_AMZN",  "AMZN",  "Amazon.com Inc",           "EQUITY", "USD", "US", "COND",  "US_LARGE", initial_price=158.30),
    InstrumentRef("EQ_US_META",  "META",  "Meta Platforms Inc",       "EQUITY", "USD", "US", "COMM",  "US_LARGE", initial_price=485.10),
    InstrumentRef("EQ_US_NVDA",  "NVDA",  "NVIDIA Corp",              "EQUITY", "USD", "US", "TECH",  "US_LARGE", initial_price=620.40),
    InstrumentRef("EQ_US_TSLA",  "TSLA",  "Tesla Inc",                "EQUITY", "USD", "US", "COND",  "US_LARGE", initial_price=215.70),
    InstrumentRef("EQ_US_JPM",   "JPM",   "JPMorgan Chase & Co",      "EQUITY", "USD", "US", "FIN",   "US_LARGE", initial_price=192.40),
    InstrumentRef("EQ_US_BAC",   "BAC",   "Bank of America Corp",     "EQUITY", "USD", "US", "FIN",   "US_LARGE", initial_price=37.85),
    InstrumentRef("EQ_US_V",     "V",     "Visa Inc",                 "EQUITY", "USD", "US", "FIN",   "US_LARGE", initial_price=275.30),
    InstrumentRef("EQ_US_MA",    "MA",    "Mastercard Inc",           "EQUITY", "USD", "US", "FIN",   "US_LARGE", initial_price=465.10),
    InstrumentRef("EQ_US_JNJ",   "JNJ",   "Johnson & Johnson",        "EQUITY", "USD", "US", "HC",    "US_LARGE", initial_price=158.20),
    InstrumentRef("EQ_US_UNH",   "UNH",   "UnitedHealth Group Inc",   "EQUITY", "USD", "US", "HC",    "US_LARGE", initial_price=512.00),
    InstrumentRef("EQ_US_PFE",   "PFE",   "Pfizer Inc",               "EQUITY", "USD", "US", "HC",    "US_LARGE", initial_price=28.95),
    InstrumentRef("EQ_US_LLY",   "LLY",   "Eli Lilly & Co",           "EQUITY", "USD", "US", "HC",    "US_LARGE", initial_price=748.30),
    InstrumentRef("EQ_US_XOM",   "XOM",   "ExxonMobil Corp",          "EQUITY", "USD", "US", "ENG",   "US_LARGE", initial_price=108.40),
    InstrumentRef("EQ_US_CVX",   "CVX",   "Chevron Corp",             "EQUITY", "USD", "US", "ENG",   "US_LARGE", initial_price=152.10),
    InstrumentRef("EQ_US_WMT",   "WMT",   "Walmart Inc",              "EQUITY", "USD", "US", "CONS",  "US_LARGE", initial_price=168.90),
    InstrumentRef("EQ_US_PG",    "PG",    "Procter & Gamble Co",      "EQUITY", "USD", "US", "CONS",  "US_LARGE", initial_price=158.40),
    InstrumentRef("EQ_US_KO",    "KO",    "Coca-Cola Co",             "EQUITY", "USD", "US", "CONS",  "US_LARGE", initial_price=62.30),
    InstrumentRef("EQ_US_HD",    "HD",    "Home Depot Inc",           "EQUITY", "USD", "US", "COND",  "US_LARGE", initial_price=384.20),
    InstrumentRef("EQ_US_DIS",   "DIS",   "Walt Disney Co",           "EQUITY", "USD", "US", "COMM",  "US_LARGE", initial_price=108.70),
    InstrumentRef("EQ_US_NEE",   "NEE",   "NextEra Energy Inc",       "EQUITY", "USD", "US", "UTL",   "US_LARGE", initial_price=72.50),
    InstrumentRef("EQ_US_BA",    "BA",    "Boeing Co",                "EQUITY", "USD", "US", "IND",   "US_LARGE", initial_price=210.30),
    InstrumentRef("EQ_US_CAT",   "CAT",   "Caterpillar Inc",          "EQUITY", "USD", "US", "IND",   "US_LARGE", initial_price=362.80),
)

EU_LARGE: tuple[InstrumentRef, ...] = (
    InstrumentRef("EQ_EU_ASML",  "ASML.AS",  "ASML Holding NV",        "EQUITY", "EUR", "NL", "TECH",  "EU_LARGE", initial_price=945.30),
    InstrumentRef("EQ_EU_SAP",   "SAP.DE",   "SAP SE",                 "EQUITY", "EUR", "DE", "TECH",  "EU_LARGE", initial_price=205.40),
    InstrumentRef("EQ_EU_SIE",   "SIE.DE",   "Siemens AG",             "EQUITY", "EUR", "DE", "IND",   "EU_LARGE", initial_price=178.20),
    InstrumentRef("EQ_EU_NESN",  "NESN.SW",  "Nestle SA",              "EQUITY", "CHF", "CH", "CONS",  "EU_LARGE", initial_price=92.50),
    InstrumentRef("EQ_EU_ROG",   "ROG.SW",   "Roche Holding AG",       "EQUITY", "CHF", "CH", "HC",    "EU_LARGE", initial_price=248.10),
    InstrumentRef("EQ_EU_NOVN",  "NOVN.SW",  "Novartis AG",            "EQUITY", "CHF", "CH", "HC",    "EU_LARGE", initial_price=92.80),
    InstrumentRef("EQ_EU_MC",    "MC.PA",    "LVMH Moet Hennessy",     "EQUITY", "EUR", "FR", "COND",  "EU_LARGE", initial_price=780.40),
    InstrumentRef("EQ_EU_OR",    "OR.PA",    "L'Oreal SA",             "EQUITY", "EUR", "FR", "CONS",  "EU_LARGE", initial_price=412.20),
    InstrumentRef("EQ_EU_TTE",   "TTE.PA",   "TotalEnergies SE",       "EQUITY", "EUR", "FR", "ENG",   "EU_LARGE", initial_price=62.80),
    InstrumentRef("EQ_EU_SAN_FR","SAN.PA",   "Sanofi SA",              "EQUITY", "EUR", "FR", "HC",    "EU_LARGE", initial_price=92.40),
    InstrumentRef("EQ_EU_AIR",   "AIR.PA",   "Airbus SE",              "EQUITY", "EUR", "FR", "IND",   "EU_LARGE", initial_price=145.80),
    InstrumentRef("EQ_EU_SHEL",  "SHEL.L",   "Shell PLC",              "EQUITY", "GBP", "GB", "ENG",   "EU_LARGE", initial_price=27.85),
    InstrumentRef("EQ_EU_AZN",   "AZN.L",    "AstraZeneca PLC",        "EQUITY", "GBP", "GB", "HC",    "EU_LARGE", initial_price=105.30),
    InstrumentRef("EQ_EU_HSBA",  "HSBA.L",   "HSBC Holdings PLC",      "EQUITY", "GBP", "GB", "FIN",   "EU_LARGE", initial_price=6.42),
    InstrumentRef("EQ_EU_ULVR",  "ULVR.L",   "Unilever PLC",           "EQUITY", "GBP", "GB", "CONS",  "EU_LARGE", initial_price=39.50),
    InstrumentRef("EQ_EU_BARC",  "BARC.L",   "Barclays PLC",           "EQUITY", "GBP", "GB", "FIN",   "EU_LARGE", initial_price=2.05),
    InstrumentRef("EQ_EU_BP",    "BP.L",     "BP PLC",                 "EQUITY", "GBP", "GB", "ENG",   "EU_LARGE", initial_price=4.85),
    InstrumentRef("EQ_EU_SAN_ES","SAN.MC",   "Banco Santander SA",     "EQUITY", "EUR", "ES", "FIN",   "EU_LARGE", initial_price=4.32),
    InstrumentRef("EQ_EU_ITX",   "ITX.MC",   "Industria de Diseno",    "EQUITY", "EUR", "ES", "COND",  "EU_LARGE", initial_price=42.10),
)

JP_LARGE: tuple[InstrumentRef, ...] = (
    InstrumentRef("EQ_JP_TOYOTA","7203.T",   "Toyota Motor Corp",      "EQUITY", "JPY", "JP", "IND",   "JP_LARGE", initial_price=2820.0),
    InstrumentRef("EQ_JP_SONY",  "6758.T",   "Sony Group Corp",        "EQUITY", "JPY", "JP", "COMM",  "JP_LARGE", initial_price=12850.0),
    InstrumentRef("EQ_JP_SOFTB", "9984.T",   "SoftBank Group Corp",    "EQUITY", "JPY", "JP", "COMM",  "JP_LARGE", initial_price=9420.0),
    InstrumentRef("EQ_JP_KEYEN", "6861.T",   "Keyence Corp",           "EQUITY", "JPY", "JP", "TECH",  "JP_LARGE", initial_price=68450.0),
    InstrumentRef("EQ_JP_TOKYO", "8035.T",   "Tokyo Electron Ltd",     "EQUITY", "JPY", "JP", "TECH",  "JP_LARGE", initial_price=37200.0),
    InstrumentRef("EQ_JP_NTT",   "9432.T",   "Nippon Telegraph",       "EQUITY", "JPY", "JP", "COMM",  "JP_LARGE", initial_price=178.5),
    InstrumentRef("EQ_JP_RECRT", "6098.T",   "Recruit Holdings",       "EQUITY", "JPY", "JP", "IND",   "JP_LARGE", initial_price=8240.0),
    InstrumentRef("EQ_JP_SHINE", "4063.T",   "Shin-Etsu Chemical",     "EQUITY", "JPY", "JP", "MAT",   "JP_LARGE", initial_price=6180.0),
    InstrumentRef("EQ_JP_MUFG",  "8306.T",   "Mitsubishi UFJ Financial","EQUITY","JPY", "JP", "FIN",   "JP_LARGE", initial_price=1485.0),
    InstrumentRef("EQ_JP_NINTE", "7974.T",   "Nintendo Co Ltd",        "EQUITY", "JPY", "JP", "COMM",  "JP_LARGE", initial_price=8420.0),
    InstrumentRef("EQ_JP_NIDEC", "6594.T",   "Nidec Corp",             "EQUITY", "JPY", "JP", "IND",   "JP_LARGE", initial_price=5840.0),
    InstrumentRef("EQ_JP_TAKED", "4502.T",   "Takeda Pharmaceutical",  "EQUITY", "JPY", "JP", "HC",    "JP_LARGE", initial_price=4120.0),
)

EM_EQUITY: tuple[InstrumentRef, ...] = (
    InstrumentRef("EQ_EM_TSMC",  "2330.TW",  "Taiwan Semiconductor",   "EQUITY", "TWD", "TW", "TECH",  "EM_EQUITY", initial_price=720.0),
    InstrumentRef("EQ_EM_SAMSU", "005930.KS","Samsung Electronics",    "EQUITY", "KRW", "KR", "TECH",  "EM_EQUITY", initial_price=78500.0),
    InstrumentRef("EQ_EM_TENC",  "0700.HK",  "Tencent Holdings",       "EQUITY", "HKD", "HK", "TECH",  "EM_EQUITY", initial_price=378.0),
    InstrumentRef("EQ_EM_BABA",  "9988.HK",  "Alibaba Group",          "EQUITY", "HKD", "HK", "COND",  "EM_EQUITY", initial_price=82.50),
    InstrumentRef("EQ_EM_AIA",   "1299.HK",  "AIA Group Ltd",          "EQUITY", "HKD", "HK", "FIN",   "EM_EQUITY", initial_price=68.40),
    InstrumentRef("EQ_EM_MEITU", "3690.HK",  "Meituan",                "EQUITY", "HKD", "HK", "COND",  "EM_EQUITY", initial_price=92.20),
    InstrumentRef("EQ_EM_RELI",  "RELIANCE.NS","Reliance Industries",  "EQUITY", "INR", "IN", "ENG",   "EM_EQUITY", initial_price=2680.0),
    InstrumentRef("EQ_EM_TCS",   "TCS.NS",   "Tata Consultancy",       "EQUITY", "INR", "IN", "TECH",  "EM_EQUITY", initial_price=3850.0),
    InstrumentRef("EQ_EM_INFY",  "INFY.NS",  "Infosys Ltd",            "EQUITY", "INR", "IN", "TECH",  "EM_EQUITY", initial_price=1620.0),
    InstrumentRef("EQ_EM_HDFCB", "HDFCBANK.NS","HDFC Bank Ltd",        "EQUITY", "INR", "IN", "FIN",   "EM_EQUITY", initial_price=1485.0),
    InstrumentRef("EQ_EM_VALE",  "VALE3.SA", "Vale SA",                "EQUITY", "BRL", "BR", "MAT",   "EM_EQUITY", initial_price=68.40),
    InstrumentRef("EQ_EM_PETR",  "PETR4.SA", "Petroleo Brasileiro",    "EQUITY", "BRL", "BR", "ENG",   "EM_EQUITY", initial_price=38.20),
    InstrumentRef("EQ_EM_ITUB",  "ITUB4.SA", "Itau Unibanco Holding",  "EQUITY", "BRL", "BR", "FIN",   "EM_EQUITY", initial_price=32.50),
    InstrumentRef("EQ_EM_AMXL",  "AMXL.MX",  "America Movil",          "EQUITY", "MXN", "MX", "COMM",  "EM_EQUITY", initial_price=15.20),
    InstrumentRef("EQ_EM_WALMX", "WALMEX.MX","Walmart de Mexico",      "EQUITY", "MXN", "MX", "CONS",  "EM_EQUITY", initial_price=68.50),
    InstrumentRef("EQ_EM_NPN",   "NPN.JO",   "Naspers Ltd",            "EQUITY", "ZAR", "ZA", "COMM",  "EM_EQUITY", initial_price=3420.0),
    InstrumentRef("EQ_EM_FSR",   "FSR.JO",   "FirstRand Ltd",          "EQUITY", "ZAR", "ZA", "FIN",   "EM_EQUITY", initial_price=78.40),
)

# Nordic small-caps: fictional names to avoid the obscurity of real micro-caps.
NORDIC_SMALL: tuple[InstrumentRef, ...] = (
    InstrumentRef("EQ_NS_SKOG",  "SKOG.ST",  "Skogsindustri AB",       "EQUITY", "SEK", "SE", "MAT",   "NORDIC_SMALL", initial_price=142.50),
    InstrumentRef("EQ_NS_LITH",  "LITH.ST",  "Lithiumstad AB",         "EQUITY", "SEK", "SE", "MAT",   "NORDIC_SMALL", initial_price=68.20),
    InstrumentRef("EQ_NS_BERG",  "BERG.OL",  "Bergverk Norden ASA",    "EQUITY", "NOK", "NO", "MAT",   "NORDIC_SMALL", initial_price=215.30),
    InstrumentRef("EQ_NS_MARI",  "MARI.OL",  "Maritim Drift ASA",      "EQUITY", "NOK", "NO", "IND",   "NORDIC_SMALL", initial_price=84.50),
    InstrumentRef("EQ_NS_VIND",  "VIND.CO",  "Vindkraft Danmark A/S",  "EQUITY", "DKK", "DK", "UTL",   "NORDIC_SMALL", initial_price=185.20),
    InstrumentRef("EQ_NS_PHAR",  "PHAR.HE",  "Pharma Helsinki Oy",     "EQUITY", "EUR", "FI", "HC",    "NORDIC_SMALL", initial_price=22.40),
    InstrumentRef("EQ_NS_NORD",  "NORD.OL",  "Nordlys Tech ASA",       "EQUITY", "NOK", "NO", "TECH",  "NORDIC_SMALL", initial_price=312.80),
    InstrumentRef("EQ_NS_STOR",  "STOR.ST",  "Stockholm Robotics AB",  "EQUITY", "SEK", "SE", "TECH",  "NORDIC_SMALL", initial_price=98.50),
)

# Investment-grade corporate bonds. Coupons annual, paid semi-annually.
# Initial price = clean price per 100 face. Most start near par.
IG_BONDS: tuple[InstrumentRef, ...] = (
    InstrumentRef("BND_USD_AAPL_2031", "AAPL_3.85_2031", "Apple Inc 3.85% 2031",
                  "BOND", "USD", "US", "TECH", "IG_BOND",
                  coupon_rate=0.0385, coupon_freq=2, maturity_date=date(2031, 8, 4),
                  face_value=100.0, initial_price=98.40),
    InstrumentRef("BND_USD_MSFT_2032", "MSFT_4.25_2032", "Microsoft Corp 4.25% 2032",
                  "BOND", "USD", "US", "TECH", "IG_BOND",
                  coupon_rate=0.0425, coupon_freq=2, maturity_date=date(2032, 6, 1),
                  face_value=100.0, initial_price=99.85),
    InstrumentRef("BND_USD_IBM_2030",  "IBM_4.50_2030",  "IBM Corp 4.50% 2030",
                  "BOND", "USD", "US", "TECH", "IG_BOND",
                  coupon_rate=0.0450, coupon_freq=2, maturity_date=date(2030, 5, 15),
                  face_value=100.0, initial_price=100.20),
    InstrumentRef("BND_USD_JNJ_2030",  "JNJ_4.00_2030",  "Johnson & Johnson 4.00% 2030",
                  "BOND", "USD", "US", "HC", "IG_BOND",
                  coupon_rate=0.0400, coupon_freq=2, maturity_date=date(2030, 9, 15),
                  face_value=100.0, initial_price=99.10),
    InstrumentRef("BND_USD_WMT_2028",  "WMT_3.90_2028",  "Walmart Inc 3.90% 2028",
                  "BOND", "USD", "US", "CONS", "IG_BOND",
                  coupon_rate=0.0390, coupon_freq=2, maturity_date=date(2028, 9, 9),
                  face_value=100.0, initial_price=98.60),
    InstrumentRef("BND_USD_VZ_2033",   "VZ_5.00_2033",   "Verizon Comms 5.00% 2033",
                  "BOND", "USD", "US", "COMM", "IG_BOND",
                  coupon_rate=0.0500, coupon_freq=2, maturity_date=date(2033, 4, 22),
                  face_value=100.0, initial_price=101.30),
    InstrumentRef("BND_USD_T_2032",    "T_4.75_2032",    "AT&T Inc 4.75% 2032",
                  "BOND", "USD", "US", "COMM", "IG_BOND",
                  coupon_rate=0.0475, coupon_freq=2, maturity_date=date(2032, 11, 15),
                  face_value=100.0, initial_price=99.45),
    InstrumentRef("BND_USD_KO_2030",   "KO_4.20_2030",   "Coca-Cola Co 4.20% 2030",
                  "BOND", "USD", "US", "CONS", "IG_BOND",
                  coupon_rate=0.0420, coupon_freq=2, maturity_date=date(2030, 6, 1),
                  face_value=100.0, initial_price=99.80),
    InstrumentRef("BND_USD_DIS_2031",  "DIS_4.50_2031",  "Walt Disney Co 4.50% 2031",
                  "BOND", "USD", "US", "COMM", "IG_BOND",
                  coupon_rate=0.0450, coupon_freq=2, maturity_date=date(2031, 3, 15),
                  face_value=100.0, initial_price=100.05),
    InstrumentRef("BND_USD_GS_2031",   "GS_5.25_2031",   "Goldman Sachs 5.25% 2031",
                  "BOND", "USD", "US", "FIN", "IG_BOND",
                  coupon_rate=0.0525, coupon_freq=2, maturity_date=date(2031, 7, 21),
                  face_value=100.0, initial_price=102.40),
    InstrumentRef("BND_USD_BAC_2030",  "BAC_4.85_2030",  "Bank of America 4.85% 2030",
                  "BOND", "USD", "US", "FIN", "IG_BOND",
                  coupon_rate=0.0485, coupon_freq=2, maturity_date=date(2030, 4, 19),
                  face_value=100.0, initial_price=100.65),
    InstrumentRef("BND_USD_JPM_2031",  "JPM_5.00_2031",  "JPMorgan Chase 5.00% 2031",
                  "BOND", "USD", "US", "FIN", "IG_BOND",
                  coupon_rate=0.0500, coupon_freq=2, maturity_date=date(2031, 1, 23),
                  face_value=100.0, initial_price=101.10),
    InstrumentRef("BND_EUR_BMW_2028",  "BMW_3.75_2028",  "BMW AG 3.75% 2028",
                  "BOND", "EUR", "DE", "COND", "IG_BOND",
                  coupon_rate=0.0375, coupon_freq=2, maturity_date=date(2028, 5, 12),
                  face_value=100.0, initial_price=99.30),
    InstrumentRef("BND_EUR_BAS_2029",  "BAS_3.50_2029",  "BASF SE 3.50% 2029",
                  "BOND", "EUR", "DE", "MAT", "IG_BOND",
                  coupon_rate=0.0350, coupon_freq=1, maturity_date=date(2029, 6, 18),
                  face_value=100.0, initial_price=98.80),
    InstrumentRef("BND_EUR_VW_2030",   "VW_4.00_2030",   "Volkswagen AG 4.00% 2030",
                  "BOND", "EUR", "DE", "COND", "IG_BOND",
                  coupon_rate=0.0400, coupon_freq=1, maturity_date=date(2030, 4, 4),
                  face_value=100.0, initial_price=99.85),
    InstrumentRef("BND_EUR_TTE_2031",  "TTE_3.60_2031",  "TotalEnergies 3.60% 2031",
                  "BOND", "EUR", "FR", "ENG", "IG_BOND",
                  coupon_rate=0.0360, coupon_freq=1, maturity_date=date(2031, 9, 7),
                  face_value=100.0, initial_price=98.20),
    InstrumentRef("BND_EUR_SAN_2030",  "SAN_4.25_2030",  "Banco Santander 4.25% 2030",
                  "BOND", "EUR", "ES", "FIN", "IG_BOND",
                  coupon_rate=0.0425, coupon_freq=1, maturity_date=date(2030, 11, 12),
                  face_value=100.0, initial_price=100.10),
    InstrumentRef("BND_EUR_NESN_2029", "NESN_3.00_2029", "Nestle SA 3.00% 2029",
                  "BOND", "EUR", "CH", "CONS", "IG_BOND",
                  coupon_rate=0.0300, coupon_freq=1, maturity_date=date(2029, 5, 24),
                  face_value=100.0, initial_price=97.85),
    InstrumentRef("BND_GBP_BARC_2031", "BARC_5.50_2031", "Barclays PLC 5.50% 2031",
                  "BOND", "GBP", "GB", "FIN", "IG_BOND",
                  coupon_rate=0.0550, coupon_freq=2, maturity_date=date(2031, 8, 4),
                  face_value=100.0, initial_price=102.10),
    InstrumentRef("BND_GBP_HSBA_2030", "HSBA_5.00_2030", "HSBC Holdings 5.00% 2030",
                  "BOND", "GBP", "GB", "FIN", "IG_BOND",
                  coupon_rate=0.0500, coupon_freq=2, maturity_date=date(2030, 3, 17),
                  face_value=100.0, initial_price=100.85),
    InstrumentRef("BND_GBP_BP_2032",   "BP_4.75_2032",   "BP PLC 4.75% 2032",
                  "BOND", "GBP", "GB", "ENG", "IG_BOND",
                  coupon_rate=0.0475, coupon_freq=2, maturity_date=date(2032, 6, 21),
                  face_value=100.0, initial_price=99.60),
    InstrumentRef("BND_GBP_VOD_2030",  "VOD_5.25_2030",  "Vodafone Group 5.25% 2030",
                  "BOND", "GBP", "GB", "COMM", "IG_BOND",
                  coupon_rate=0.0525, coupon_freq=2, maturity_date=date(2030, 10, 9),
                  face_value=100.0, initial_price=101.40),
    InstrumentRef("BND_GBP_SHEL_2031", "SHEL_4.50_2031", "Shell PLC 4.50% 2031",
                  "BOND", "GBP", "GB", "ENG", "IG_BOND",
                  coupon_rate=0.0450, coupon_freq=2, maturity_date=date(2031, 2, 14),
                  face_value=100.0, initial_price=99.20),
    InstrumentRef("BND_GBP_AZN_2029",  "AZN_4.00_2029",  "AstraZeneca PLC 4.00% 2029",
                  "BOND", "GBP", "GB", "HC", "IG_BOND",
                  coupon_rate=0.0400, coupon_freq=2, maturity_date=date(2029, 7, 30),
                  face_value=100.0, initial_price=98.50),
    InstrumentRef("BND_GBP_ULVR_2028", "ULVR_3.75_2028", "Unilever PLC 3.75% 2028",
                  "BOND", "GBP", "GB", "CONS", "IG_BOND",
                  coupon_rate=0.0375, coupon_freq=2, maturity_date=date(2028, 12, 5),
                  face_value=100.0, initial_price=98.10),
)

ALL_INSTRUMENTS: tuple[InstrumentRef, ...] = (
    *US_LARGE, *EU_LARGE, *JP_LARGE, *EM_EQUITY, *NORDIC_SMALL, *IG_BONDS,
)

INSTRUMENTS_BY_UNIVERSE: dict[str, tuple[InstrumentRef, ...]] = {
    "US_LARGE":     US_LARGE,
    "EU_LARGE":     EU_LARGE,
    "JP_LARGE":     JP_LARGE,
    "EM_EQUITY":    EM_EQUITY,
    "NORDIC_SMALL": NORDIC_SMALL,
    "IG_BOND":      IG_BONDS,
}


# ----------------------------------------------------------------------------
# Fund domiciles (used for WHT lookup)
# ----------------------------------------------------------------------------
FUND_DOMICILES: dict[str, str] = {
    "ATLAS":  "IE",
    "MERID":  "LU",
    "PACIF":  "IE",
    "STERL":  "IE",
    "HELIO":  "LU",
    "COBAL":  "KY",
    "AURORA": "LU",
    "NORDIC": "LU",
}


# ----------------------------------------------------------------------------
# WHT treaty matrix (fund domicile, source country) -> (treaty_rate, statutory_rate)
# Synthetic; rates are illustrative.
# ----------------------------------------------------------------------------
WHT_TREATY: dict[tuple[str, str], tuple[float, float]] = {
    # (domicile, source) : (treaty_rate, statutory_rate)
    # US-source dividends
    ("IE", "US"): (0.15, 0.30),
    ("LU", "US"): (0.15, 0.30),
    ("KY", "US"): (0.30, 0.30),  # no treaty
    # UK-source
    ("IE", "GB"): (0.00, 0.00),  # UK doesn't WHT divs to non-residents broadly
    ("LU", "GB"): (0.00, 0.00),
    ("KY", "GB"): (0.00, 0.00),
    # Switzerland-source
    ("IE", "CH"): (0.15, 0.35),
    ("LU", "CH"): (0.15, 0.35),
    ("KY", "CH"): (0.35, 0.35),
    # Japan-source
    ("IE", "JP"): (0.10, 0.15),
    ("LU", "JP"): (0.05, 0.15),
    ("KY", "JP"): (0.15, 0.15),
    # Korea-source
    ("IE", "KR"): (0.15, 0.22),
    ("LU", "KR"): (0.15, 0.22),
    ("KY", "KR"): (0.22, 0.22),
    # Taiwan-source
    ("IE", "TW"): (0.21, 0.21),
    ("LU", "TW"): (0.21, 0.21),
    ("KY", "TW"): (0.21, 0.21),
    # India-source
    ("IE", "IN"): (0.10, 0.20),
    ("LU", "IN"): (0.10, 0.20),
    ("KY", "IN"): (0.20, 0.20),
    # Brazil-source
    ("IE", "BR"): (0.15, 0.15),
    ("LU", "BR"): (0.15, 0.15),
    ("KY", "BR"): (0.15, 0.15),
    # Mexico-source
    ("IE", "MX"): (0.10, 0.10),
    ("LU", "MX"): (0.10, 0.10),
    ("KY", "MX"): (0.10, 0.10),
    # South Africa-source
    ("IE", "ZA"): (0.15, 0.20),
    ("LU", "ZA"): (0.15, 0.20),
    ("KY", "ZA"): (0.20, 0.20),
    # Hong Kong-source
    ("IE", "HK"): (0.00, 0.00),
    ("LU", "HK"): (0.00, 0.00),
    ("KY", "HK"): (0.00, 0.00),
    # EU intra
    ("LU", "DE"): (0.05, 0.26375),
    ("LU", "FR"): (0.15, 0.25),
    ("LU", "NL"): (0.15, 0.15),
    ("LU", "ES"): (0.10, 0.19),
    ("LU", "FI"): (0.05, 0.30),
    ("LU", "DK"): (0.15, 0.27),
    ("LU", "SE"): (0.05, 0.30),
    ("LU", "NO"): (0.05, 0.25),
    ("IE", "DE"): (0.15, 0.26375),
    ("IE", "FR"): (0.15, 0.25),
    ("IE", "NL"): (0.15, 0.15),
    ("IE", "ES"): (0.15, 0.19),
}


def get_wht_rates(domicile: str, source: str) -> tuple[float, float]:
    """Treaty rate, statutory rate for (domicile, source). Defaults to (0.30, 0.30) if missing."""
    return WHT_TREATY.get((domicile, source), (0.30, 0.30))


# ----------------------------------------------------------------------------
# Sector factor universe (used by price generator).
# ----------------------------------------------------------------------------
SECTORS: tuple[str, ...] = (
    "TECH", "FIN", "HC", "COND", "CONS", "IND", "ENG", "MAT", "UTL", "COMM", "RE",
)
