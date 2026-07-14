# IG Niche Scraper

Scraper de perfiles de Instagram desde hashtags de nicho. Interfaz web con backend Selenium que abre Chrome con tu sesión existente.

![screenshot](https://img.shields.io/badge/python-3.9+-blue) ![license](https://img.shields.io/badge/license-MIT-green)

## Cómo funciona

1. Abre Chrome con una copia de tu perfil (cookies de sesión)
2. Navega a hashtags de nicho (#emprendimiento, #motivacion, #dinero, etc.)
3. Recorre posts extrayendo usernames de autores y comentaristas
4. Muestra los perfiles en tiempo real en una interfaz web local

## Requisitos

- **Python 3.9+**
- **Google Chrome** instalado
- **Sesión de Instagram** activa en Chrome (debes estar logueado)

## Instalación

```bash
git clone https://github.com/pazosimon01/ig-niche-scraper.git
cd ig-niche-scraper
pip install -r requirements.txt
```

## Uso

```bash
python ig_scraper.py
```

Se abrirá un servidor local en `http://localhost:9876`. Abre esa URL en tu navegador.

### Desde la interfaz web:

1. **Selecciona la cantidad** de perfiles: 50, 100, 200, 300, 500 o 1000
2. **Haz click en "Iniciar Scraping"** — se abrirá Chrome automáticamente
3. **Observa el progreso** en tiempo real (contador + barra de progreso)
4. **Copia o descarga** los perfiles con los botones de abajo

### Importante

- **Cierra Chrome** antes de iniciar el scraping (la app abre su propia instancia)
- Debes tener **sesión activa de Instagram** en Chrome
- La app copia tus cookies a un perfil temporal (no modifica tu perfil original)

## Personalización

Edita las variables al inicio de `ig_scraper.py`:

```python
# Hashtags a scrapear (agrega o quita los que quieras)
HASHTAGS = ["emprendimiento", "motivacion", "dinero"]

# Puerto del servidor web
PORT = 9876
```

## Estructura

```
ig_scraper.py      # App completa (backend + frontend)
requirements.txt   # Dependencias Python
README.md          # Este archivo
```

## Disclaimer

Esta herramienta es solo para uso educativo e investigación. Úsala de forma responsable y respeta los Términos de Servicio de Instagram.

## Licencia

MIT
