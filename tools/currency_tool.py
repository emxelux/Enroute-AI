import os
import requests
from typing import Optional
from langchain.tools import tool
from dotenv import load_dotenv

load_dotenv()


# Country to currency code mapping (ISO 4217)
COUNTRY_TO_CURRENCY = {
    "US": "USD", "USA": "USD", "United States": "USD",
    "GB": "GBP", "UK": "GBP", "United Kingdom": "GBP",
    "NG": "NGN", "Nigeria": "NGN",
    "EU": "EUR", "Europe": "EUR", "Germany": "EUR", "France": "EUR", "Italy": "EUR", "Spain": "EUR",
    "CA": "CAD", "Canada": "CAD",
    "AU": "AUD", "Australia": "AUD",
    "JP": "JPY", "Japan": "JPY",
    "CN": "CNY", "China": "CNY",
    "IN": "INR", "India": "INR",
    "BR": "BRL", "Brazil": "BRL",
    "ZA": "ZAR", "South Africa": "ZAR",
    "KE": "KES", "Kenya": "KES",
    "GH": "GHS", "Ghana": "GHS",
    "ZA": "ZAR", "South Africa": "ZAR",
    "AE": "AED", "UAE": "AED", "Dubai": "AED",
    "SG": "SGD", "Singapore": "SGD",
    "CH": "CHF", "Switzerland": "CHF",
    "NO": "NOK", "Norway": "NOK",
    "SE": "SEK", "Sweden": "SEK",
    "DK": "DKK", "Denmark": "DKK",
    "PL": "PLN", "Poland": "PLN",
    "CZ": "CZK", "Czech Republic": "CZK",
    "HU": "HUF", "Hungary": "HUF",
    "RO": "RON", "Romania": "RON",
    "BG": "BGN", "Bulgaria": "BGN",
    "HR": "HRK", "Croatia": "HRK",
    "RS": "RSD", "Serbia": "RSD",
    "TR": "TRY", "Turkey": "TRY",
    "IL": "ILS", "Israel": "ILS",
    "SA": "SAR", "Saudi Arabia": "SAR",
    "QA": "QAR", "Qatar": "QAR",
    "KW": "KWD", "Kuwait": "KWD",
    "BH": "BHD", "Bahrain": "BHD",
    "OM": "OMR", "Oman": "OMR",
    "JO": "JOD", "Jordan": "JOD",
    "LB": "LBP", "Lebanon": "LBP",
    "EG": "EGP", "Egypt": "EGP",
    "MA": "MAD", "Morocco": "MAD",
    "TN": "TND", "Tunisia": "TND",
    "DZ": "DZD", "Algeria": "DZD",
    "ET": "ETB", "Ethiopia": "ETB",
    "TZ": "TZS", "Tanzania": "TZS",
    "UG": "UGX", "Uganda": "UGX",
    "RW": "RWF", "Rwanda": "RWF",
    "ZW": "ZWL", "Zimbabwe": "ZWL",
    "ZM": "ZMW", "Zambia": "ZMW",
    "BW": "BWP", "Botswana": "BWP",
    "NA": "NAD", "Namibia": "NAD",
    "MZ": "MZN", "Mozambique": "MZN",
    "MW": "MWK", "Malawi": "MWK",
    "SZ": "SZL", "Eswatini": "SZL",
    "LS": "LSL", "Lesotho": "LSL",
    "MU": "MUR", "Mauritius": "MUR",
    "SC": "SCR", "Seychelles": "SCR",
    "KM": "KMF", "Comoros": "KMF",
    "ST": "STN", "Sao Tome and Principe": "STN",
    "CV": "CVE", "Cape Verde": "CVE",
    "GW": "XOF", "Guinea-Bissau": "XOF",
    "GM": "GMD", "Gambia": "GMD",
    "SN": "XOF", "Senegal": "XOF",
    "ML": "XOF", "Mali": "XOF",
    "BF": "XOF", "Burkina Faso": "XOF",
    "CI": "XOF", "Ivory Coast": "XOF",
    "TG": "XOF", "Togo": "XOF",
    "BJ": "XOF", "Benin": "XOF",
    "NE": "XOF", "Niger": "XOF",
    "MR": "MRU", "Mauritania": "MRU",
    "LR": "LRD", "Liberia": "LRD",
    "SL": "SLL", "Sierra Leone": "SLL",
    "GN": "GNF", "Guinea": "GNF",
    "GW": "XOF", "Guinea-Bissau": "XOF",
    "CF": "XAF", "Central African Republic": "XAF",
    "TD": "XAF", "Chad": "XAF",
    "CG": "XAF", "Congo": "XAF",
    "GA": "XAF", "Gabon": "XAF",
    "GQ": "XAF", "Equatorial Guinea": "XAF",
    "CM": "XAF", "Cameroon": "XAF",
    "CD": "CDF", "DR Congo": "CDF",
    "AO": "AOA", "Angola": "AOA",
    "KM": "KMF", "Comoros": "KMF",
    "YT": "EUR", "Mayotte": "EUR",
    "RE": "EUR", "Reunion": "EUR",
    "PM": "EUR", "Saint Pierre and Miquelon": "EUR",
    "MF": "EUR", "Saint Martin": "EUR",
    "BL": "EUR", "Saint Barthelemy": "EUR",
    "GF": "EUR", "French Guiana": "EUR",
    "GP": "EUR", "Guadeloupe": "EUR",
    "MQ": "EUR", "Martinique": "EUR",
    "NC": "XPF", "New Caledonia": "XPF",
    "PF": "XPF", "French Polynesia": "XPF",
    "WF": "XPF", "Wallis and Futuna": "XPF",
    "TF": "EUR", "French Southern Territories": "EUR",
}


def get_currency_from_country(country: str) -> str:
    """Get ISO currency code from country name or code."""
    country = country.strip().title()
    return COUNTRY_TO_CURRENCY.get(country, country.upper())


@tool
def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: Optional[str] = None,
    user_country: Optional[str] = None,
) -> dict:
    """
    Convert an amount from one currency to another.

    Args:
        amount: The amount to convert
        from_currency: Source currency code (e.g., "USD", "GBP", "EUR")
        to_currency: Target currency code (e.g., "NGN", "USD"). If not provided, uses user_country.
        user_country: User's country name or code (e.g., "Nigeria", "NG", "United States").
                     Used to determine target currency if to_currency not provided.

    Returns:
        Dictionary with conversion result including converted amount, rate, and metadata.
    """
    # Determine target currency
    if to_currency:
        target_currency = to_currency.upper()
    elif user_country:
        target_currency = get_currency_from_country(user_country)
    else:
        # Default to USD if nothing specified
        target_currency = "USD"

    source_currency = from_currency.upper()

    # If same currency, return as-is
    if source_currency == target_currency:
        return {
            "original_amount": amount,
            "converted_amount": amount,
            "from_currency": source_currency,
            "to_currency": target_currency,
            "exchange_rate": 1.0,
            "note": "Same currency, no conversion needed"
        }

    try:
        # Use Frankfurter API (free, no API key required)
        # https://api.frankfurter.dev/
        url = f"https://api.frankfurter.dev/v1/latest"
        params = {
            "from": source_currency,
            "to": target_currency
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        rate = data["rates"].get(target_currency)
        if rate is None:
            return {
                "error": f"Currency {target_currency} not available for conversion from {source_currency}",
                "original_amount": amount,
                "from_currency": source_currency,
                "to_currency": target_currency,
            }

        converted_amount = round(amount * rate, 2)

        return {
            "original_amount": amount,
            "converted_amount": converted_amount,
            "from_currency": source_currency,
            "to_currency": target_currency,
            "exchange_rate": rate,
            "date": data.get("date"),
            "note": f"Converted using Frankfurter API (ECB rates)"
        }

    except requests.RequestException as e:
        # Fallback: try a different free API or return error
        return {
            "error": f"Failed to fetch exchange rate: {str(e)}",
            "original_amount": amount,
            "from_currency": source_currency,
            "to_currency": target_currency,
            "fallback": "You may want to try again or use a different conversion service"
        }


def detect_currency_from_text(text: str) -> dict:
    """
    Detect currency codes and amounts mentioned in text (e.g., from flight/hotel responses).

    Args:
        text: Text that may contain currency information

    Returns:
        Dictionary with detected currencies and amounts
    """
    import re

    # Common currency patterns
    currency_patterns = {
        "USD": [r"\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"USD\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "GBP": [r"£\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"GBP\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "EUR": [r"€\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"EUR\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "NGN": [r"₦\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"NGN\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "JPY": [r"¥\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"JPY\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "CAD": [r"C\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"CAD\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "AUD": [r"A\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"AUD\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "CHF": [r"CHF\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "CNY": [r"CNY\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"¥\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
        "INR": [r"₹\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", r"INR\s*(\d+(?:,\d{3})*(?:\.\d{2})?)"],
    }

    detected = []
    for currency, patterns in currency_patterns.items():
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    
                    amount = float(match.replace(",", ""))
                    detected.append({
                        "currency": currency,
                        "amount": amount,
                        "raw_match": match
                    })
                except ValueError:
                    continue

    return {
        "detected_currencies": detected,
        "text_analyzed": text[:200] + "..." if len(text) > 200 else text
    }


@tool
def convert_detected_currencies(
    text: str,
    target_currency: Optional[str] = None,
    user_country: Optional[str] = None,
) -> dict:
    """
    Detect currencies in text and convert them to target currency.

    Args:
        text: Text containing currency amounts (e.g., flight/hotel response)
        target_currency: Target currency code
        user_country: User's country to determine target currency

    Returns:
        Dictionary with all detected amounts converted
    """
    detection = detect_currency_from_text(text)
    detected = detection.get("detected_currencies", [])

    if not detected:
        return {
            "conversions": [],
            "note": "No currencies detected in text"
        }

    conversions = []
    for item in detected:
        result = convert_currency(
            amount=item["amount"],
            from_currency=item["currency"],
            to_currency=target_currency,
            user_country=user_country
        )
        result["source_text"] = item["raw_match"]
        conversions.append(result)

    return {
        "conversions": conversions,
        "target_currency": target_currency or get_currency_from_country(user_country) if user_country else "USD"
    }