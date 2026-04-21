"""
Currency Conversion Service
==========================

Service para conversión de monedas.
Service boundary claro para futura extracción.
"""

from typing import Dict, Any

class CurrencyConversionService:
    """Currency Service con tasas actualizables"""
    
    def __init__(self):
        # FIX v2.1.0 (27/03/2026): Añadido CLP y COP.
        # Las tasas se expresan como USD/moneda (1 USD = N moneda).
        # CLP: 1 USD ≈ 961 CLP (Banco Central de Chile, 27/03/2026)
        # COP: 1 USD ≈ 3900 COP (Banco de la República, 27/03/2026)
        self.exchange_rates = {
            "USD": 1.0,
            "EUR": 0.85,
            "GBP": 0.73,
            "MXN": 20.0,
            "CAD": 1.25,
            "JPY": 110.0,
            "CLP": 961.0,   # Peso chileno — mercado primario de AI-Shoppings
            "COP": 3900.0,  # Peso colombiano
        }
    
    async def convert_price(
        self, 
        amount: float, 
        from_currency: str, 
        to_currency: str
    ) -> Dict[str, Any]:
        """Service boundary: Currency conversion"""
        
        if from_currency == to_currency:
            return {
                "original_amount": amount,
                "converted_amount": amount, 
                "exchange_rate": 1.0,
                "conversion_successful": True
            }
        
        if from_currency not in self.exchange_rates or to_currency not in self.exchange_rates:
            return {
                "original_amount": amount,
                "converted_amount": amount,
                "conversion_successful": False,
                "error": "Unsupported currency pair"
            }
        
        # Conversión a través de USD
        usd_amount = amount / self.exchange_rates[from_currency]
        converted_amount = usd_amount * self.exchange_rates[to_currency]
        exchange_rate = self.exchange_rates[to_currency] / self.exchange_rates[from_currency]
        
        return {
            "original_amount": amount,
            "converted_amount": round(converted_amount, 2),
            "exchange_rate": round(exchange_rate, 4),
            "conversion_successful": True
        }
    
    async def get_market_currency(self, market_id: str) -> str:
        """Service boundary: Market currency lookup"""
        # FIX v2.1.0 (27/03/2026): Añadido CL → CLP y CO → COP
        currency_map = {
            "US": "USD",
            "ES": "EUR",
            "MX": "MXN",
            "GB": "GBP",
            "CA": "CAD",
            "JP": "JPY",
            "CL": "CLP",   # Chile — mercado primario de AI-Shoppings
            "CO": "COP",   # Colombia
        }
        return currency_map.get(market_id, "USD")
