"""
Knowledge Base - Simple Hardcoded Implementation
Provides answers to common informational queries.

Design Principles:
- Hardcoded for MVP (easy to migrate to DB later)
- Markdown formatting (rich text support)
- Multi-language ready (ES/EN for now)
- Product-context aware (can customize answers by product category)
- Easy to extend (just add to dictionaries)
"""

import logging
from typing import Optional, List, Dict
from datetime import datetime

from src.api.core.intent_types import (
    InformationalSubIntent,
    KnowledgeBaseAnswer
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# KNOWLEDGE BASE CONTENT
# ═══════════════════════════════════════════════════════════════

class KnowledgeBaseContent:
    """
    Hardcoded knowledge base content.
    
    Structure:
    - POLICIES: Return, shipping, payment policies
    - PRODUCT_INFO: Material, sizing, care instructions
    - GENERAL_FAQ: General questions
    
    Each entry can have:
    - "general": Default answer
    - "[CATEGORY]": Category-specific answer (e.g., "ZAPATOS", "VESTIDOS")
    """
    
    # ───────────────────────────────────────────────────────────
    # RETURN POLICY
    # ───────────────────────────────────────────────────────────
    
    RETURN_POLICY = {
        "general": """
**📦 Política de Devoluciones**

✅ **Plazo de Devolución**
- 30 días naturales desde la fecha de recepción
- Extensión a 60 días en período navideño (Nov 15 - Ene 15)

✅ **Condiciones del Producto**
- Sin uso aparente (sin manchas, olores, desgaste)
- Etiquetas originales adheridas y legibles
- Empaque original (caja, bolsa protectora)
- Sin alteraciones ni modificaciones

✅ **Proceso de Devolución**
1. Inicia tu devolución desde **Mi Cuenta > Mis Pedidos**
2. Selecciona el(los) producto(s) a devolver
3. Elige motivo de devolución
4. Descarga e imprime etiqueta de envío **GRATIS**
5. Empaca el producto y envía
6. Recibirás reembolso en **5-7 días hábiles**

✅ **Opciones de Reembolso**
- **Reembolso completo** a método de pago original
- **Cambio por talla/color** diferente (sujeto a disponibilidad)
- **Crédito en tienda** (10% extra de bonificación)

❌ **Excepciones**
- Productos de higiene personal (lencería, trajes de baño)
- Artículos en liquidación o descuento >50%
- Productos personalizados o bajo pedido
- Joyería con sellos rotos

💡 **¿Necesitas ayuda?**
- WhatsApp: +52 55 1234 5678 (L-V 9am-7pm)
- Email: devoluciones@tutienda.com
- Chat en vivo: [Iniciar Chat →](/help/chat)
""",
        
        "ZAPATOS": """
**👟 Devolución de Calzado**

✅ **Condiciones Especiales para Zapatos**
- **Plazo**: 30 días desde recepción
- **Estado**: Sin uso en exteriores (suelas limpias e intactas)
- **Prueba**: Puedes probarlos en casa sobre alfombra o superficie limpia
- **Caja**: Debe incluirse caja original sin daños

✅ **Proceso Simplificado**
1. Solicita devolución en línea
2. Recibe etiqueta de envío **GRATIS**
3. Empaca con caja original
4. Reembolso en **5-7 días hábiles**

💡 **Consejo Pro**
Prueba tus zapatos en casa con calcetines durante 15-20 minutos antes de decidir. 
Caminar sobre alfombra no cuenta como "uso exterior".

✅ **Cambio Express por Talla**
¿Te quedaron grandes/chicos? Cambio por talla diferente **SIN COSTO** 
y te llega en **48-72 horas**.

❌ **No Aceptamos Devoluciones Si**
- Suelas muestran desgaste por uso exterior
- Zapatos tienen manchas, rasguños o daños
- Caja destruida o faltante (excepto si llegó así)
- Han pasado más de 30 días

📞 **Dudas sobre tu talla?**
Consulta nuestra [Guía de Tallas →](/help/shoe-sizing) antes de ordenar.
""",
        
        "VESTIDOS": """
**👗 Devolución de Vestidos**

✅ **Política para Vestimenta**
- **Plazo**: 30 días desde recepción (60 días en temporada festiva)
- **Estado**: Sin alteraciones, etiquetas adheridas, sin manchas/olores
- **Empaque**: Bolsa protectora original incluida

✅ **Consideraciones Especiales**
- **Vestidos de noche/gala**: Revisa cuidadosamente antes de quitar etiquetas
- **Vestidos con pedrería**: Verifica que no falten aplicaciones
- **Vestidos blancos**: Evita contacto con maquillaje al probarte

💡 **Tips para Probarte en Casa**
1. Lava tus manos antes de manipular el vestido
2. No uses maquillaje, cremas o perfumes al probarte
3. Prueba sobre ropa interior similar a la que usarás
4. Toma fotos si tienes dudas sobre ajuste (envíalas a nuestro chat)

✅ **Cambio por Talla**
Cambio **GRATIS** por talla diferente si:
- Solicitado dentro de 15 días
- Etiquetas intactas
- Sin uso/alteraciones

❌ **No Podemos Aceptar Si**
- Tiene manchas de maquillaje, sudor o perfume
- Falta alguna aplicación o accesorio
- Costuras alteradas o descosidas
- Etiquetas removidas o dañadas

📏 **¿Dudas de talla?**
Usa nuestra [Calculadora de Tallas →](/help/dress-sizing) 
o chatea con nosotros para asesoría personalizada.
"""
    }
    
    # ───────────────────────────────────────────────────────────
    # SHIPPING POLICY
    # ───────────────────────────────────────────────────────────
    
    SHIPPING_POLICY = {
        "general": """
**🚚 Información de Envío**

✅ **Tiempos de Entrega Estimados**

| Destino | Tiempo Estimado | Costo Estándar |
|---------|----------------|----------------|
| Ciudad de México | 2-3 días hábiles | $99 MXN |
| Área Metropolitana | 3-4 días hábiles | $99 MXN |
| Guadalajara, Monterrey | 3-4 días hábiles | $129 MXN |
| Ciudades principales | 4-5 días hábiles | $149 MXN |
| Zonas rurales/remotas | 5-8 días hábiles | $199 MXN |

✅ **Envío GRATIS** 🎉
- En compras mayores a **$1,000 MXN**
- Aplica a todo México
- Sin código necesario (se aplica automáticamente)

✅ **Envío Express** ⚡
- Disponible para CDMX y Área Metropolitana
- **Entrega en 24-48 horas**
- Costo: **$249 MXN**
- Pedidos antes de 2pm → Entrega al día siguiente (días hábiles)

✅ **Rastreo de Pedido**
- Número de rastreo enviado por email dentro de 24h
- Rastrea tu paquete en: [Mi Cuenta > Mis Pedidos](/account/orders)
- Notificaciones por SMS/WhatsApp (opcional)

✅ **Horarios de Entrega**
- Lunes a Viernes: 9am - 6pm
- Sábados: 9am - 2pm (área metropolitana)
- No entregamos domingos ni días festivos

❓ **¿Qué Paquetería Usamos?**
- **FedEx** (envíos express y estándar)
- **Estafeta** (envíos nacionales)
- **DHL** (zonas específicas)

💡 **Consejos para Recibir tu Pedido**
- Proporciona número de teléfono actualizado
- Especifica referencias de ubicación
- Si no estarás, deja autorización para vecino/portero

📦 **¿No Recibiste tu Pedido?**
Contáctanos inmediatamente:
- WhatsApp: +52 55 1234 5678
- Email: envios@tutienda.com
- Tiempo de respuesta: < 2 horas (días hábiles)
""",
        
        "cost": """
**💰 Costos de Envío**

✅ **Envío Estándar**
- **GRATIS** en compras >$1,000 MXN ✨
- $99 MXN (CDMX y Área Metropolitana)
- $129 MXN (Guadalajara, Monterrey, ciudades principales)
- $149 MXN (Resto del país)
- $199 MXN (Zonas rurales/remotas)

✅ **Envío Express** ⚡ (24-48h)
- $249 MXN (CDMX y Área Metropolitana)
- $349 MXN (Guadalajara, Monterrey)
- No disponible para zonas rurales

💡 **Promociones Especiales**
- **Cyber Monday**: Envío gratis sin mínimo
- **Black Friday**: 50% descuento en envío express
- **Temporada Navideña**: Envío gratis en compras >$750 MXN

📊 **Calculadora de Envío**
Agrega productos al carrito para ver costo exacto de envío a tu código postal.

💸 **¿Cuánto te Falta para Envío Gratis?**
El sistema te muestra en tiempo real cuánto debes agregar:
- Ejemplo: "¡Agrega solo $250 MXN más para envío GRATIS!"
""",
        
        "time": """
**⏱️ Tiempos de Entrega**

✅ **Procesamiento del Pedido**
- Pedidos antes de 2pm: Procesados el mismo día
- Pedidos después de 2pm: Procesados al día siguiente
- Fines de semana: Procesados el lunes siguiente

✅ **Tiempo en Tránsito**

**CDMX y Área Metropolitana:**
- Estándar: 2-3 días hábiles
- Express: 24-48 horas

**Ciudades Principales** (GDL, MTY, Puebla, QRO):
- Estándar: 3-4 días hábiles
- Express: 48-72 horas (solo GDL, MTY)

**Resto del País:**
- Estándar: 4-5 días hábiles
- Zonas rurales: 5-8 días hábiles

**Península de Yucatán / Baja California:**
- 5-7 días hábiles (distancia)

❓ **¿Días Hábiles?**
Lunes a Viernes, excluyendo días festivos oficiales.

⚠️ **Retrasos Posibles**
- Condiciones climáticas extremas
- Días festivos (Navidad, Año Nuevo, etc.)
- Alta demanda (Buen Fin, Hot Sale)
- Direcciones incompletas/incorrectas

💡 **¿Cuándo Llegará mi Pedido?**
Consulta fecha estimada en:
1. Email de confirmación
2. Rastreo en tiempo real
3. [Mi Cuenta > Mis Pedidos](/account/orders)

🚨 **¿Pedido Urgente?**
Usa **Envío Express** y ordena antes de 2pm para entrega al día siguiente (CDMX).
"""
    }
    
    # ───────────────────────────────────────────────────────────
    # PAYMENT POLICY
    # ───────────────────────────────────────────────────────────
    
    PAYMENT_POLICY = {
        "general": """
**💳 Métodos de Pago Aceptados**

✅ **Tarjetas de Crédito/Débito**
- Visa, MasterCard, American Express
- Tarjetas nacionales e internacionales
- Procesamiento seguro 3D Secure
- Cargo al momento de realizar pedido

✅ **Meses Sin Intereses** 🎉
- 3 MSI en compras desde $1,000 MXN
- 6 MSI en compras desde $2,000 MXN
- 9 MSI en compras desde $4,000 MXN
- 12 MSI en compras desde $6,000 MXN

**Bancos participantes:**
- Citibanamex, BBVA, Santander, HSBC
- Scotiabank, Banorte, Inbursa

✅ **Pagos Digitales**
- **PayPal** (instantáneo)
- **Mercado Pago** (instantáneo)
- **Apple Pay** (solo en Safari/iOS)
- **Google Pay** (solo en Chrome/Android)

✅ **Transferencia Bancaria**
- Genera referencia de pago en checkout
- Válida por 24 horas
- Pedido se procesa al confirmar pago (1-2 horas)

**Datos para Transferencia:**
- Banco: BBVA Bancomer
- Cuenta: 0123456789
- CLABE: 012180001234567890
- Beneficiario: Tu Tienda SA de CV

✅ **Pago en OXXO** 🏪
- Genera código de barras en checkout
- Paga en cualquier OXXO
- Válido por 48 horas
- Pedido se procesa al confirmar pago (1-2 horas)

✅ **Pago Contra Entrega** 📦
- Disponible solo en CDMX y Área Metropolitana
- Solo efectivo (monto exacto)
- Cargo adicional: $50 MXN
- No disponible para pedidos >$5,000 MXN

🔒 **Seguridad de Pagos**
- Certificado SSL 256-bit
- PCI DSS Compliant
- Tokenización de tarjetas
- No almacenamos datos completos de tarjetas

❓ **¿Es Seguro Comprar Aquí?**
**¡100% Seguro!** Utilizamos la misma tecnología de bancos online.
Tu información está protegida y encriptada.

💡 **¿Problemas con tu Pago?**
Contacta a tu banco o prueba con:
1. Otro método de pago
2. Navegador diferente (modo incógnito)
3. Nuestro equipo de soporte: pagos@tutienda.com
"""
    }
    
    # ───────────────────────────────────────────────────────────
    # PRODUCT INFORMATION
    # ───────────────────────────────────────────────────────────
    
    PRODUCT_MATERIAL = {
        "general": """
**🧵 Materiales de Nuestros Productos**

Cada producto especifica su composición exacta en la ficha de producto.

✅ **Materiales Comunes**
- **Algodón**: Natural, respirable, fácil cuidado
- **Poliéster**: Duradero, resistente a arrugas, secado rápido
- **Mezclas**: Combina beneficios (ej: 60% algodón, 40% poliéster)
- **Seda**: Premium, suave, elegante (cuidado delicado)
- **Lino**: Natural, fresco, ideal verano
- **Spandex/Elastano**: Elasticidad y ajuste (típicamente 2-5% en mezclas)

💡 **¿Cómo Saber el Material Exacto?**
1. Ve a la página del producto
2. Desplázate a "Detalles del Producto"
3. Busca "Composición" o "Material"

📋 **Certificaciones de Calidad**
- OEKO-TEX® Standard 100 (libre de sustancias nocivas)
- Global Organic Textile Standard (GOTS) para algodón orgánico
- Responsible Wool Standard (RWS) para lana

❓ **¿Tienes Alergias?**
Contáctanos antes de comprar para confirmar materiales hipoalergénicos.
""",
        
        "VESTIDOS": """
**👗 Materiales de Vestidos**

Nuestros vestidos están confeccionados con materiales premium según el diseño:

✅ **Vestidos Casuales**
- 95% Algodón, 5% Spandex (comodidad y movimiento)
- 100% Algodón orgánico (línea eco-friendly)
- Jersey de algodón (suave, elástico)

✅ **Vestidos de Noche/Gala**
- Satén de seda (brillo elegante, caída perfecta)
- Gasa/Chiffon (ligero, vaporoso, romántico)
- Terciopelo (lujo, textura rica)
- Tul (capas voluminosas, estructura)

✅ **Vestidos de Oficina**
- Mezclas de algodón-poliéster (no arrugas, profesional)
- Crepe (textura elegante, no requiere plancha)

✅ **Vestidos de Verano**
- Lino 100% (fresco, respirable)
- Rayón (suave, fluido, económico)
- Algodón voile (ligero, perfecto para calor)

💡 **Tip de Compra**
- ¿Evento formal? → Seda o satén
- ¿Uso diario? → Algodón con spandex
- ¿Clima cálido? → Lino o algodón voile

🧼 **Cuidados Especiales**
Cada vestido incluye etiqueta con instrucciones de lavado específicas.
Vestidos de seda/satén generalmente requieren lavado en seco.
""",
        
        "ZAPATOS": """
**👞 Materiales de Calzado**

✅ **Materiales Exteriores**
- **Cuero Genuino**: Duradero, respirable, se adapta al pie con el tiempo
- **Cuero Sintético (PU)**: Similar apariencia, más económico, fácil limpieza
- **Textiles/Mesh**: Ligeros, respirables, ideales deportivos
- **Gamuza (Suede)**: Elegante, textura suave, requiere cuidado especial

✅ **Materiales de Suela**
- **Goma/Caucho**: Antideslizante, durable, flexible
- **EVA**: Ligero, amortiguación excelente (tenis/deportivos)
- **Cuero**: Clásico, elegante (zapatos formales)
- **TPU**: Alta resistencia, soporte estructural

✅ **Plantillas/Forros**
- **Cuero**: Respirable, absorbe humedad
- **Memory Foam**: Máxima comodidad, se adapta al pie
- **Textil**: Suave, económico, fácil limpieza

💡 **¿Cuero Real vs Sintético?**
**Cuero Real:**
- Más caro, más duradero
- Requiere mantenimiento (cremas, betún)
- Mejora con el tiempo

**Cuero Sintético:**
- Más económico
- Fácil limpieza (paño húmedo)
- No requiere mantenimiento especial

🌱 **Opciones Veganas**
Filtra por "Vegano" en categoría zapatos para opciones sin materiales animales.

🧼 **Cuidado del Calzado**
Ver nuestra [Guía de Cuidado →](/help/shoe-care) según tipo de material.
"""
    }
    
    PRODUCT_SIZE = {
        "general": """
**📏 Guías de Tallas**

Consulta nuestra guía interactiva de tallas por categoría:

✅ **Vestidos y Ropa**
[Guía de Tallas Vestimenta →](/help/clothing-sizing)
- Tabla de medidas por talla
- Cómo tomar tus medidas correctamente
- Videos tutorial

✅ **Calzado**
[Guía de Tallas Zapatos →](/help/shoe-sizing)
- Conversión MX/US/EUR
- Cómo medir tu pie en casa
- Tabla por marca (algunas corren diferentes)

💡 **¿Entre Tallas?**
**Regla general:**
- Ropa ajustada (vestidos, blusas) → Talla mayor
- Ropa holgada (oversized) → Tu talla normal o menor
- Zapatos → Talla mayor (especialmente tacones)

📞 **Asesoría Personalizada**
Chatea con nosotros enviando tus medidas, te ayudamos a elegir:
- WhatsApp: +52 55 1234 5678
- Chat en vivo: [Iniciar →](/help/chat)

✅ **Cambio Gratis por Talla**
Si no te queda, cambio sin costo dentro de 15 días.
""",
        
        "VESTIDOS": """
**👗 Guía de Tallas - Vestidos**

| Talla | Busto (cm) | Cintura (cm) | Cadera (cm) | Largo* |
|-------|-----------|--------------|-------------|---------|
| **XS** | 78-82 | 60-64 | 86-90 | Según modelo |
| **S** | 82-86 | 64-68 | 90-94 | Según modelo |
| **M** | 86-92 | 68-74 | 94-100 | Según modelo |
| **L** | 92-98 | 74-80 | 100-106 | Según modelo |
| **XL** | 98-104 | 80-86 | 106-112 | Según modelo |
| **2XL** | 104-112 | 86-94 | 112-120 | Según modelo |

*Largo varía según si es vestido corto, midi o largo. Ver ficha de cada producto.

✅ **Cómo Medir Correctamente**

**Busto:**
Rodea la parte más amplia del busto, manteniendo cinta horizontal y ajustada sin apretar.

**Cintura:**
Mide en la parte más estrecha del torso, generalmente 2-3 cm arriba del ombligo.

**Cadera:**
Rodea la parte más amplia de las caderas, manteniendo cinta horizontal.

💡 **Tips Importantes**
- Mide sobre ropa interior, no sobre ropa gruesa
- No aprietes la cinta, debe estar ajustada pero cómoda
- Pide ayuda (es difícil medirse solo correctamente)
- Si estás entre tallas, considera el fit del vestido:
  - Vestido ajustado/bodycon → Talla mayor
  - Vestido tipo A/holgado → Tu talla normal

📐 **Calculadora de Tallas**
Ingresa tus medidas y te recomendamos la talla:
[Calcular Mi Talla →](/tools/size-calculator)

❓ **¿Qué Talla Soy en Otras Tiendas?**
Nuestras tallas son estándar mexicanas, pero pueden variar según marca:
- Zara: Generalmente 1 talla menor
- H&M: Equivalente
- Shein: 1-2 tallas mayores
""",
        
        "ZAPATOS": """
**👟 Guía de Tallas - Calzado**

| Talla MX | Talla US (Mujer) | Talla EUR | CM (Largo Pie) |
|----------|------------------|-----------|----------------|
| **22** | 5 | 35 | 22.0 |
| **22.5** | 5.5 | 35.5 | 22.5 |
| **23** | 6 | 36 | 23.0 |
| **23.5** | 6.5 | 36.5 | 23.5 |
| **24** | 7 | 37 | 24.0 |
| **24.5** | 7.5 | 37.5 | 24.5 |
| **25** | 8 | 38 | 25.0 |
| **25.5** | 8.5 | 38.5 | 25.5 |
| **26** | 9 | 39 | 26.0 |
| **26.5** | 9.5 | 39.5 | 26.5 |
| **27** | 10 | 40 | 27.0 |
| **27.5** | 10.5 | 40.5 | 27.5 |
| **28** | 11 | 41 | 28.0 |

✅ **Cómo Medir tu Pie**

1. **Prepara:** Hoja blanca, lápiz, regla
2. **Párate** sobre la hoja (con calcetín si usarás zapato con calcetín)
3. **Marca** el punto más largo del talón y del dedo más largo
4. **Mide** la distancia en centímetros
5. **Repite** con el otro pie (pueden ser diferentes)
6. **Usa** la medida del pie MÁS GRANDE

📹 **Video Tutorial**
[Ver Cómo Medir Tu Pie →](/help/shoe-measure-video)

💡 **Consejos Importantes**
- **Pie ancho?** → Considera media talla más o busca modelos "Wide Fit"
- **Tacones altos?** → Media talla más (el pie se desliza hacia adelante)
- **Botas?** → Considera el grosor del calcetín/media
- **Mide por la tarde** → El pie se hincha ligeramente durante el día

⚠️ **Zapatos que Corren Diferentes**
Algunas marcas/modelos tienen ajuste diferente:
- Converse: Tienden a correr grande (media talla menos)
- Nike: Generalmente fiel a talla
- Steve Madden: Tiende a correr pequeño (media talla más)

Ver "Opiniones" en cada producto para leer experiencias de otros compradores.

✅ **Cambio Gratis por Talla**
Si no te quedan, ¡cambio sin costo! Solo asegúrate de no usarlos en exteriores.
"""
    }
    
    PRODUCT_CARE = {
        "general": """
**🧼 Cuidado de Productos**

Cada producto incluye etiqueta con instrucciones específicas de cuidado.

✅ **Símbolos Comunes de Cuidado**

**Lavado:**
- 🛁 30°C = Lavar en agua fría (máximo 30°C)
- 🛁 40°C = Lavar en agua tibia
- 🚫 🛁 = No lavar en máquina (lavado a mano o en seco)

**Secado:**
- ☀️ = Secar al aire libre
- 🌡️• = Secadora temperatura baja
- 🚫 🌡️ = No usar secadora

**Planchado:**
- 🔥• = Planchar temperatura baja (110°C)
- 🔥•• = Planchar temperatura media (150°C)
- 🔥••• = Planchar temperatura alta (200°C)

**Limpieza en Seco:**
- ⭕ A = Limpieza en seco profesional (cualquier solvente)
- 🚫 ⭕ = No limpiar en seco

📋 **Guías Específicas**
- [Cuidado de Vestidos →](/help/dress-care)
- [Cuidado de Calzado →](/help/shoe-care)
- [Cuidado de Accesorios →](/help/accessories-care)

💡 **Consejos Generales**
- Lee etiquetas ANTES del primer lavado
- Separa colores oscuros de claros
- Cierra cierres antes de lavar
- Dale vuelta a prendas con estampados
- No sobrecargues la lavadora
""",
        
        "VESTIDOS": """
**👗 Cuidado de Vestidos**

✅ **Vestidos de Algodón**
- **Lavado**: Máquina, agua fría (30°C)
- **Secado**: Tender o secadora temperatura baja
- **Planchado**: Temperatura media mientras húmedo
- **Tip**: Dale vuelta para proteger color

✅ **Vestidos de Seda/Satén**
- **Lavado**: Lavado a mano con detergente suave o limpieza en seco
- **Secado**: Tender en horizontal (no colgar húmedo)
- **Planchado**: Temperatura baja, del revés, con paño protector
- **Tip**: NUNCA exprimir, enrollar en toalla para absorber agua

✅ **Vestidos de Gala/Noche**
- **Lavado**: Limpieza en seco profesional **SIEMPRE**
- **Almacenamiento**: Funda respirable, colgado (no doblado)
- **Antes de usar**: Colgar en baño con vapor para eliminar arrugas
- **Manchas**: Llevar inmediatamente a tintorería (no intentar quitar)

✅ **Vestidos con Lentejuelas/Pedrería**
- **Lavado**: Mano, agua fría, del revés
- **Secado**: Tender horizontal
- **Planchado**: NO planchar (usa vaporizador)
- **Almacenamiento**: Bolsa de tela (no plástico)

🚨 **Manchas Comunes**

**Maquillaje:**
1. Espolvorea talco/maicena inmediatamente
2. Deja absorber 30 min
3. Cepilla suavemente
4. Lava según instrucciones

**Vino/Bebidas:**
1. Absorbe con paño (no frotes)
2. Agua con gas (no agua normal)
3. Sal o bicarbonato
4. Lava lo antes posible

**Sudor:**
1. Enjuaga con agua fría inmediatamente
2. Vinagre blanco diluido (1:4)
3. Deja actuar 15 min
4. Lava normal

💡 **Almacenamiento a Largo Plazo**
- Limpia ANTES de guardar (manchas invisibles se fijan con tiempo)
- Usa fundas de algodón respirable
- Guarda en lugar fresco, seco, oscuro
- Evita perchas metálicas (usan perchas acolchadas)
"""
    }


# ═══════════════════════════════════════════════════════════════
# KNOWLEDGE BASE CLASS
# ═══════════════════════════════════════════════════════════════

class SimpleKnowledgeBase:
    """
    Simple hardcoded knowledge base.
    Retrieves answers based on sub-intent and optional product context.
    """
    
    def __init__(self):
        """Initialize knowledge base."""
        self.content = KnowledgeBaseContent()
        
        # Metrics
        self.metrics = {
            "total_queries": 0,
            "successful_answers": 0,
            "fallback_to_general": 0,
            "no_answer_found": 0
        }
        
        logger.info("✅ SimpleKnowledgeBase initialized")
    
    def get_answer(
        self,
        sub_intent: InformationalSubIntent,
        product_context: Optional[List[str]] = None,
        query: Optional[str] = None
    ) -> Optional[KnowledgeBaseAnswer]:
        """
        Get answer for informational query.
        
        Args:
            sub_intent: Type of information requested
            product_context: Product categories mentioned (e.g., ["ZAPATOS"])
            query: Original query (for future semantic search)
        
        Returns:
            KnowledgeBaseAnswer or None if not found
        """
        self.metrics["total_queries"] += 1
        
        logger.info(f"Knowledge base query: {sub_intent}, context: {product_context}")
        
        # ═══════════════════════════════════════════════════════
        # ROUTE TO APPROPRIATE CONTENT
        # ═══════════════════════════════════════════════════════
        
        answer_text = None
        sources = []
        
        # Return Policy
        if sub_intent == InformationalSubIntent.POLICY_RETURN:
            answer_text = self._get_contextual_answer(
                self.content.RETURN_POLICY,
                product_context
            )
            sources = ["policies/returns.md"]
        
        # Shipping Policy
        elif sub_intent == InformationalSubIntent.POLICY_SHIPPING:
            # Check if query is about cost or time specifically
            if query:
                query_lower = query.lower()
                if "costo" in query_lower or "cuánto cuesta" in query_lower or "precio" in query_lower:
                    answer_text = self.content.SHIPPING_POLICY.get("cost")
                    sources = ["policies/shipping_cost.md"]
                elif "cuánto tarda" in query_lower or "tiempo" in query_lower or "cuándo" in query_lower:
                    answer_text = self.content.SHIPPING_POLICY.get("time")
                    sources = ["policies/shipping_time.md"]
            
            # Default to general shipping
            if not answer_text:
                answer_text = self.content.SHIPPING_POLICY.get("general")
                sources = ["policies/shipping.md"]
        
        # Payment Policy
        elif sub_intent == InformationalSubIntent.POLICY_PAYMENT:
            answer_text = self.content.PAYMENT_POLICY.get("general")
            sources = ["policies/payment.md"]
        
        # Product Material
        elif sub_intent == InformationalSubIntent.PRODUCT_MATERIAL:
            answer_text = self._get_contextual_answer(
                self.content.PRODUCT_MATERIAL,
                product_context
            )
            sources = ["product_info/materials.md"]
        
        # Product Size
        elif sub_intent == InformationalSubIntent.PRODUCT_SIZE:
            answer_text = self._get_contextual_answer(
                self.content.PRODUCT_SIZE,
                product_context
            )
            sources = ["product_info/sizing.md"]
        
        # Product Care
        elif sub_intent == InformationalSubIntent.PRODUCT_CARE:
            answer_text = self._get_contextual_answer(
                self.content.PRODUCT_CARE,
                product_context
            )
            sources = ["product_info/care.md"]
        
        # General FAQ or Unknown
        else:
            logger.warning(f"No specific answer for sub_intent: {sub_intent}")
            answer_text = self._get_general_help_message()
            sources = ["general/faq.md"]
            self.metrics["no_answer_found"] += 1
        
        # ═══════════════════════════════════════════════════════
        # RETURN RESULT
        # ═══════════════════════════════════════════════════════
        
        if answer_text:
            self.metrics["successful_answers"] += 1
            
            return KnowledgeBaseAnswer(
                answer=answer_text,
                sub_intent=sub_intent,
                sources=sources,
                related_links=self._get_related_links(sub_intent)
            )
        
        return None
    
    def _get_contextual_answer(
        self,
        content_dict: Dict[str, str],
        product_context: Optional[List[str]]
    ) -> str:
        """
        Get contextual answer based on product category.
        
        Priority:
        1. Specific category (e.g., "ZAPATOS")
        2. General answer
        """
        # Try specific category first
        if product_context:
            for category in product_context:
                if category in content_dict:
                    logger.debug(f"Using specific answer for category: {category}")
                    return content_dict[category]
                
                # Try parent category (e.g., "VESTIDOS" for "VESTIDOS LARGOS")
                parent_category = category.split()[0]  # Get first word
                if parent_category in content_dict:
                    logger.debug(f"Using parent category answer: {parent_category}")
                    self.metrics["fallback_to_general"] += 1
                    return content_dict[parent_category]
        
        # Fallback to general
        logger.debug("Using general answer")
        self.metrics["fallback_to_general"] += 1
        return content_dict.get("general", "")
    
    def _get_general_help_message(self) -> str:
        """Default help message when no specific answer found."""
        return """
**🤔 No encontramos información específica para tu pregunta**

Pero podemos ayudarte:

📞 **Contacta a Nuestro Equipo**
- **WhatsApp**: +52 55 1234 5678 (L-V 9am-7pm)
- **Email**: ayuda@tutienda.com
- **Chat en Vivo**: [Iniciar Chat →](/help/chat)
- **Tiempo de respuesta**: < 2 horas en días hábiles

📚 **Recursos Útiles**
- [Centro de Ayuda Completo →](/help)
- [Preguntas Frecuentes →](/help/faq)
- [Políticas de la Tienda →](/policies)
- [Guías de Tallas →](/help/sizing)

💡 **También puedes preguntarme sobre:**
- Política de devoluciones
- Información de envío
- Métodos de pago
- Cuidado de productos
- Guías de tallas
"""
    
    def _get_related_links(self, sub_intent: InformationalSubIntent) -> List[Dict[str, str]]:
        """Get related helpful links based on sub-intent."""
        
        links = []
        
        if sub_intent == InformationalSubIntent.POLICY_RETURN:
            links = [
                {"title": "Iniciar Devolución", "url": "/account/returns"},
                {"title": "Guía de Tallas", "url": "/help/sizing"},
                {"title": "Contacto", "url": "/help/contact"}
            ]
        
        elif sub_intent == InformationalSubIntent.POLICY_SHIPPING:
            links = [
                {"title": "Rastrear Pedido", "url": "/account/orders"},
                {"title": "Cambiar Dirección", "url": "/account/addresses"},
                {"title": "Preguntas Frecuentes", "url": "/help/faq"}
            ]
        
        elif sub_intent == InformationalSubIntent.POLICY_PAYMENT:
            links = [
                {"title": "Métodos de Pago", "url": "/help/payment-methods"},
                {"title": "Seguridad", "url": "/help/security"},
                {"title": "Facturación", "url": "/help/invoicing"}
            ]
        
        elif sub_intent == InformationalSubIntent.PRODUCT_SIZE:
            links = [
                {"title": "Calculadora de Tallas", "url": "/tools/size-calculator"},
                {"title": "Video Tutorial", "url": "/help/measure-tutorial"},
                {"title": "Cambio por Talla", "url": "/help/size-exchange"}
            ]
        
        return links
    
    def get_metrics(self) -> Dict:
        """Get knowledge base metrics."""
        total = self.metrics["total_queries"]
        return {
            **self.metrics,
            "success_rate": (
                self.metrics["successful_answers"] / total
                if total > 0 else 0.0
            ),
            "fallback_rate": (
                self.metrics["fallback_to_general"] / total
                if total > 0 else 0.0
            )
        }


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

# Singleton instance
_knowledge_base_instance: Optional[SimpleKnowledgeBase] = None


def get_knowledge_base() -> SimpleKnowledgeBase:
    """
    Get singleton instance of knowledge base.
    Lazy initialization.
    """
    global _knowledge_base_instance
    if _knowledge_base_instance is None:
        _knowledge_base_instance = SimpleKnowledgeBase()
    return _knowledge_base_instance


def get_answer(
    sub_intent: InformationalSubIntent,
    product_context: Optional[List[str]] = None,
    query: Optional[str] = None
) -> Optional[KnowledgeBaseAnswer]:
    """
    Public API for knowledge base queries.
    
    Args:
        sub_intent: Type of information requested
        product_context: Product categories mentioned
        query: Original user query
    
    Returns:
        KnowledgeBaseAnswer or None
    
    Example:
        >>> answer = get_answer(
        ...     sub_intent=InformationalSubIntent.POLICY_RETURN,
        ...     product_context=["ZAPATOS"]
        ... )
        >>> print(answer.answer)
        # Returns shoe-specific return policy
    """
    kb = get_knowledge_base()
    return kb.get_answer(sub_intent, product_context, query)