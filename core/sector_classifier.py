"""
AI / Semiconductor Sector Classifier
-------------------------------------
Determines whether a ticker belongs to the AI or semiconductor supply chain.

Priority:
  1. Hardcoded lookup table (fast, curated, always available)
  2. yfinance Ticker.info fallback for unlisted tickers (keyword matching)
  3. Default → NO if data is unavailable

Categories covered:
  Electronics, Semiconductor, AI Infrastructure, AI Hardware, Chip Design,
  Chip Manufacturing, AI Compute, AI Data Center Hardware, GPU/Accelerator,
  AI Networking Equipment, EDA Software
"""
from __future__ import annotations

from loguru import logger

# ── Curated lookup ────────────────────────────────────────────────────────────
# Format: ticker → (exposure, category)
_CLASSIFIED: dict[str, tuple[str, str]] = {

    # GPU / AI Accelerator
    "NVDA":  ("YES", "GPU / AI Accelerator"),
    "AMD":   ("YES", "GPU / AI Accelerator / CPU"),

    # Semiconductor — Memory / AI Storage
    "MU":    ("YES", "Semiconductor — Memory (HBM / AI Training)"),
    "WDC":   ("YES", "Data Storage — AI Infrastructure"),
    "STX":   ("YES", "Data Storage — AI Infrastructure"),

    # Semiconductor — Analog / Mixed Signal
    "TXN":   ("YES", "Semiconductor — Analog"),
    "ADI":   ("YES", "Semiconductor — Analog / Mixed Signal"),
    "MCHP":  ("YES", "Semiconductor — Microcontrollers"),
    "ON":    ("YES", "Semiconductor — Power / Automotive"),
    "MPWR":  ("YES", "Semiconductor — Power ICs"),
    "NXPI":  ("YES", "Semiconductor — Automotive / IoT"),
    "SWKS":  ("YES", "Semiconductor — RF / Wireless"),
    "QRVO":  ("YES", "Semiconductor — RF / Mobile"),

    # Semiconductor — Digital / AI Chip Design
    "QCOM":  ("YES", "Semiconductor — Mobile / On-Device AI Chip"),
    "AVGO":  ("YES", "Semiconductor — AI Networking Chip"),
    "MRVL":  ("YES", "Semiconductor — AI Networking / Data Center"),
    "INTC":  ("YES", "Semiconductor — CPU / AI Infrastructure"),
    "ARM":   ("YES", "Semiconductor IP — AI Chip Architecture"),

    # EDA Software (chip design tools — part of semiconductor ecosystem)
    "CDNS":  ("YES", "EDA Software — Chip Design Tools"),
    "SNPS":  ("YES", "EDA Software — Chip Design Tools"),

    # Semiconductor Equipment
    "ASML":  ("YES", "Semiconductor Equipment — EUV Lithography"),
    "AMAT":  ("YES", "Semiconductor Manufacturing Equipment"),
    "LRCX":  ("YES", "Semiconductor Manufacturing Equipment"),
    "KLAC":  ("YES", "Semiconductor — Process Control Equipment"),
    "TER":   ("YES", "Semiconductor — Test Equipment"),
    "KEYS":  ("YES", "Electronic Test & Measurement"),
    "COHU":  ("YES", "Semiconductor — Test & Inspection"),
    "ENTG":  ("YES", "Semiconductor Materials & Equipment"),
    "MKSI":  ("YES", "Semiconductor Manufacturing Equipment"),

    # Chip Manufacturing — Foundry
    "TSM":   ("YES", "Chip Manufacturing — Foundry (TSMC)"),
    "GFS":   ("YES", "Chip Manufacturing — Foundry (GlobalFoundries)"),
    "UMC":   ("YES", "Chip Manufacturing — Foundry"),

    # AI Data Center Hardware / Servers
    "SMCI":  ("YES", "AI Data Center Hardware — GPU Servers / Racks"),
    "DELL":  ("YES", "AI Data Center Infrastructure"),
    "HPE":   ("YES", "AI Data Center / HPC Servers"),
    "IBM":   ("YES", "AI Infrastructure / Enterprise AI"),

    # AI Networking Equipment
    "CSCO":  ("YES", "AI Networking Infrastructure"),
    "JNPR":  ("YES", "AI Networking Equipment"),
    "ANET":  ("YES", "AI Networking — Data Center Switching"),
    "CIEN":  ("YES", "AI Networking — Optical Networking"),
    "COHR":  ("YES", "AI Networking — Optical Components"),
    "II-VI": ("YES", "AI Networking — Photonics / Optical"),
    "VIAV":  ("YES", "AI Networking — Optical Test"),

    # AI Cloud / Hyperscaler (custom silicon + AI compute)
    "MSFT":  ("YES", "AI Cloud Infrastructure — Azure AI / Maia Chip"),
    "GOOGL": ("YES", "AI Compute — Cloud AI / Google TPU"),
    "GOOG":  ("YES", "AI Compute — Cloud AI / Google TPU"),
    "AMZN":  ("YES", "AI Cloud Infrastructure — AWS Trainium/Inferentia"),
    "META":  ("YES", "AI Infrastructure — Custom Silicon (MTIA)"),

    # Consumer Electronics (products use AI but not in supply chain)
    "AAPL":  ("NO", "Consumer Electronics / Software"),
    "TSLA":  ("NO", "EV / Autonomous Driving Software"),

    # Enterprise SaaS / Software
    "CRM":   ("NO", "Enterprise SaaS"),
    "ADBE":  ("NO", "Creative Software / Generative AI Tools"),
    "NOW":   ("NO", "Enterprise SaaS / IT Automation"),
    "ORCL":  ("NO", "Enterprise Database / Cloud ERP"),
    "SNOW":  ("NO", "Cloud Data Warehousing"),
    "PLTR":  ("NO", "AI Analytics / Defense Software"),
    "PATH":  ("NO", "Robotic Process Automation"),
    "WDAY":  ("NO", "HCM / Enterprise SaaS"),
    "PAYC":  ("NO", "HR Software / SaaS"),
    "VEEV":  ("NO", "Life Sciences SaaS"),

    # Cybersecurity
    "CRWD":  ("NO", "Cybersecurity — AI-Powered EDR"),
    "PANW":  ("NO", "Cybersecurity — SASE"),
    "FTNT":  ("NO", "Cybersecurity — Network Security"),
    "ZS":    ("NO", "Cybersecurity — Zero Trust"),
    "OKTA":  ("NO", "Identity Security"),
    "S":     ("NO", "Cybersecurity — AI-Powered EDR"),
    "NET":   ("NO", "CDN / Edge Security"),

    # DevOps / Cloud Monitoring
    "DDOG":  ("NO", "Cloud Observability / DevOps"),
    "MDB":   ("NO", "NoSQL Database / Cloud"),
    "GTLB":  ("NO", "DevOps Platform"),
    "DOCN":  ("NO", "Cloud Infrastructure / PaaS"),
    "NTNX":  ("NO", "Hyperconverged Infrastructure"),
    "EPAM":  ("NO", "IT Services / Software Engineering"),

    # FinTech / Other
    "COIN":  ("NO", "Cryptocurrency Exchange"),
    "HOOD":  ("NO", "Retail Brokerage / FinTech"),
    "SQ":    ("NO", "Payments / FinTech"),
    "TTD":   ("NO", "Programmatic Advertising"),
    "SHOP":  ("NO", "E-Commerce Platform"),

    # Storage / Infra (borderline but not pure AI hardware)
    "ANSS":  ("NO", "Simulation Software (EDA-adjacent)"),
}

# yfinance industry/sector keywords that indicate AI/semiconductor exposure
_SEMI_INDUSTRIES: set[str] = {
    "semiconductors",
    "semiconductor equipment & materials",
    "electronic components",
    "electronic equipment & instruments",
    "electronics distribution",
    "computer hardware",
    "data storage devices",
    "communication equipment",
    "networking hardware",
}

_AI_DESCRIPTION_KEYWORDS: list[str] = [
    "semiconductor",
    "gpu",
    " chip ",
    "wafer",
    "foundry",
    "fpga",
    "accelerator",
    "neural network",
    "ai infrastructure",
    "data center",
    "hpc",
    "photonics",
    "optical networking",
    "lithography",
    "eda software",
    "chip design",
]


def classify(ticker: str) -> tuple[str, str]:
    """Return (exposure, category) for *ticker*.

    exposure is "YES" or "NO".
    Falls back to yfinance industry lookup for unknown tickers.
    """
    ticker = ticker.upper()

    # 1. Fast path — curated lookup
    if ticker in _CLASSIFIED:
        return _CLASSIFIED[ticker]

    # 2. Fallback — yfinance industry / description scan
    try:
        return _classify_via_yfinance(ticker)
    except Exception as e:
        logger.debug(f"Sector classifier fallback failed for {ticker}: {e}")

    return "NO", "Technology"


def _classify_via_yfinance(ticker: str) -> tuple[str, str]:
    import yfinance as yf

    info = yf.Ticker(ticker).info
    industry = (info.get("industry") or "").lower()
    sector = (info.get("sector") or "").lower()
    summary = (info.get("longBusinessSummary") or "").lower()

    if industry in _SEMI_INDUSTRIES:
        # Map to a descriptive category
        category = _industry_to_category(industry, summary)
        return "YES", category

    # Keyword scan of business description
    for kw in _AI_DESCRIPTION_KEYWORDS:
        if kw in summary or kw in industry:
            category = _industry_to_category(industry, summary)
            return "YES", category

    return "NO", _sector_label(sector, industry)


def _industry_to_category(industry: str, summary: str) -> str:
    if "equipment" in industry:
        return "Semiconductor Equipment"
    if "storage" in industry or "storage" in summary:
        return "Data Storage — AI Infrastructure"
    if "network" in industry or "network" in summary:
        return "AI Networking Hardware"
    if "semiconductor" in industry:
        if "gpu" in summary or "accelerator" in summary:
            return "GPU / AI Accelerator"
        if "memory" in summary or "dram" in summary or "nand" in summary:
            return "Semiconductor — Memory"
        return "Semiconductor"
    if "computer hardware" in industry:
        return "AI Data Center Hardware"
    if "electronic" in industry:
        return "Electronics / Semiconductor"
    return "AI / Semiconductor"


def _sector_label(sector: str, industry: str) -> str:
    if sector == "technology":
        return "Technology"
    return industry.title() or "Technology"
