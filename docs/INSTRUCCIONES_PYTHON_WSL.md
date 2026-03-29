# 🐍 Instrucciones para Ejecutar Python en WSL

Documento de configuración para ejecutar scripts Python en WSL (Windows Subsystem for Linux).

---

## 📋 Requisitos Previos

- WSL2 instalado en Windows
- Python 3.12+ instalado en WSL
- Acceso a terminal bash en WSL

---

## 🚀 Pasos para Ejecutar Scripts Python

### **Paso 1: Crear Virtual Environment**

```bash
python3 -m venv venv
```

**Qué hace:** Crea un entorno virtual aislado en la carpeta `venv/`

---

### **Paso 2: Activar Virtual Environment**

```bash
source venv/bin/activate
```

**Qué hace:** Activa el entorno virtual. Verás `(venv)` al inicio del prompt.

**Salida esperada:**
```bash
(venv) jjrm@C85291:~/podman/ai-stack$
```

---

### **Paso 3: Instalar Dependencias**

```bash
pip install httpx
```

O si necesitas múltiples paquetes:

```bash
pip install httpx pydantic fastapi uvicorn
```

---

### **Paso 4: Ejecutar Scripts Python**

```bash
python3 debug_classify.py "Mi texto aquí" ollama
```

**Nota:** Una vez activado el venv, puedes usar `python3` o incluso `python`.

---

## 🔄 Uso Repetido

Cada vez que abras una **nueva terminal** en WSL, necesitas:

```bash
# 1. Navegar a la carpeta del proyecto
cd ~/podman/ai-stack

# 2. Activar el venv
source venv/bin/activate

# 3. Ejecutar tu script
python3 debug_classify.py "Mi email no funciona" ollama
```

---

## ❌ Errores Comunes y Soluciones

### **Error: `ModuleNotFoundError: No module named 'httpx'`**

**Causa:** No instalaste las dependencias.

**Solución:**
```bash
source venv/bin/activate
pip install httpx
```

---

### **Error: `externally-managed-environment`**

**Causa:** Intentaste instalar paquetes sin virtual environment.

**Solución:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install httpx
```

---

### **Error: `Command 'python' not found`**

**Causa:** WSL usa `python3` por defecto, no `python`.

**Solución:**
```bash
python3 script.py    # Correcto en WSL
python script.py     # No funciona en WSL
```

---

## 📦 Dependencias del Proyecto

Para instalar todas las dependencias de desarrollo:

```bash
source venv/bin/activate
pip install httpx pydantic asyncpg redis fastapi uvicorn
```

---

## 🎯 Resumen Rápido

| Acción | Comando |
|--------|---------|
| Crear venv | `python3 -m venv venv` |
| Activar venv | `source venv/bin/activate` |
| Instalar paquete | `pip install nombre_paquete` |
| Ejecutar script | `python3 script.py args` |
| Desactivar venv | `deactivate` |

---

## 💡 Tips

1. **Guarda las dependencias en `requirements.txt`:**
   ```bash
   pip freeze > requirements.txt
   ```

2. **Luego instálalas rápido:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verifica qué está instalado:**
   ```bash
   pip list
   ```

4. **Usa alias para activar venv más rápido:**
   ```bash
   alias venv='source venv/bin/activate'
   ```
   Luego solo: `venv`

---

**Última actualización:** Marzo 29, 2026
