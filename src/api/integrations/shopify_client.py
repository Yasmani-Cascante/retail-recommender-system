from asyncio.log import logger
import requests
from typing import List, Dict
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
        self.api_url = f"https://{self.shop_url}/admin/api/2024-01"
        logging.info(f"Initializing Shopify client with:")
        logging.info(f"Shop URL: {self.shop_url}")
        logging.info(f"API URL: {self.api_url}")
        logging.info(f"Access Token: {self.access_token[:4]}...")

    def get_products(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """
        Obtiene productos de Shopify con paginación y límites específicos.
        
        Args:
            limit (int, optional): Número máximo de productos a retornar. None para todos.
            offset (int): Número de productos a saltar (para paginación).
        
        Returns:
            List[Dict]: Lista de productos paginada
        """
        try:
            all_products = []
            
            # Optimización: Si el límite es pequeño, usar directamente
            if limit and limit <= 50:
                url = f"{self.api_url}/products.json?limit={limit}"
                logging.info(f"Using optimized fetch for small limit: {limit}")
            else:
                # Para límites grandes o sin límite, usar paginación estándar
                url = f"{self.api_url}/products.json?limit=250"
            
            # Manejar offset saltando productos si es necesario
            products_to_skip = offset
            products_collected = 0
            
            # Continuar paginando mientras haya páginas siguientes
            while url:
                logging.info(f"Fetching products from: {url}")
                
                # Realizar la petición
                response = self._make_request_with_retry(url)
                
                # Extraer los productos de la respuesta
                data = response.json()
                products = data.get('products', [])
                
                if products:
                    logging.info(f"Received {len(products)} products")
                    
                    # Aplicar offset (saltar productos si es necesario)
                    if products_to_skip > 0:
                        if products_to_skip >= len(products):
                            # Saltar toda esta página
                            products_to_skip -= len(products)
                            url = self._get_next_page_url(response)
                            continue
                        else:
                            # Saltar parte de esta página
                            products = products[products_to_skip:]
                            products_to_skip = 0
                    
                    # Aplicar límite si está especificado
                    if limit is not None:
                        remaining_needed = limit - products_collected
                        if remaining_needed <= 0:
                            break
                        if len(products) > remaining_needed:
                            products = products[:remaining_needed]
                    
                    all_products.extend(products)
                    products_collected += len(products)
                    
                    # Si hemos alcanzado el límite exacto, parar
                    if limit is not None and products_collected >= limit:
                        logging.info(f"Reached target limit of {limit} products")
                        break
                else:
                    logging.info("No products found in current page")
                    break
                
                # Buscar el header de paginación para la siguiente página
                url = self._get_next_page_url(response)
            
            logging.info(f"Successfully fetched a total of {len(all_products)} products")
            
            # Mostrar muestra del primer producto si hay datos
            if all_products:
                sample = all_products[0]
                logging.info(f"Sample product: ID={sample.get('id')}, Title={sample.get('title')}")
            
            return all_products
        except Exception as e:
            logging.error(f"Error fetching products: {str(e)}")
            return []
    
    def _get_next_page_url(self, response):
        """
        Extrae la URL de la siguiente página del header Link de la respuesta.
        
        Args:
            response: Respuesta de la API de Shopify
            
        Returns:
            str: URL de la siguiente página o None si no hay más páginas
        """
        # Comprobar si existe el header Link
        if 'Link' not in response.headers:
            return None
        
        links = response.headers['Link'].split(',')
        for link in links:
            if 'rel="next"' in link:
                # Extraer la URL entre < y >
                url = link.split(';')[0].strip().lstrip('<').rstrip('>')
                return url
                
        return None
    
    def _make_request_with_retry(self, url, max_retries=3, retry_delay=1):
        """
        Realiza una petición HTTP con manejo de reintentos y rate limiting
        
        Args:
            url: URL a consultar
            max_retries: Número máximo de reintentos
            retry_delay: Tiempo base de espera entre reintentos (segundos)
            
        Returns:
            Response: Objeto response de requests
        """
        retries = 0
        while retries < max_retries:
            try:
                response = requests.get(url, headers=self.headers)
                
                # Verificar si estamos siendo limitados por rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', retry_delay * 2))
                    logging.warning(f"Rate limit reached. Waiting {retry_after} seconds.")
                    time.sleep(retry_after)
                    retries += 1
                    continue
                
                # Para cualquier otro error, lanzar excepción
                response.raise_for_status()
                
                # Si llegamos aquí, la respuesta es correcta
                return response
                
            except requests.exceptions.RequestException as e:
                retries += 1
                wait_time = retry_delay * (2 ** retries)  # Backoff exponencial
                logging.warning(f"Request error: {str(e)}. Retry {retries}/{max_retries} in {wait_time} seconds.")
                
                if retries < max_retries:
                    time.sleep(wait_time)
                else:
                    logging.error(f"Max retries reached. Giving up.")
                    raise
        
        # Si llegamos aquí, agotamos reintentos
        raise Exception(f"Failed to complete request after {max_retries} retries")

    def get_orders_by_customer(self, customer_id: str, limit: int = 50) -> List[Dict]:
        """
        Obtiene las órdenes de un cliente con paginación.
        
        Args:
            customer_id: ID del cliente
            limit: Número máximo de órdenes a recuperar
            
        Returns:
            List[Dict]: Lista de órdenes
        """
        try:
            all_orders = []
            
            # Construir URL inicial
            url = f"{self.api_url}/orders.json?customer_id={customer_id}&status=any&limit=250"
            
            # Continuar mientras haya páginas y no hayamos excedido el límite
            while url and (limit is None or len(all_orders) < limit):
                logging.info(f"Fetching orders for customer {customer_id}")
                
                # Realizar la petición
                response = self._make_request_with_retry(url)
                
                # Extraer las órdenes
                orders = response.json().get('orders', [])
                
                if orders:
                    # Añadir sólo hasta alcanzar el límite
                    if limit is not None and len(all_orders) + len(orders) > limit:
                        all_orders.extend(orders[:limit - len(all_orders)])
                        break
                    else:
                        all_orders.extend(orders)
                        
                    logging.info(f"Fetched {len(orders)} orders, total so far: {len(all_orders)}")
                else:
                    break
                
                # Buscar la siguiente página
                url = self._get_next_page_url(response)
            
            return all_orders
            
        except Exception as e:
            logging.error(f"Error fetching orders for customer {customer_id}: {str(e)}")
            return []

    def get_customers(self, limit: int = 250) -> List[Dict]:
        """
        Obtiene la lista de clientes de la tienda con paginación.
        
        Args:
            limit: Número máximo de clientes a recuperar, None para todos
            
        Returns:
            List[Dict]: Lista de clientes
        """
        try:
            all_customers = []
            
            # Construir URL inicial
            url = f"{self.api_url}/customers.json?limit=250"
            
            # Continuar mientras haya páginas y no hayamos excedido el límite
            while url and (limit is None or len(all_customers) < limit):
                logging.info(f"Fetching customers")
                
                # Realizar la petición
                response = self._make_request_with_retry(url)
                
                # Extraer los clientes
                customers = response.json().get('customers', [])
                
                if customers:
                    # Añadir sólo hasta alcanzar el límite
                    if limit is not None and len(all_customers) + len(customers) > limit:
                        all_customers.extend(customers[:limit - len(all_customers)])
                        break
                    else:
                        all_customers.extend(customers)
                        
                    logging.info(f"Fetched {len(customers)} customers, total so far: {len(all_customers)}")
                else:
                    break
                
                # Buscar la siguiente página
                url = self._get_next_page_url(response)
            
            return all_customers
            
        except Exception as e:
            logging.error(f"Error fetching customers: {str(e)}")
            return []
            
    def get_product_count(self) -> int:
        """
        Obtiene el número total de productos en la tienda.
        
        Returns:
            int: Número total de productos
        """
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
        

    # ══════════════════════════════════════════════════════════════════════
    # GRAPHQL API SUPPORT
    # ══════════════════════════════════════════════════════════════════════
    
    async def _graphql_query(self, query: str, variables: Dict = None) -> Dict:
        """
        Execute GraphQL query against Shopify Admin API (ASYNC).
        
        This method enables async GraphQL queries while maintaining compatibility
        with the existing sync REST methods. Uses asyncio.to_thread() to run
        the sync HTTP call in a thread pool, preventing event loop blocking.
        
        Architecture Note:
        -----------------
        - Parent class (ShopifyIntegration): Mix of sync REST + async GraphQL
        - Child classes can use either sync REST or async GraphQL methods
        - asyncio.to_thread() enables async compatibility without rewriting
          existing sync code
        
        Args:
            query: GraphQL query string (not mutation)
            variables: Optional query variables as dict
            
        Returns:
            Dict containing GraphQL response data
            
        Raises:
            Exception: If HTTP request fails or GraphQL returns errors
            
        Example:
            >>> query = '''
            ... query getProduct($id: ID!) {
            ...   product(id: $id) {
            ...     id
            ...     title
            ...   }
            ... }
            ... '''
            >>> variables = {"id": "gid://shopify/Product/123"}
            >>> data = await client._graphql_query(query, variables)
            >>> print(data["product"]["title"])
        """
        import asyncio
        
        # Build GraphQL endpoint URL
        url = f"https://{self.shop_url}/admin/api/2024-01/graphql.json"
        
        # Build request payload
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        # Build headers (reuse existing access token)
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token
        }
        
        try:
            # Execute sync HTTP POST in thread pool (non-blocking async)
            # This prevents blocking the event loop while maintaining
            # compatibility with requests library
            response = await asyncio.to_thread(
                requests.post,
                url,
                json=payload,
                headers=headers,
                timeout=30  # 30s timeout for GraphQL queries
            )
            
            # Check HTTP status
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            
            # Check for GraphQL-specific errors
            # GraphQL can return 200 OK but still have errors in response
            if "errors" in data:
                error_msgs = [
                    err.get("message", str(err)) 
                    for err in data["errors"]
                ]
                raise Exception(f"GraphQL errors: {'; '.join(error_msgs)}")
            
            # Return data portion of response
            # GraphQL wraps data in {"data": {...}}
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

# ══════════════════════════════════════════════════════════════════════════
# CÓDIGO OPCIONAL - RETRY LOGIC
# ══════════════════════════════════════════════════════════════════════════

    async def _graphql_query_with_retry(
        self, 
        query: str, 
        variables: Dict = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> Dict:
        """
        Execute GraphQL query with retry logic for network errors.
        
        This is an ENHANCED version of _graphql_query() with retry capabilities
        for transient network issues. Use this when you need extra robustness.
        
        Retries ONLY for:
        - Network timeouts
        - Connection errors  
        - 5xx server errors (Shopify internal errors)
        
        Does NOT retry for:
        - GraphQL logical errors (field doesn't exist, invalid query)
        - 4xx client errors (authentication, malformed request)
        
        Args:
            query: GraphQL query string
            variables: Optional query variables
            max_retries: Maximum retry attempts (default: 3)
            retry_delay: Base delay between retries in seconds (default: 1.0)
            
        Returns:
            Dict containing GraphQL response data
            
        Raises:
            Exception: If all retries exhausted or non-retriable error
            
        Example:
            >>> # Use for critical operations that need extra robustness
            >>> data = await client._graphql_query_with_retry(query, variables)
        """
        import asyncio
        from requests.exceptions import RequestException, Timeout, ConnectionError
        
        # Build GraphQL endpoint URL
        url = f"https://{self.shop_url}/admin/api/2024-01/graphql.json"
        
        # Build request payload
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        # Build headers
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token
        }
        
        retries = 0
        
        while retries <= max_retries:
            try:
                # Execute sync HTTP POST in thread pool
                response = await asyncio.to_thread(
                    requests.post,
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                # Check for 5xx server errors (retriable)
                if response.status_code >= 500:
                    raise RequestException(
                        f"Shopify server error: {response.status_code}"
                    )
                
                # Check for 4xx client errors (NOT retriable)
                response.raise_for_status()
                
                # Parse JSON response
                data = response.json()
                
                # Check for GraphQL-specific errors (NOT retriable)
                if "errors" in data:
                    error_msgs = [
                        err.get("message", str(err)) 
                        for err in data["errors"]
                    ]
                    raise Exception(f"GraphQL errors: {'; '.join(error_msgs)}")
                
                # Success - return data
                return data.get("data", {})
                
            except Timeout as e:
                # Network timeout - retriable
                retries += 1
                if retries <= max_retries:
                    wait_time = retry_delay * (2 ** (retries - 1))  # Exponential backoff
                    logger.warning(
                        f"GraphQL timeout for query. "
                        f"Retry {retries}/{max_retries} in {wait_time}s. "
                        f"Error: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Max retries ({max_retries}) reached for GraphQL query. "
                        f"Giving up."
                    )
                    raise
                    
            except ConnectionError as e:
                # Network/connection error - retriable
                retries += 1
                if retries <= max_retries:
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.warning(
                        f"GraphQL connection error. "
                        f"Retry {retries}/{max_retries} in {wait_time}s. "
                        f"Error: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Max retries ({max_retries}) reached for GraphQL query. "
                        f"Giving up."
                    )
                    raise
                    
            except RequestException as e:
                # Check if it's a 5xx error (retriable)
                if "5" in str(e) and retries < max_retries:
                    retries += 1
                    wait_time = retry_delay * (2 ** (retries - 1))
                    logger.warning(
                        f"GraphQL request failed (retriable). "
                        f"Retry {retries}/{max_retries} in {wait_time}s. "
                        f"Error: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # 4xx error or max retries - don't retry
                    logger.error(f"GraphQL request failed (non-retriable): {e}")
                    raise
                    
            except Exception as e:
                # GraphQL logical error or other non-network error - don't retry
                logger.error(f"GraphQL query failed: {e}")
                raise
    