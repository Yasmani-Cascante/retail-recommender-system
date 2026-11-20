# Inventario de contenido de plantilla -- politicas legales (R-10) y paginas de la base de conocimiento (R-14) (20/11/2026)

Documento de trabajo para Yasmani, complemento de `DCT_Frescura_Contenido_KB_20112026.md` (seccion 4). Compara,
tema por tema, lo que dicen las politicas legales de Shopify, las paginas de la base de conocimiento (las que el
chat sirve a los clientes) y la configuracion real de la tienda.

**Aclaracion de Yasmani (20/11/2026) [Y]**: `ai-shoppings` es una tienda de demostracion sin clientes reales. Los
datos de las paginas y de las politicas son **de ejemplo a proposito**; cada tienda cliente aportara los suyos.
Por eso este inventario no es una lista de correcciones urgentes, sino:
1. el **caso de prueba** de lo que un verificador de contenido por tienda deberia detectar (seccion 6, punto 6);
2. la **lista de datos que cada tienda cliente debe aportar** antes de activar el chat (seccion 7);
3. una lista de incoherencias de la demo, a corregir solo si confunden las pruebas o las demostraciones.

Convencion: [V] verificado (Admin API de Shopify, solo lectura, 20/11/2026); [H] hipotesis; [Y] a confirmar o
decidir por Yasmani. **No es asesoria legal**: senala que alinear; el texto final y lo que exige la ley de Chile
y de Suiza los decide Yasmani, con asesoria si hace falta.

---

## 1. Resumen

- **R-10 (politicas legales de Shopify con contenido de plantilla)** se confirma y se amplia [V]: marcadores
  `[INSERT ...]` y `[LINK TO ...]` en devoluciones y terminos; sin politica de envios; datos de contacto vacios
  (telefono, IVA) y un correo personal.
- **R-14 (nuevo): las paginas de la base de conocimiento tienen contenido ficticio de plantilla** [V]: correos de
  `tutienda.com`, telefonos `+1 (555) 123-4567`, `+1 (800) 555-0123` y `+52 55 1234 5678`, direccion "Calle
  Principal 123, Ciudad, Pais", envios a Estados Unidos, Espana y Mexico, monedas USD/EUR/MXN, RFC (dato fiscal de
  Mexico), un "VIP Club" y tarjetas regalo. **Es el contenido que el chat sirve tal cual o reformulado**: es la misma
  clase de riesgo que R-2 (contenido ficticio de `SimpleKnowledgeBase`), pero en la fuente de verdad. En la demo
  es intencionado [Y]; en una tienda real seria un riesgo, y hoy el sistema no lo detectaria.
- **Las traducciones copian lo mismo** [V: ingles de "Como funcionan los envios", mismos precios en USD, mismos
  destinos y `shipping@ai-shoppings.com`]: hay que corregir espanol, ingles y frances.
- **Contradicciones entre paginas** de la propia base de conocimiento (envio gratis desde 50 o 75, reembolso en
  5-7 o 7-10 dias, cuotas desde 50 o 100, modificar el pedido 30 min o 2 h).
- La tienda esta cerrada con contrasena [V] y es de demostracion [Y]: ningun cliente lo ha visto. En una tienda
  cliente real, este contenido debe sustituirse antes de activar el chat.

## 2. Configuracion real de la tienda (referencia) [V]

| Dato | Valor real en Shopify |
|---|---|
| Pais de la tienda | Chile |
| Moneda base | CLP |
| Monedas de presentacion | CHF, CLP, MXN |
| Idiomas publicados | es (principal), en, fr |
| Envio nacional | Chile: "Standard" 0 CLP |
| Envio internacional | 28 paises: AE, AT, AU, BE, CA, CH, CZ, DE, DK, ES, FI, FR, GB, HK, IE, IL, IT, JP, KR, MY, NL, NO, NZ, PL, PT, SE, SG, US. Tarifas: "Standard" 19.000 CLP, "Free International Shipping" 0 CLP, "International Shipping" 30 CLP (condiciones de cada tarifa no consultadas; 30 CLP parece un error de configuracion [H]) |
| Mexico y resto de America Latina | **No estan** en ninguna zona de envio |
| Billeteras digitales (Apple Pay, Google Pay) | Ninguna disponible (`supportedDigitalWallets` vacio) |
| PayPal y tarjetas | No consultado [H: revisar en Ajustes > Pagos] |
| Politicas configuradas | Privacidad (30/10/2026), Reembolso, Cancelaciones (suscripciones), Terminos, Contacto. **Sin politica de envios** |
| Pagina "Contact" | Publicada, cuerpo vacio [H: usa la plantilla de formulario de contacto] |

## 3. Datos de contacto que aparecen

| Donde | Correo | Telefono / direccion |
|---|---|---|
| Politicas de Shopify (contacto, reembolso, privacidad, terminos) | `yasmani.cascante@gmail.com` | Telefono vacio; direccion "Chile"; `[INSERT BUSINESS ADDRESS]`, `[INSERT BUSINESS PHONE NUMBER]`, `[INSERT RETURN ADDRESS]` |
| Como funcionan los envios | `shipping@ai-shoppings.com` | - |
| Donde esta mi pedido | `orders@ai-shoppings.com` | - |
| Guia de tallas | `sizing@ai-shoppings.com` | - |
| Metodos de pago | `billing@ai-shoppings.com`, `payments@ai-shoppings.com` | - |
| Garantia y defectos | `warranty@ai-shoppings.com` | `+1 (800) 555-0123`; chat L-V 9-18 |
| Cancelaciones y modificaciones | `pedidos@tutienda.com` | `+1 (555) 123-4567` (telefono y WhatsApp) |
| Politica de privacidad (pagina) | `privacy@tutienda.com` | `+1 (555) 123-4567`; "Calle Principal 123, Ciudad, Pais" |
| Preguntas frecuentes | `info@tutienda.com`, `privacy@tutienda.com` | `+1 (555) 123-4567` (telefono y WhatsApp); `@tutienda` en redes |
| Cuidado de productos; Materiales y tejidos | `info@tutienda.com` | - |
| Mensaje de ayuda general (oculta; el chat la sirve para `unknown`) | `ayuda@tutienda.com` | `+52 55 1234 5678` |

`tutienda.com` es el dominio de la plantilla. Si `ai-shoppings.com` es un dominio de la tienda con esos buzones
activos [Y: confirmar]; si no, esos correos tampoco son reales.

## 4. Contradicciones y datos sin respaldo, por tema

| Tema | Politicas de Shopify | Paginas de la base de conocimiento | Configuracion real | A decidir [Y] |
|---|---|---|---|---|
| Plazo para devolver | 30 dias desde la recepcion; 14 dias de desistimiento en la UE | Devoluciones: 30 dias. FAQ: 30 dias desde la entrega | - | Plazo unico; que exige la ley de Chile y de Suiza (Suiza no es UE) |
| Plazo de reembolso | 10 dias habiles tras aprobar; contactar si pasan 15 | Devoluciones: "procesamiento 5-7 dias habiles". FAQ: 7-10 dias tras recibir. Cancelaciones: tarjeta 5-7, PayPal 3-5, transferencia 7-10 | - | Un plazo y una sola redaccion |
| Coste del envio de devolucion | Enviamos la etiqueta de devolucion | Devoluciones: "etiqueta prepagada". Garantia: etiqueta GRATIS por defecto. FAQ: el cliente paga si cambia de opinion | - | Quien paga en cada caso |
| Direccion de devolucion | `[INSERT RETURN ADDRESS]` | No aparece | Tienda en Chile | Direccion real |
| Articulos no devolvibles | Rebajas y tarjetas regalo no | No lo dicen; garantia limitada para "segunda" | - | Alinear |
| Destinos de envio | Sin politica de envios | Envios: EE. UU., Espana (peninsula y Baleares), Mexico, America Latina. FAQ: toda America Latina y Espana | Chile + 28 paises (incluye CH, US, ES, FR, DE, IT); **sin Mexico ni America Latina** | Lista real, o remitir al checkout |
| Precio del envio | - | Envios: gratis desde 50 USD; 5,99 / 12,99 / 19,99 USD. FAQ: gratis desde 75 | Chile 0 CLP; internacional 19.000 CLP, 0 CLP o 30 CLP | No repetir precios en las paginas: "se calcula en el checkout" |
| Plazos de entrega | - | Envios: 5-7 / 2-3 / 1-2 dias. FAQ: internacional 10-15 | No configurado como dato consultable | Plazos reales por zona |
| Monedas | - | USD, EUR, MXN | CLP, CHF, MXN | Alinear o no enumerarlas |
| Medios de pago | - | Visa, Mastercard, Amex, Discover, PayPal, Apple Pay, Google Pay, transferencia (>500), Shopify Payments | Apple Pay y Google Pay no disponibles; resto no consultado [H] | Lista real (Ajustes > Pagos) |
| Cuotas sin interes | - | Pagos: desde 100 (3), 300 (6), 500 (12). FAQ: desde 50 | - | Existen? |
| Facturacion | - | RFC (Mexico); `billing@ai-shoppings.com` | Tienda en Chile | Dato fiscal correcto para Chile/Suiza |
| Modificar o cancelar un pedido | Politica de "Cancellations" = plantilla de suscripciones, preventa y "try before you buy" | Cancelaciones: modificar hasta 30 min; cancelar gratis <1 h, 1-24 h con un cargo de 2 $. Donde esta mi pedido: gratis antes de 2 h | - | Reglas reales; politica de Shopify adecuada a la tienda |
| Garantia | - | 30 / 60 / 90 dias / 1 ano segun producto; "Garantia de satisfaccion 100 %, sin preguntas, 30 dias" | - | Compromisos reales (un "sin preguntas" es una promesa fuerte) |
| Privacidad | Politica generada el 30/10/2026, coherente, contacto gmail | Pagina con "Tu Tienda", `privacy@tutienda.com`, "Calle Principal 123", conservacion 5 anos | - | La legal es la de Shopify: la pagina deberia resumirla y enlazarla, sin datos propios |
| Funciones anunciadas | - | FAQ: "VIP Club", tarjetas regalo de 25-200, 10 % por newsletter, chat L-S 9-20, WhatsApp, pedidos por telefono, calculadora de tallas | - | Existen? Si no, retirarlas |
| Seguridad | - | "Certificado PCI-DSS", "SSL 256 bits", "procesamiento via Shopify Payments" | Shopify Payments en Chile [H: verificar disponibilidad] | Afirmar solo lo que es cierto |
| Terminos del servicio | Ley de Chile; `[INSERT TRADING NAME/BUSINESS ADDRESS/PHONE/REGISTRATION/VAT]`; `[LINK TO REFUND POLICY]`, `[LINK TO PRIVACY POLICY]` | - | - | Completar o regenerar |

## 5. Como se propaga una correccion

1. Editar la pagina en espanol en Shopify y despues sus traducciones en Translate & Adapt (ingles y frances). Las
   traducciones actuales copian los mismos datos ficticios [V, muestra del ingles].
2. La base de conocimiento recoge el cambio en el siguiente ciclo de sincronizacion (cada 5 min mientras haya una
   instancia viva) o en el siguiente arranque; con R-13a incluye el frances [V].
3. Redis se invalida al cambiar la pagina [V, codigo].
4. Comprobar con `check_kb_links.py` (fecha de `last_synced`) y preguntando en el chat.

## 6. Recomendaciones

1. **Decidir primero los datos reales** (seccion 7) y despues reescribir: muchas paginas comparten los mismos datos.
2. **No repetir en las paginas lo que vive en la configuracion de Shopify** (precios y destinos de envio, monedas,
   medios de pago): decir "se calcula en el checkout" o enlazar. Es la leccion de la lista escrita a mano: una
   copia manual se desfasa sin avisar.
3. **Una sola fuente por tema**: la politica legal de Shopify manda; la pagina de la base de conocimiento la
   resume con las mismas cifras y la enlaza.
4. **Retirar las funciones que no existen** (VIP Club, tarjetas regalo, WhatsApp, chat con horario, telefono) y
   todo correo de `tutienda.com`.
5. Revisar `mensaje-de-ayuda-general` (oculta, pero el chat la usa para `unknown`): `ayuda@tutienda.com` y `+52`.
6. **Verificador de contenido por tienda** (propuesta de producto): reglas simples sobre las paginas de la base de
   conocimiento y las politicas antes de activar el chat: marcadores `[INSERT` y `[LINK`, dominios de plantilla,
   telefonos `555`, monedas, paises y medios de pago que no esten en la configuracion de la tienda, y cifras que se
   contradicen entre paginas. Este inventario es su primer caso de prueba.

## 7. Datos que cada tienda cliente debe aportar (lista de incorporacion)

Para la demo, solo si se decide hacerla coherente [Y].

1. Canales de contacto reales: correo (dominio propio o gmail), telefono y WhatsApp si existen.
2. Direccion de devoluciones.
3. Destinos de envio, tarifas y plazos reales (o la decision de remitir al checkout).
4. Medios de pago activos (tarjetas, PayPal, transferencia, cuotas).
5. Funciones que existen: programa de fidelidad, tarjetas regalo, newsletter con descuento, chat con horario.
6. Plazos y condiciones de devolucion, reembolso, cambios y garantia.
7. Dominio y buzones propios de la tienda (en la demo: si `ai-shoppings.com` existe y tiene esos buzones).
