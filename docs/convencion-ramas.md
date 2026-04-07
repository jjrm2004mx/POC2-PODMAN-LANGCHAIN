# Convención de Nombres para Ramas

📁 **Archivo:** `docs/convencion-ramas.md`  
📌 **Propósito:** Establecer una convención clara y uniforme para nombrar ramas en este proyecto, basado en Git Flow.  
👥 **Equipo:** 5 personas  
🔄 **Flujo de trabajo:** Git Flow + futura integración con GitHub Actions  
🧰 **Estado de CI/CD:** En planeación (se usará GitHub Actions)

---

## 🕓 Historial de cambios

| Fecha       | Autor        | Descripción                         | Validado por      |
|-------------|--------------|--------------------------------------|-------------------|
| 2025-07-29  | Equipo Dev   | Creación inicial del documento       | Líder técnico     |
| ...         | ...          | ...                                  | ...               |

> ✅ Actualiza este historial con cada cambio importante.

---

## 🔵 Ramas principales (permanentes)

| Rama     | Descripción |
|----------|-------------|
| `main`   | Contiene el código listo para producción. |
| `develop`| Contiene el código de integración. Todas las funcionalidades se integran aquí antes de pasar a producción. |

---

## 🟢 Ramas temporales (de trabajo)

Estas ramas se crean desde `develop` (excepto `hotfix`, que parte de `main`) y se eliminan después de ser integradas mediante *merge* o *pull request*.

| Tipo         | Prefijo     | Formato                         | Ejemplo                            |
|--------------|-------------|----------------------------------|------------------------------------|
| Funcionalidad nueva | `feature/`  | `feature/nombre-descriptivo`      | `feature/login-usuarios`           |
| Corrección de errores | `bugfix/`   | `bugfix/nombre-descriptivo`       | `bugfix/error-carga-imagen`        |
| Corrección urgente en producción | `hotfix/`   | `hotfix/nombre-descriptivo`       | `hotfix/caida-servidor`            |
| Preparación de una versión | `release/`  | `release/numero-version`          | `release/1.3.0`                     |
| Tareas técnicas o de mantenimiento | `chore/`    | `chore/nombre-descriptivo`        | `chore/actualizar-dependencias`    |
| Documentación | `docs/`     | `docs/nombre-descriptivo`         | `docs/actualizar-readme`           |
| Experimentación o prototipos | `test/`     | `test/nombre-descriptivo`         | `test/ui-nueva-navbar`             |

---

## 🧠 Reglas y buenas prácticas

- Utiliza **guiones medios** (`-`) para separar palabras.
- Usa nombres **claros, breves y descriptivos**.
- No incluyas fechas ni nombres de personas.
- Opcional: Si se utiliza un sistema de tickets (como JIRA), puedes anteponer el ID del ticket:
  - `feature/PROY-123-login-usuarios`

---

## 🛠️ Consideraciones para CI/CD (GitHub Actions)

Las ramas están diseñadas para facilitar automatizaciones. Ejemplo de configuración para GitHub Actions:

```yaml
on:
  push:
    branches:
      - main
      - develop
      - release/*
      - hotfix/*
      - feature/*
```

### 🧩 ¿Qué significa el asterisco (`*`) en las ramas?

En este contexto, el asterisco (`*`) actúa como un **comodín** (*wildcard*). Sirve para indicar que la automatización debe aplicarse a todas las ramas cuyo nombre comience con un prefijo específico.

Por ejemplo:

- `release/*` se activa para cualquier rama que comience con `release/`, como:
  - `release/1.0.0`
  - `release/v2.1.1`

- `hotfix/*` incluye ramas como:
  - `hotfix/ajuste-login`
  - `hotfix/correccion-token`

- `feature/*` incluye ramas como:
  - `feature/nueva-ui`
  - `feature/exportar-csv`

Esto permite que el flujo de trabajo de CI/CD escuche múltiples ramas sin necesidad de listarlas una por una.