from asyncio.log import logger
import requests
from typing import List, Dict, Optional
import logging
from base64 import b64encode
import time

class ShopifyIntegration:
    def __init__(self, shop_url: str, access_token: str):
        self.shop_url = shop_url.rstrip('/').replace('https://', '').replace('http://', '')
        self.access_token = access_token
        self.headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json'
        }
        # VERSION DE API: debe coincidir con la configurada en Shopify App.
        # La app esta configurada en 2025-01 (verificado en Shopify Admin).
        self.api_url = f"https://{self.shop_url}/admin/api/2025-01"
        logging.info(f"Initializing Shopify client with:")
        logging.info(f"Shop URL: {self.shop_url}")
        logging.info(f"API URL: {self.api_url}")
        logging.info(f"Access Token: {self.access_token[:4]}...")

    def get_products(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """
        Obtiene productos de Shopify con paginacion y limites especificos.
        
        Args:
            limit (int, optional): Numero maximo de productos a retornar. None para todos.
            offset (int): Numero de productos a saltar (para paginacion).
        
        Returns:
            List[Dict]: Lista de productos paginada
        """
        try:
            all_products = []
            
            # Optimizacion: Si el limite es pequeno, usar directamente
            if limit and limit <= 50:
                url = f"{self.api_url}/products.json?limit={limit}"
                logging.info(f"Using optimized fetch for small limit: {limit}")
            else:
                # Para limites grandes o sin limite, usar paginacion estandar
                url = f"{self.api_url}/products.json?limit=250"
            
            # Manejar offset saltando productos si es necesario
            products_to_skip = offset
            products_collected = 0
            
            # Continuar paginando mientras haya paginas siguientes
            while url:
                logging.info(f"Fetching products from: {url}")
                
                # Realizar la peticion
                response = self._make_request_with_retry(url)
                
                # Extraer los productos de la respuesta
                data = response.json()
                products = data.get('products', [])
                
                if products:
                    logging.info(f"Received {len(products)} products")
                    
                    # Aplicar offset (saltar productos si es necesario)
                    if products_to_skip > 0:
                        if products_to_skip >= len(products):
                            products_to_skip -= len(products)
                            url = self._get_next_page_url(response)
                            continue
                        else:
                            products = products[products_to_skip:]
                            products_to_skip = 0
                    
                    # Aplicar limite si esta especificado
                    if limit is not None:
                        remaining_needed = limit - products_collected
                        if remaining_needed <= 0:
                            break
                        if len(products) > remaining_needed:
                            products = products[:remaining_needed]
                    
                    all_products.extend(products)
                    products_collected += len(products)
                    
                    if limit is not None and products_collected >= limit:
                        logging.info(f"Reached target limit of {limit} products")
                        break
                else:
                    logging.info("No products found in current page")
                    break
                
                url = self._get_next_page_url(response)
            
            logging.info(f"Successfully fetched a total of {len(all_products)} products")
            
            if all_products:
                sample = all_products[0]
                logging.info(f"Sample product: ID={sample.get('id')}, Title={sample.get('title')}")
            
            return all_products
        except Exception as e:
            logging.error(f"Error fetching products: {str(e)}")
            return []
    
    def _get_next_page_url(self, response):
        """Extrae la URL de la siguiente pagina del header Link."""
        if 'Link' not in response.headers:
            return None
        
        links = response.headers['Link'].split(',')
        for link in links:
            if 'rel="next"' in link:
                url = link.split(';')[0].strip().lstrip('<').rstrip('>')
                return url
                
        return None
    
    def _make_request_with_retry(self, url, max_retries=3, retry_delay=1):
        """Realiza una peticion HTTP con manejo de reintentos y rate limiting."""
        retries = 0
        while retries < max_retries:
            try:
                response = requests.get(url, headers=self.headers)
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', retry_delay * 2))
                    logging.warning(f"Rate limit reached. Waiting {retry_after} seconds.")
                    time.sleep(retry_after)
                    retries += 1
                    continue
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.RequestException as e:
                retries += 1
                wait_time = retry_delay * (2 ** retries)
                logging.warning(f"Request error: {str(e)}. Retry {retries}/{max_retries} in {wait_time} seconds.")
                
                if retries < max_retries:
                    time.sleep(wait_time)
                else:
                    logging.error(f"Max retries reached. Giving up.")
                    raise
        
        raise Exception(f"Failed to complete request after {max_retries} retries")

    def get_orders_by_customer(self, customer_id: str, limit: int = 50) -> List[Dict]:
        """Obtiene las ordenes de un cliente con paginacion."""
        try:
            all_orders = []
            url = f"{self.api_url}/orders.json?customer_id={customer_id}&status=any&limit=250"
            
            while url and (limit is None or len(all_orders) < limit):
                logging.info(f"Fetching orders for customer {customer_id}")
                response = self._make_request_with_retry(url)
                orders = response.json().get('orders', [])
                
                if orders:
                    if limit is not None and len(all_orders) + len(orders) > limit:
                        all_orders.extend(orders[:limit - len(all_orders)])
                        break
                    else:
                        all_orders.extend(orders)
                    logging.info(f"Fetched {len(orders)} orders, total so far: {len(all_orders)}")
                else:
                    break
                
                url = self._get_next_page_url(response)
            
            return all_orders
            
        except Exception as e:
            logging.error(f"Error fetching orders for customer {customer_id}: {str(e)}")
            return []

    def get_customer_by_id(self, customer_id: str) -> Optional[Dict]:
        """Obtiene un cliente individual por su ID de Shopify.

        Usado por CustomerProfileService para el fetch lazy del perfil.
        Retorna None si el cliente no existe o hay error de red.

        Args:
            customer_id: ID numérico del cliente en Shopify (str o int).

        Returns:
            Dict con datos del cliente (id, email, orders_count, total_spent,
            tags, default_address, created_at) o None si no encontrado.
        """
        try:
            url = f"{self.api_url}/customers/{customer_id}.json"
            logging.info(f"Fetching customer profile for id={customer_id}")
            response = self._make_request_with_retry(url)
            customer = response.json().get("customer")
            if not customer:
                logging.warning(f"Customer {customer_id} not found in Shopify")
                return None
            return customer
        except Exception as e:
            logging.error(f"Error fetching customer {customer_id}: {str(e)}")
            return None

    def get_customers(self, limit: int = 250) -> List[Dict]:
        """Obtiene la lista de clientes de la tienda con paginacion."""
        try:
            all_customers = []
            url = f"{self.api_url}/customers.json?limit=250"
            
            while url and (limit is None or len(all_customers) < limit):
                logging.info(f"Fetching customers")
                response = self._make_request_with_retry(url)
                customers = response.json().get('customers', [])
                
                if customers:
                    if limit is not None and len(all_customers) + len(customers) > limit:
                        all_customers.extend(customers[:limit - len(all_customers)])
                        break
                    else:
                        all_customers.extend(customers)
                    logging.info(f"Fetched {len(customers)} customers, total so far: {len(all_customers)}")
                else:
                    break
                
                url = self._get_next_page_url(response)
            
            return all_customers
            
        except Exception as e:
            logging.error(f"Error fetching customers: {str(e)}")
            return []
            
    def get_product_count(self) -> int:
        """Obtiene el numero total de productos en la tienda."""
        try:
            url = f"{self.api_url}/products/count.json"
            logging.info(f"Fetching product count from: {url}")
            response = self._make_request_with_retry(url)
            count = response.json().get('count', 0)
            logging.info(f"Total product count: {count}")
            return count
        except Exception as e:
            logging.error(f"Error fetching product count: {str(e)}")
            return 0
        

    # ==========================================================================
    # GRAPHQL API SUPPORT
    # ==========================================================================
    
    async def _graphql_query(self, query: str, variables: Dict = None) -> Dict:
        """
        Execute GraphQL query against Shopify Admin API (ASYNC).
        Uses asyncio.to_thread() to run the sync HTTP call in a thread pool.
        """
        import asyncio
        
        url = f"https://{self.shop_url}/admin/api/2025-01/graphql.json"
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token
        }
        
        try:
            response = await asyncio.to_thread(
                requests.post, url, json=payload, headers=headers, timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                error_msgs = [err.get("message", str(err)) for err in data["errors"]]
                raise Exception(f"GraphQL errors: {'; '.join(error_msgs)}")
            
            return data.get("data", {})
            
        except requests.exceptions.Timeout:
            logging.error(f"GraphQL query timeout after 30s")
            raise Exception("GraphQL query timeout")
        except requests.exceptions.RequestException as e:
            logging.error(f"GraphQL HTTP request failed: {e}")
            raise
        except Exception as e:
            logging.error(f"GraphQL query failed: {e}")
            raise

    async def get_products_with_shopify_prices(
        self,
        limit: int = None
    ) -> List[Dict]:
        """
        Obtiene productos de Shopify REST y los enriquece con precios por mercado
        autorizados por Shopify via Admin GraphQL contextualPricing.

        OPCION A - Multi-mercado (v2.1.0, 28/03/2026):
        ------------------------------------------------
        AI-Shoppings tiene 4 mercados activos confirmados en Shopify Admin:
          - Chile (CL)        -> CLP  (moneda nativa de la tienda)
          - Mexico (MX)       -> MXN
          - Switzerland (CH)  -> CHF
          - International     -> USD  (representante: US)

        La API REST devuelve el precio nativo (CLP). Para los mercados no-CL,
        Shopify calcula el precio en la moneda local usando su propia tasa de
        cambio actualizada. Este metodo obtiene esos precios para todos los
        mercados activos y los almacena en el campo `market_prices` del producto.

        Resultado: el sistema ya no necesita tablas de tasas hardcodeadas.
        Claude, MarketAdapter y ProductCard leen el precio directamente de
        Shopify para el mercado del cliente.

        ARQUITECTURA:
            1. REST /products.json -> lista completa (metadatos, variantes, imagenes)
            2. Admin GraphQL contextualPricing por mercado -> precio en moneda local
            3. Enriquecer cada producto con market_prices: {CL:{...}, CH:{...}, MX:{...}}

        SEGURIDAD DE TIPOS:
            Si GraphQL falla para un lote, se usa el precio REST como fallback.
            El campo `price` nivel-raiz siempre contiene CLP para compatibilidad.

        Args:
            limit: Numero maximo de productos (None = todos)

        Returns:
            Lista de productos enriquecidos con campos:
            - price: float            -- precio en CLP (nivel raiz, compatibilidad)
            - currency: str           -- "CLP" (moneda nativa)
            - market_prices: dict     -- precios por mercado:
                {
                  "CL": {"price": 160000.0, "currency": "CLP"},
                  "CH": {"price": 159.0,    "currency": "CHF"},
                  "MX": {"price": 3200.0,   "currency": "MXN"},
                  "US": {"price": 166.4,    "currency": "USD"}
                }
        """
        import asyncio

        # Mercados activos confirmados en Shopify Admin (28/03/2026).
        # Screenshot: Chile (CL), Switzerland (CH), Mexico (MX), International (27 regiones).
        #
        # MAPEADO de mercados Shopify -> country_code para contextualPricing:
        #   - Chile      -> CL  (moneda nativa CLP)
        #   - switzerland-> CH  (CHF)
        #   - Mexico     -> MX  (MXN)
        #   - International (27 regiones) -> ES como representante europeo (EUR)
        #
        # Por que ES para International?
        #   El mercado "International" cubre 27 regiones con distintas monedas.
        #   ES (Espana/EUR) es el representante logico para clientes europeos,
        #   que es el caso principal observado (cliente suizo ve CHF en storefront).
        #   Switzerland tiene su propio mercado dedicado -> CH/CHF.
        #
        # Actualizar esta lista si se anaden/eliminan mercados en Shopify Admin.
        ACTIVE_MARKETS = [
            {"market_id": "CL", "country_code": "CL"},   # Chile -> CLP (primario)
            {"market_id": "CH", "country_code": "CH"},   # Switzerland -> CHF
            {"market_id": "MX", "country_code": "MX"},   # Mexico -> MXN
            {"market_id": "ES", "country_code": "ES"},   # International/Europa -> EUR
        ]

        # -- PASO 1: Obtener lista de productos via REST ----------------------
        logging.info("[ShopifyPrices] Step 1: Fetching product list via REST...")
        products = self.get_products(limit=limit)

        if not products:
            logging.warning("[ShopifyPrices] No products returned from REST API")
            return []

        logging.info(f"[ShopifyPrices] Retrieved {len(products)} products from REST")

        # market_price_map[market_id][product_id] = {"price": float, "currency": str}
        market_price_map: Dict[str, Dict[str, Dict]] = {
            m["market_id"]: {} for m in ACTIVE_MARKETS
        }

        # -- PASO 2: Consultar precios por mercado via GraphQL ----------------
        #
        # Usamos aliases GraphQL para consultar todos los productos x mercados
        # en una sola query por lote.
        #
        # Formato de query resultante (2 productos, 2 mercados):
        #   query GetMultiMarketPrices {
        #     p0_CL: product(id: "gid://shopify/Product/123") {
        #       contextualPricing(context: {country: CL}) {
        #         priceRange { minVariantPrice { amount currencyCode } }
        #       }
        #     }
        #     p0_CH: product(id: "gid://shopify/Product/123") {
        #       contextualPricing(context: {country: CH}) { ... }
        #     }
        #     p1_CL: product(id: "gid://shopify/Product/456") { ... }
        #   }
        #
        # COMPLEJIDAD GraphQL: Shopify limita a ~10.000 puntos/query.
        # Con lotes de 30 productos x 4 mercados: ~600 puntos -> seguro.
        BATCH_SIZE = 30

        graphql_url = f"https://{self.shop_url}/admin/api/2025-01/graphql.json"
        graphql_headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token
        }

        for batch_start in range(0, len(products), BATCH_SIZE):
            batch = products[batch_start: batch_start + BATCH_SIZE]

            # Construir aliases: p{idx}_{market_id} para cada producto x mercado
            alias_fragments = []
            for idx, product in enumerate(batch):
                product_id = str(product.get("id", ""))
                gid = f"gid://shopify/Product/{product_id}"
                for market in ACTIVE_MARKETS:
                    country = market["country_code"]
                    market_id = market["market_id"]
                    alias_fragments.append(
                        f'p{idx}_{market_id}: product(id: "{gid}") {{\n'
                        f'  contextualPricing(context: {{country: {country}}}) {{\n'
                        f'    priceRange {{ minVariantPrice {{ amount currencyCode }} }}\n'
                        f'  }}\n'
                        f'}}'
                    )

            bulk_query = "query GetMultiMarketPrices {\n" + "\n".join(alias_fragments) + "\n}"

            try:
                response = await asyncio.to_thread(
                    requests.post,
                    graphql_url,
                    json={"query": bulk_query},
                    headers=graphql_headers,
                    timeout=45  # mas tiempo por query mas grande
                )
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    error_msgs = [e.get("message", str(e)) for e in data["errors"]]
                    logging.error(
                        f"[ShopifyPrices] GraphQL errors in batch {batch_start}: {error_msgs}"
                    )
                    continue  # usar fallback REST para este lote

                response_data = data.get("data", {})

                # Parsear aliases del lote
                for idx, product in enumerate(batch):
                    product_id = str(product.get("id", ""))
                    for market in ACTIVE_MARKETS:
                        market_id = market["market_id"]
                        alias_key = f"p{idx}_{market_id}"
                        product_node = response_data.get(alias_key)
                        if not product_node:
                            continue

                        contextual = product_node.get("contextualPricing", {})
                        min_price = (
                            contextual
                            .get("priceRange", {})
                            .get("minVariantPrice", {})
                        )
                        amount_str = min_price.get("amount", "0")
                        currency_code = min_price.get("currencyCode", "")

                        try:
                            amount_float = float(amount_str)
                        except (TypeError, ValueError):
                            amount_float = 0.0

                        if amount_float > 0 and currency_code:
                            market_price_map[market_id][product_id] = {
                                "price": amount_float,
                                "currency": currency_code
                            }

                resolved = sum(len(v) for v in market_price_map.values())
                logging.info(
                    f"[ShopifyPrices] Batch {batch_start}-{batch_start+len(batch)}: "
                    f"{resolved} market-prices resolved total"
                )

            except Exception as batch_err:
                logging.error(
                    f"[ShopifyPrices] Batch {batch_start} error: {batch_err}",
                    exc_info=True
                )
                # Continuar con el siguiente lote; precio REST sera el fallback

        # -- PASO 3: Enriquecer productos con precios multi-mercado -----------
        enriched_products = []
        fallback_count = 0

        for product in products:
            product_id = str(product.get("id", ""))

            # Construir dict market_prices para este producto
            market_prices = {}
            for market in ACTIVE_MARKETS:
                market_id = market["market_id"]
                price_data = market_price_map[market_id].get(product_id)
                if price_data:
                    market_prices[market_id] = price_data

            # Precio "principal" del catalogo: siempre CLP (moneda nativa).
            # Si no tenemos precio CL de GraphQL, extraemos de REST (fallback).
            if "CL" in market_prices:
                native_price = market_prices["CL"]["price"]
                native_currency = market_prices["CL"]["currency"]
            else:
                # Fallback REST: extraer desde variants[0].price
                fallback_count += 1
                variants = product.get("variants") or []
                native_price = 0.0
                native_currency = "CLP"
                if variants:
                    try:
                        native_price = float(variants[0].get("price") or "0")
                    except (TypeError, ValueError):
                        native_price = 0.0
                # Asegurar que CL siempre existe en market_prices
                market_prices["CL"] = {"price": native_price, "currency": native_currency}

            enriched_products.append({
                **product,
                # -- Precio nativo nivel-raiz (compatibilidad hacia atras) ----
                # Codigo que no conoce market_prices sigue funcionando igual.
                "price": native_price,
                "currency": native_currency,
                # -- Precios multi-mercado autorizados por Shopify -------------
                # Consumidos por:
                #   - mcp_personalization_engine._build_advanced_personalization_prompt()
                #   - MarketAdapter._adapt_currency()
                #   - sanitize_rec_for_frontend() (a traves del adapter)
                "market_prices": market_prices,
            })

        logging.info(
            f"[ShopifyPrices] Enrichment complete: "
            f"{len(enriched_products)} products | "
            f"GraphQL: CL={len(market_price_map.get('CL', {}))}, "
            f"CH={len(market_price_map.get('CH', {}))}, "
            f"MX={len(market_price_map.get('MX', {}))}, "
            f"ES={len(market_price_map.get('ES', {}))} | "
            f"REST fallbacks: {fallback_count}"
        )

        return enriched_products

    async def get_prices_for_products(
        self,
        product_ids: List[str],
        markets: List[str] = None
    ) -> Dict[str, Dict[str, Dict]]:
        """
        Obtiene precios multi-mercado para un conjunto pequeno de productos
        via una unica query GraphQL con aliases.

        Disenado para la resolucion lazy de precios: en lugar de pre-calcular
        todo el catalogo al startup (3.062 productos x 4 mercados = 9 minutos),
        esta funcion consulta solo los N productos que se van a mostrar en el
        turno conversacional actual (tipicamente 3-5 productos x 4 mercados
        = 20 aliases), en paralelo con la llamada a Claude.

        La query usa exactamente el mismo patron de aliases que
        get_products_with_shopify_prices(), pero para N productos en lugar
        de batches del catalogo completo.

        Args:
            product_ids: IDs de Shopify (strings, ej. ["9978700071221", ...])
                         Maximo recomendado: 10 productos (40 aliases con 4 mercados).
            markets:     Lista de market_ids a consultar.
                         Default: los 4 mercados activos ["CL", "CH", "MX", "ES"].

        Returns:
            Dict con estructura:
            {
                "9978700071221": {
                    "CL": {"price": 160000.0, "currency": "CLP"},
                    "CH": {"price": 26.0,     "currency": "CHF"},
                    "MX": {"price": 3200.0,   "currency": "MXN"},
                    "ES": {"price": 159.0,    "currency": "EUR"},
                },
                ...
            }
            Productos sin precio retornan un dict vacio para ese market_id.
            Si la query falla completamente, retorna {} para todos los productos.
        """
        import asyncio

        if not product_ids:
            return {}

        # Mercados por defecto: los 4 activos en Shopify Admin (AI-Shoppings)
        ACTIVE_MARKETS = [
            {"market_id": m, "country_code": m}
            for m in (markets or ["CL", "CH", "MX", "ES"])
        ]

        gql_url = f"https://{self.shop_url}/admin/api/2025-01/graphql.json"
        gql_headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token,
        }

        # Construir query GraphQL con un alias por (producto, mercado).
        # Formato: p{idx}_{market_id}: product(id: "gid://...") { contextualPricing ... }
        # Con 5 productos x 4 mercados = 20 aliases — muy por debajo del
        # limite de Shopify Admin GraphQL (1000 puntos de coste por request).
        alias_fragments = []
        for idx, pid in enumerate(product_ids):
            gid = f"gid://shopify/Product/{pid}"
            for market in ACTIVE_MARKETS:
                alias_fragments.append(
                    f'p{idx}_{market["market_id"]}: product(id: "{gid}") {{\n'
                    f'  contextualPricing(context: {{country: {market["country_code"]}}}) {{\n'
                    f'    priceRange {{ minVariantPrice {{ amount currencyCode }} }}\n'
                    f'  }}\n'
                    f'}}'
                )

        bulk_query = (
            "query GetPricesForTurn {\n"
            + "\n".join(alias_fragments)
            + "\n}"
        )

        try:
            response = await asyncio.to_thread(
                requests.post,
                gql_url,
                json={"query": bulk_query},
                headers=gql_headers,
                timeout=10,  # timeout ajustado: pocos productos, debe ser rapido
            )
            response.raise_for_status()
            resp_data = response.json()

            if "errors" in resp_data:
                err_msgs = [e.get("message", str(e)) for e in resp_data["errors"]]
                logging.warning(
                    f"[get_prices_for_products] GraphQL errors: {err_msgs}"
                )
                return {}

            graph_data = resp_data.get("data", {})

            # Parsear aliases y construir el dict de resultado
            result: Dict[str, Dict[str, Dict]] = {pid: {} for pid in product_ids}

            for idx, pid in enumerate(product_ids):
                for market in ACTIVE_MARKETS:
                    mid = market["market_id"]
                    node = graph_data.get(f"p{idx}_{mid}")
                    if not node:
                        continue
                    min_price = (
                        node.get("contextualPricing", {})
                        .get("priceRange", {})
                        .get("minVariantPrice", {})
                    )
                    try:
                        amt = float(min_price.get("amount", "0"))
                    except (TypeError, ValueError):
                        amt = 0.0
                    cur = min_price.get("currencyCode", "")
                    if amt > 0 and cur:
                        result[pid][mid] = {"price": amt, "currency": cur}

            logging.info(
                f"[get_prices_for_products] OK: "
                f"{len(product_ids)} productos x {len(ACTIVE_MARKETS)} mercados"
            )
            return result

        except Exception as e:
            logging.warning(
                f"[get_prices_for_products] Fallo: {e}. "
                f"_format_price_for_market usara CLP_RATES como fallback."
            )
            return {}


# ==========================================================================
# GRAPHQL RETRY LOGIC
# ==========================================================================

    async def _graphql_query_with_retry(
        self, 
        query: str, 
        variables: Dict = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> Dict:
        """
        Execute GraphQL query with retry logic for transient network errors.
        
        Retries ONLY for: network timeouts, connection errors, 5xx server errors.
        Does NOT retry for: GraphQL logical errors, 4xx client errors.
        """
        import asyncio
        from requests.exceptions import RequestException, Timeout, ConnectionError
        
        url = f"https://{self.shop_url}/admin/api/2025-01/graphql.json"
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token
        }
        
        retries = 0
        
        while retries <= max_retries:
            try:
                response = await asyncio.to_thread(
                    requests.post, url, json=payload, headers=headers, timeout=30
                )
                
                if response.status_code >= 500:
                    raise RequestException(f"Shopify server error: {response.status_code}")
                
                response.raise_for_status()
                data = response.json()
                
                if "errors" in data:
                    error_msgs = [err.get("message", str(err)) for err in data["errors"]]
                    raise Exception(f"GraphQL errors: {'; '.join(error_msgs)}")
                
                return data.get("data", {})
                
            except Timeout as e:
                retries += 1
                if retries <= max_retries:
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.warning(f"GraphQL timeout. Retry {retries}/{max_retries} in {wait_time}s. Error: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Max retries ({max_retries}) reached. Giving up.")
                    raise
                    
            except ConnectionError as e:
                retries += 1
                if retries <= max_retries:
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.warning(f"GraphQL connection error. Retry {retries}/{max_retries} in {wait_time}s. Error: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Max retries ({max_retries}) reached. Giving up.")
                    raise
                    
            except RequestException as e:
                if "5" in str(e) and retries < max_retries:
                    retries += 1
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.warning(f"GraphQL request failed (retriable). Retry {retries}/{max_retries} in {wait_time}s. Error: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"GraphQL request failed (non-retriable): {e}")
                    raise
                    
            except Exception as e:
                logger.error(f"GraphQL query failed: {e}")
                raise
