# =============================================================================
# test_load.py — Prueba de carga concurrente para shared-services-classifier
# Ejecutar en VS Code: python test_load.py
# Requiere: pip install httpx
# =============================================================================

import asyncio
import httpx
import json
import time
from datetime import datetime

# ── Configuración ─────────────────────────────────────────────────────────────
AGENT_URL      = "http://localhost:8001/process"
PROVIDER       = "ollama"       # ollama | openai | anthropic | gemini
CONCURRENCY    = 5              # N requests simultáneos
MESSAGES_PER_CATEGORY = 2      # Mensajes por categoría (2 × ~34 cats = ~68 total)
TIMEOUT        = 300.0          # segundos por request (ollama es lento)

# ── Mensajes por categoría ────────────────────────────────────────────────────
MESSAGES = {
    # ── IT ────────────────────────────────────────────────────────────────────
    "IT.hardware": [
        "Mi computadora no enciende desde esta mañana, necesito soporte urgente.",
        "La pantalla de mi laptop tiene líneas y no se ve bien, requiero revisión.",
        "El teclado dejó de funcionar después de derramar café, necesito reemplazo.",
        "El mouse inalámbrico no conecta aunque cambié las baterías.",
        "La impresora no jalona el papel y marca error de hardware.",
        "Mi disco duro hace ruidos extraños y el equipo va muy lento.",
        "El ventilador de la computadora hace mucho ruido y se calienta.",
        "Necesito ampliar la memoria RAM de mi equipo para trabajar con el ERP.",
        "El monitor no enciende aunque el CPU sí está funcionando.",
        "Requiero cambio de batería en mi laptop, ya no dura ni una hora.",
    ],
    "IT.software": [
        "El sistema SAP no abre y me marca error de licencia vencida.",
        "Excel se cierra solo cuando intento abrir archivos con macros.",
        "Necesito instalar el software de diseño para el nuevo proyecto.",
        "El antivirus está bloqueando el acceso al sistema de nómina.",
        "La aplicación de ventas no sincroniza con el servidor central.",
        "Requiero actualización de Office, tengo una versión muy antigua.",
        "El sistema de facturación no imprime correctamente las pólizas.",
        "El programa de contabilidad arroja error al cerrar el mes.",
        "Necesito permisos de administrador para instalar una herramienta.",
        "El software de videoconferencia no detecta la cámara ni el micrófono.",
    ],
    "IT.red": [
        "No tengo acceso a internet desde mi puesto de trabajo desde ayer.",
        "La conexión WiFi se cae constantemente en el área de ventas.",
        "El servidor de archivos compartidos no es accesible desde la VPN.",
        "La red está muy lenta, las descargas tardan horas.",
        "No puedo conectarme a la impresora de red del piso 3.",
        "Hay intermitencia en la conexión de toda el área de finanzas.",
        "Necesito configurar la red para el nuevo equipo que llegó hoy.",
        "El switch del rack principal está parpadeando en rojo.",
        "No puedo acceder a las carpetas compartidas del servidor.",
        "La conexión entre la sucursal y la matriz está caída.",
    ],
    "IT.acceso": [
        "Olvidé mi contraseña del sistema y no puedo entrar al correo.",
        "Mi usuario está bloqueado después de varios intentos fallidos.",
        "Necesito acceso al módulo de reportes de SAP para mi nuevo rol.",
        "El nuevo colaborador requiere alta de usuario en todos los sistemas.",
        "Mi acceso al portal de proveedores fue revocado por error.",
        "Necesito permisos de lectura en la carpeta de proyectos 2026.",
        "Al colaborador que se fue hay que darle de baja en todos los sistemas.",
        "Requiero acceso al sistema de RRHH para consultar mis vacaciones.",
        "Mi contraseña expiró y el enlace de recuperación no llega al correo.",
        "Necesito habilitar el segundo factor de autenticación en mi cuenta.",
    ],
    "IT.correo": [
        "Mi buzón de correo está lleno y no puedo recibir mensajes nuevos.",
        "No puedo enviar archivos adjuntos mayores a 5MB por correo.",
        "Necesito crear una lista de distribución para el equipo de ventas.",
        "Los correos que envío llegan a spam en el destinatario.",
        "Mi firma corporativa desapareció después de la actualización.",
        "Necesito acceso al correo del colaborador que salió de vacaciones.",
        "Los correos de un proveedor están siendo bloqueados como spam.",
        "Requiero configurar el correo en mi teléfono celular nuevo.",
        "No recibo las notificaciones automáticas del sistema de tickets.",
        "El calendario compartido del equipo no se sincroniza correctamente.",
    ],
    "IT.impresora": [
        "La impresora del área de contabilidad no imprime desde ayer.",
        "El cartucho de la impresora está vacío, necesito reposición.",
        "La impresora marca error de papel atascado pero no hay papel.",
        "Necesito instalar la impresora nueva que llegó hoy al área.",
        "La impresora imprime con manchas negras en todas las hojas.",
        "No puedo imprimir en doble cara desde mi computadora.",
        "La impresora de recepción no conecta a la red.",
        "Necesito configurar la impresora para que imprima en tamaño carta.",
        "El escáner de la impresora multifuncional no funciona.",
        "La impresora tarda mucho en imprimir documentos PDF.",
    ],
    "IT.vpn": [
        "No puedo conectarme a la VPN desde casa, marca error de autenticación.",
        "La VPN conecta pero no puedo acceder a los sistemas internos.",
        "El cliente VPN no instala en mi laptop con Windows 11.",
        "La VPN se desconecta sola cada 30 minutos.",
        "Necesito configurar VPN para el nuevo colaborador en home office.",
        "La VPN va muy lenta y no puedo trabajar con el ERP desde casa.",
        "El certificado de la VPN expiró y no puedo conectarme.",
        "Necesito VPN para acceder al sistema desde el viaje de negocios.",
        "La VPN bloquea el acceso a algunas páginas de trabajo.",
        "Error 619 al conectar VPN, ya reinstalé el cliente y sigue igual.",
    ],
    "IT.servidor": [
        "El servidor de producción no responde desde las 9am.",
        "El servidor de archivos está al 95% de capacidad.",
        "El servidor web está caído y la tienda en línea no está disponible.",
        "Necesito reiniciar el servicio de base de datos en el servidor.",
        "El servidor de respaldos no completó el proceso de anoche.",
        "El servidor de aplicaciones está generando errores 500.",
        "Necesito aumentar la memoria del servidor de reportes.",
        "El servidor de correo está rechazando conexiones entrantes.",
        "El servidor de desarrollo necesita actualización del sistema operativo.",
        "Los logs del servidor muestran intentos de acceso no autorizado.",
    ],
    "IT.base_de_datos": [
        "La base de datos de SAP está respondiendo muy lento.",
        "Necesito restaurar un registro que fue eliminado por error.",
        "La consulta del reporte mensual tarda 2 horas en ejecutarse.",
        "La base de datos de producción arrojó error de espacio en disco.",
        "Necesito un respaldo de la base de datos antes de la migración.",
        "Hay registros duplicados en la tabla de clientes.",
        "La conexión a la base de datos desde la aplicación falla intermitente.",
        "Necesito crear un usuario de solo lectura para el área de auditoría.",
        "El índice de la tabla de transacciones está fragmentado.",
        "Necesito exportar datos históricos de los últimos 5 años.",
    ],
    "IT.seguridad": [
        "Recibí un correo sospechoso con enlace extraño, creo que es phishing.",
        "Alguien accedió a mi cuenta desde una ubicación desconocida.",
        "Encontré un USB en el estacionamiento y lo conecté sin querer.",
        "Mi equipo está mostrando anuncios extraños, creo que tiene virus.",
        "Recibí una llamada pidiendo mis credenciales del sistema.",
        "Hay un intento de ransomware en el servidor de archivos.",
        "Necesito revisar los permisos de acceso del área de finanzas.",
        "El sistema detectó un acceso fuera de horario a la base de datos.",
        "Necesito deshabilitar el acceso inmediato de un colaborador despedido.",
        "El firewall está bloqueando una aplicación legítima de trabajo.",
    ],

    # ── CLIENTE ───────────────────────────────────────────────────────────────
    "cliente.facturacion": [
        "Mi factura del mes anterior tiene un error en el monto cobrado.",
        "No he recibido la factura del servicio contratado hace 15 días.",
        "Necesito factura con datos fiscales diferentes a los registrados.",
        "Me cobraron dos veces el mismo servicio en la misma factura.",
        "Requiero copia de factura de los últimos 3 meses para auditoría.",
        "La factura electrónica no llega a mi correo registrado.",
        "El RFC en mi factura está incorrecto, necesito corrección.",
        "Necesito factura global por todos los consumos del mes.",
        "Me aplicaron IVA cuando estoy exento, requiero nota de crédito.",
        "La fecha de la factura no corresponde al periodo del servicio.",
    ],
    "cliente.reclamo": [
        "El producto llegó dañado y no corresponde a lo que ordené.",
        "El servicio no fue entregado en la fecha prometida.",
        "El técnico que enviaron no resolvió el problema y cobró de más.",
        "Me prometieron un descuento que no aplicaron en mi factura.",
        "El servicio tiene fallas recurrentes que no han sido resueltas.",
        "Mi queja anterior no fue atendida en el plazo prometido.",
        "El producto no funciona como se describió en la oferta.",
        "Me enviaron el artículo equivocado y no han gestionado el cambio.",
        "El cobro en mi tarjeta no corresponde al precio acordado.",
        "El personal de atención me trató de forma inapropiada.",
    ],
    "cliente.consulta": [
        "¿Cuáles son los horarios de atención al cliente?",
        "¿Cuánto tiempo tarda en llegar mi pedido a Monterrey?",
        "¿Qué documentos necesito para contratar el servicio premium?",
        "¿Tienen sucursal en Guadalajara o solo en CDMX?",
        "¿Puedo cambiar la dirección de entrega después de confirmar el pedido?",
        "¿Cuál es el proceso para renovar mi contrato de servicio?",
        "¿Aceptan pagos en parcialidades sin intereses?",
        "¿Cómo puedo consultar el saldo de mi cuenta de servicio?",
        "¿Qué incluye el plan básico vs el plan empresarial?",
        "¿Puedo transferir mi contrato a otra empresa?",
    ],
    "cliente.devolucion": [
        "Quiero devolver el producto, llegó con defecto de fábrica.",
        "El artículo no es lo que necesitaba, ¿puedo devolverlo?",
        "Solicito reembolso del pago, el servicio no fue prestado.",
        "El equipo rentado presenta fallas, solicito sustitución o devolución.",
        "Compré el artículo equivocado y no lo he abierto aún.",
        "El producto tiene garantía vigente y dejó de funcionar.",
        "Necesito cancelar el pedido antes de que sea enviado.",
        "El servicio no cumplió lo acordado, solicito devolución parcial.",
        "Devuelvo el equipo al terminar el contrato de arrendamiento.",
        "El producto vino incompleto, faltan accesorios incluidos.",
    ],
    "cliente.garantia": [
        "Mi equipo falló dentro del periodo de garantía de 1 año.",
        "¿Qué cubre exactamente la garantía del producto que compré?",
        "Necesito hacer válida la garantía por falla de pantalla.",
        "El servicio de garantía tardó más de lo prometido.",
        "Perdí la póliza de garantía, ¿pueden reexpedirla?",
        "¿La garantía cubre daños por voltaje si tenía regulador?",
        "El proveedor dice que la falla no aplica a garantía, no estoy de acuerdo.",
        "¿Puedo extender la garantía del equipo por 2 años adicionales?",
        "El equipo reparado bajo garantía volvió a fallar al mes.",
        "Necesito constancia de que el equipo está en garantía para seguros.",
    ],
    "cliente.soporte": [
        "Necesito asistencia para configurar el equipo que acabo de recibir.",
        "El sistema no funciona correctamente, requiero soporte técnico.",
        "¿Tienen soporte disponible los fines de semana?",
        "Necesito un técnico en sitio para revisar la instalación.",
        "El manual no explica cómo configurar la función avanzada.",
        "Requiero capacitación para el nuevo personal en el uso del sistema.",
        "El soporte remoto no pudo resolver el problema, necesito visita.",
        "¿Cuánto tiempo es el tiempo de respuesta de soporte prioritario?",
        "Necesito soporte en inglés para mi equipo en EUA.",
        "El número de soporte no contesta, ¿hay otro canal de atención?",
    ],
    "cliente.pedido": [
        "¿Cuál es el estatus de mi pedido número 45821?",
        "Mi pedido lleva 10 días y aún no ha salido del almacén.",
        "Necesito modificar la cantidad de mi pedido antes del envío.",
        "El pedido llegó incompleto, faltan 3 artículos del total.",
        "¿Puedo agregar un artículo a mi pedido ya confirmado?",
        "Necesito que mi pedido llegue antes del viernes para el evento.",
        "El número de seguimiento no aparece en el sistema del courier.",
        "Quiero cancelar el pedido, cambié de proveedor.",
        "El pedido fue entregado en dirección incorrecta.",
        "Necesito confirmación de recibo para pagar la factura.",
    ],
    "cliente.envio": [
        "El paquete lleva 5 días en tránsito sin movimiento en el rastreo.",
        "Necesito envío express para mañana, ¿es posible?",
        "El courier intentó entregar y no había nadie, ¿cómo reagendo?",
        "¿Tienen envío a zonas rurales en Oaxaca?",
        "El empaque llegó golpeado aunque el producto está bien.",
        "Necesito cambiar la dirección de entrega antes del envío.",
        "¿Cuánto cuesta el envío a Mérida para una caja de 20kg?",
        "El número de guía no reconoce el sistema del courier.",
        "¿Puedo recoger mi pedido en almacén para evitar el costo de envío?",
        "El paquete figura como entregado pero no lo recibí.",
    ],

    # ── OPERACIONES ───────────────────────────────────────────────────────────
    "operaciones.logistica": [
        "Necesito coordinar el traslado de equipos entre sucursales.",
        "El camión de distribución no llegó a tiempo a la planta.",
        "Hay retraso en la cadena de suministro por el proveedor de Asia.",
        "Necesito planificar la ruta óptima para las entregas de esta semana.",
        "El almacén de tránsito está saturado, necesitamos redistribuir.",
        "La mercancía llegó sin los documentos de transporte requeridos.",
        "Necesito coordinar el retorno de embalajes al proveedor.",
        "El operador de montacargas no se presentó, hay carga urgente.",
        "Requiero trazabilidad de los embarques del mes de enero.",
        "La temperatura del contenedor frigorífico estuvo fuera de rango.",
    ],
    "operaciones.compras": [
        "Necesito generar una orden de compra para insumos urgentes.",
        "El proveedor cambió los precios sin previo aviso.",
        "Requiero cotización de al menos 3 proveedores para la licitación.",
        "La orden de compra 4521 lleva 3 semanas sin ser surtida.",
        "Necesito aprobación del comité para compra mayor a $500,000.",
        "El proveedor actual no puede surtir el volumen que necesitamos.",
        "Necesito buscar proveedor alternativo para materia prima.",
        "La compra de emergencia requiere omitir el proceso de licitación.",
        "El contrato con el proveedor de servicios vence este mes.",
        "Requiero alta de nuevo proveedor en el sistema de compras.",
    ],
    "operaciones.inventario": [
        "El conteo físico no cuadra con el sistema, hay diferencia de 50 piezas.",
        "El inventario de seguridad de componente A está por agotarse.",
        "Necesito ajuste de inventario por merma registrada en auditoría.",
        "El almacén no tiene espacio para el nuevo lote que llega mañana.",
        "Hay productos caducados en el almacén que requieren baja del sistema.",
        "El código de barras del producto no está en el catálogo.",
        "Necesito inventario cíclico del área de materia prima esta semana.",
        "El sistema muestra stock negativo en el artículo 7821.",
        "Requiero política de inventario mínimo para los 20 artículos críticos.",
        "El traslado entre almacenes no se reflejó en el sistema.",
    ],
    "operaciones.mantenimiento": [
        "La máquina de producción línea 3 requiere mantenimiento preventivo.",
        "El compresor principal tiene fuga de aceite, requiere atención urgente.",
        "Necesito programar mantenimiento anual de toda la flota vehicular.",
        "El aire acondicionado del área de servidores está fallando.",
        "La banda transportadora se detuvo por desgaste excesivo.",
        "Requiero mantenimiento correctivo urgente en la prensa hidráulica.",
        "El sistema eléctrico del almacén presenta fallas intermitentes.",
        "Necesito informe del historial de mantenimiento de los equipos.",
        "El generador de emergencia no arrancó en la última prueba.",
        "La caldera requiere revisión de válvulas de seguridad.",
    ],
    "operaciones.produccion": [
        "La línea de producción se detuvo por falta de materia prima.",
        "Necesito reprogramar la producción de la semana por cambio de pedido.",
        "La eficiencia de la línea 2 bajó al 65%, requiere análisis.",
        "Hay defectos en el lote 2240, necesitamos revisión de calidad.",
        "El plan de producción del mes no se va a cumplir por ausentismo.",
        "Requiero autorización para hora extra el fin de semana.",
        "La capacidad instalada es insuficiente para el nuevo pedido.",
        "Necesito balancear las líneas de producción para el nuevo producto.",
        "El operador reporta variaciones en las especificaciones del producto.",
        "Se requiere cambio de turno de producción por mantenimiento programado.",
    ],
    "operaciones.calidad": [
        "El lote recibido del proveedor no cumple las especificaciones.",
        "El cliente rechazó el envío por problemas de calidad en el acabado.",
        "Necesito implementar control estadístico de proceso en la línea 1.",
        "Los resultados del laboratorio indican contaminación en el lote.",
        "Requiero auditoría de calidad al proveedor de empaques.",
        "El producto en proceso tiene variación dimensional fuera de tolerancia.",
        "Necesito actualizar el plan de control del producto modificado.",
        "El área de calidad rechazó el 15% de la producción de ayer.",
        "Se requiere análisis de causa raíz por reclamación del cliente.",
        "El equipo de medición está descalibrado, necesita certificación.",
    ],
    "operaciones.proveedores": [
        "El proveedor de empaque no entregó a tiempo y paró la línea.",
        "Necesito evaluar el desempeño del proveedor principal del trimestre.",
        "El proveedor está en lista negra por incumplimientos previos.",
        "Requiero certificación ISO del proveedor para la auditoría.",
        "El proveedor subió precios 20% sin justificación.",
        "Necesito negociar mejores condiciones de pago con el proveedor.",
        "El proveedor envió material fuera de especificación por segunda vez.",
        "Requiero alta urgente de proveedor alternativo para contingencia.",
        "El proveedor de servicios no cumplió el SLA acordado.",
        "Necesito contrato marco con el proveedor de papelería.",
    ],

    # ── OTRO ──────────────────────────────────────────────────────────────────
    "otro.general": [
        "Necesito información sobre el proceso de onboarding para nuevo ingreso.",
        "¿Cuáles son los beneficios del plan de salud para empleados?",
        "Requiero información sobre el reglamento interno de trabajo.",
        "¿Dónde puedo consultar el organigrama actualizado de la empresa?",
        "Necesito información sobre el programa de capacitación anual.",
        "¿Cómo solicito el reembolso de gastos de viaje?",
        "Necesito información sobre el plan de carrera en la empresa.",
        "¿Qué trámites debo hacer para registrar a mi familiar en el seguro?",
        "Solicito información sobre el programa de becas para hijos.",
        "¿Cuál es el proceso para solicitar permiso por matrimonio?",
    ],
    "otro.sin_clasificar": [
        "Hola, tengo una pregunta pero no sé bien a qué área dirigirme.",
        "Recibí una notificación del sistema pero no entiendo qué significa.",
        "Alguien dejó cajas en el pasillo y no sé a quién reportarlo.",
        "Vi algo en el estacionamiento que me pareció extraño.",
        "Tengo una duda sobre mi contrato pero no sé si es RRHH o legal.",
        "Me llegó un correo de alguien de otra empresa preguntando por datos.",
        "No entiendo la circular que enviaron la semana pasada.",
        "¿A quién le reporto un comportamiento inadecuado de un proveedor?",
        "Encontré documentos con información confidencial en la copiadora.",
        "Tengo una sugerencia para mejorar el proceso pero no sé a quién decirla.",
    ],
    "otro.otro": [
        "Este ticket es para probar el sistema de clasificación.",
        "Mensaje de prueba número uno para verificar funcionamiento.",
        "Test de integración del sistema de tickets compartidos.",
        "Verificación de conectividad con el agente clasificador.",
        "Prueba de carga para medir tiempo de respuesta del sistema.",
        "Este es un mensaje de diagnóstico enviado por el equipo de TI.",
        "Simulación de ticket para capacitación del personal.",
        "Mensaje automático generado por el sistema de monitoreo.",
        "Prueba de flujo completo: clasificar, validar y guardar ticket.",
        "Test final de regresión antes del despliegue a producción.",
    ],
}


# ── Runner ────────────────────────────────────────────────────────────────────
async def send_request(client: httpx.AsyncClient, semaphore: asyncio.Semaphore,
                       msg_id: str, categoria_esperada: str, texto: str) -> dict:
    async with semaphore:
        start = time.time()
        try:
            resp = await client.post(
                AGENT_URL,
                json={"texto": texto, "origen": "test", "provider": PROVIDER},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            elapsed = round(time.time() - start, 2)

            dominio_esperado, cat_esp = categoria_esperada.split(".")
            match = "✅" if data.get("dominio") == dominio_esperado else "❌"
            fuzzy = "🔍" if data.get("requiere_revision") else "  "

            print(
                f"{match}{fuzzy} [{msg_id}] "
                f"esperado={categoria_esperada} | "
                f"got={data.get('dominio')}.{data.get('categoria')} | "
                f"confianza={data.get('confianza')} | "
                f"{elapsed}s"
            )
            return {"id": msg_id, "esperado": categoria_esperada,
                    "dominio": data.get("dominio"), "categoria": data.get("categoria"),
                    "requiere_revision": data.get("requiere_revision"),
                    "confianza": data.get("confianza"), "elapsed": elapsed,
                    "ok": data.get("validated", False), "error": None}

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            print(f"💥 [{msg_id}] ERROR: {e} ({elapsed}s)")
            return {"id": msg_id, "esperado": categoria_esperada,
                    "ok": False, "error": str(e), "elapsed": elapsed}


async def main():
    print(f"\n{'='*70}")
    print(f"  TEST DE CARGA — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  URL       : {AGENT_URL}")
    print(f"  Provider  : {PROVIDER}")
    print(f"  Concurrency: {CONCURRENCY}")
    print(f"  Mensajes/cat: {MESSAGES_PER_CATEGORY}")
    total = sum(min(MESSAGES_PER_CATEGORY, len(msgs)) for msgs in MESSAGES.values())
    print(f"  Total msgs: {total}")
    print(f"{'='*70}\n")

    tasks_data = []
    for categoria, mensajes in MESSAGES.items():
        for i, texto in enumerate(mensajes[:MESSAGES_PER_CATEGORY]):
            tasks_data.append((f"{categoria}[{i+1}]", categoria, texto))

    semaphore = asyncio.Semaphore(CONCURRENCY)
    start_total = time.time()

    async with httpx.AsyncClient() as client:
        tasks = [
            send_request(client, semaphore, msg_id, cat, texto)
            for msg_id, cat, texto in tasks_data
        ]
        results = await asyncio.gather(*tasks)

    elapsed_total = round(time.time() - start_total, 2)

    # ── Resumen ───────────────────────────────────────────────────────────────
    ok       = [r for r in results if r.get("ok")]
    errors   = [r for r in results if r.get("error")]
    revision = [r for r in results if r.get("requiere_revision")]
    dom_ok   = [r for r in ok if r.get("dominio") == r.get("esperado", "").split(".")[0]]

    print(f"\n{'='*70}")
    print(f"  RESUMEN")
    print(f"{'='*70}")
    print(f"  Total enviados  : {len(results)}")
    print(f"  ✅ Validados     : {len(ok)}")
    print(f"  ✅ Dominio OK    : {len(dom_ok)} / {len(ok)}")
    print(f"  🔍 Req revisión  : {len(revision)}")
    print(f"  💥 Errores       : {len(errors)}")
    print(f"  ⏱  Tiempo total  : {elapsed_total}s")
    if ok:
        avg = round(sum(r["elapsed"] for r in ok) / len(ok), 2)
        print(f"  ⏱  Promedio/req  : {avg}s")

    if revision:
        print(f"\n  Categorías que requieren revisión:")
        for r in revision:
            print(f"    - esperado={r['esperado']} | got={r.get('categoria')}")

    if errors:
        print(f"\n  Errores:")
        for r in errors:
            print(f"    - {r['id']}: {r['error']}")

    print(f"{'='*70}\n")

    # ── Guardar resultados en JSON ────────────────────────────────────────────
    fname = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  Resultados guardados en: {fname}\n")


if __name__ == "__main__":
    asyncio.run(main())
