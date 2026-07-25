# ProxyForge — Contexto para continuar

## Objetivo
App de escritorio Windows (gratis, no open-source) que convierte imágenes de cartas MTG en proxies imprimibles a **1200 DPI reales** con upscaling IA por GPU, y arma PDFs listos para imprimir. Distribuida globalmente vía GitHub. Repo: **Boffo90/proxyforge**. Autor: Boffo90. Donaciones: paypal.me/warchazzz. Separado del negocio local de venta (NO mencionar ventas).

## Arquitectura (todo en C:/Users/smyo9/upscaler)
- `main.py` — entrypoint (`from gui import App`)
- `version.py` — APP_NAME, APP_VERSION (2.6.0), GITHUB_REPO, DONATE_URL. **Fuente única de versión.**
- `config.py` — rutas (ROOT frozen-aware), MODELS, modo Auto, DPI (2976×4160=1200dpi), constantes de borde/bleed/calibración/shadow, load_settings/save_settings (settings.json), ICON_FILE.
- `gui.py` — customtkinter. Clases: `App`, `QueueItem`, `ImportDialog`, `MPCDialog`, `ExportDialog`, `SetupDialog`. Paleta oro/arena.
- `upscale.py` — pipeline: normalizar→(trim MPC bleed)→Real-ESRGAN x4→fit 2976×4160→DPI 1200. Sin GPU: resize LANCZOS.
- `scryfall.py` — fetch por nombre/link/decklist/Gatherer/Archidekt; `resolve_decklist`, `fetch_archidekt`, `_fetch_gatherer`, `download_to_temp` (maneja Drive, timeout 120).
- `mpcfill.py` — API mpcfill.com: `search`, `download`, `fetch_thumb`.
- `print_sheet.py` — `build_pdf` (layouts 3×3/4×2, calidad, calibración, shadow, sharpen, bleed, duplex, split), `build_calibration`, `build_shadow_test`, `_deepen_black_border`.
- `bootstrap.py` — primer arranque descarga motor+modelos; `probe_gpu` (Vulkan-only).
- `update.py` — auto-update GitHub Releases; `_write_swap_script`.
- `installer.iss` — Inno Setup (per-user, sin admin). Compila con ISCC en `C:/Users/smyo9/AppData/Local/Programs/Inno Setup 6/ISCC.exe`.
- `icon.ico` — carta+estrella oro (embebido).
- Motor/modelos NO en el repo (.gitignore); se descargan en primer arranque.

## Modelos (elegidos por comparación real)
- Escaneos (pre 2023-06 LTR): AnimeVideo v3
- Renders digitales: UltraSharp
- Sets realistas (msc/spm/mar Marvel): Real-ESRGAN x4+ (caras)
- Auto decide por released_at (fecha) o tamaño de archivo. UltraSharp/high-fidelity son CC-BY-NC (bajados del repo Upscayl).

## Decisiones tomadas
- Licencia **source-available** (no MIT): código visible, prohibido redistribuir/vender/rebrandear.
- Calibración impresora del usuario (Epson ET-2800, 300gsm laminado mate frío): **perfil color 9, shadow lift Medium (+14)**, sharpening Off, shift-down según papel.
- Shadow lift: curva quirúrgica solo bajo nivel 75 (no toca medios).
- Deepen border: snap **binario** a negro (no proporcional) para evitar moteado; detección por-línea con guard de croma (marco neutro croma≤14) y **cobertura por lado ≥88%** (rechaza lados de arte). Control manual por carta en preview (clic izq cicla auto/off/on) + sliders Amount/Manual width.
- MPC bleed: recorte por proporción (0.733 vs 0.716), toggle "Trim MPC bleed" ON por defecto.
- Gatherer link → SIEMPRE imagen de Gatherer (Scryfall solo da mid+metadata).

## Problemas resueltos (historial en changelog_ai.md)
Auto-update (3 iteraciones: PID→imagename, timeout sin consola, START no funciona→ejecución directa), duplex preview pairing, borde negro (5+ iteraciones), moteado, Winota extended-art, MPC search, multi-hoja preview, exclusión de cartas, cardback custom.

## Problemas pendientes / posibles
- MPC search depende de API mpcfill.com + Google Drive (frágil si cambian).
- Gatherer de cartas extranjeras que Scryfall NO conoce: sin mid no se puede bajar.
- Imágenes MPC ya son 1200dpi pero pasan por el AI igual (no optimizado para saltear).
- Exclusión de cartas: el PDF recompacta (no deja huecos); preview muestra posición original con X.
- Firma de código pendiente (Azure Trusted Signing ~US$10/mes) → SmartScreen avisa "editor desconocido".

## Próximos pasos sugeridos
- Publicar release v2.6.0 (subir ProxyForge.exe PRIMERO, luego installer/ProxyForge_Setup-2.6.0.exe; tag v2.6.0).
- Email a Moxfield NO reintentar (rechazado: WotC les objetó tools de proxies).
- Difusión r/mtgproxies cuando el usuario quiera.

## Convención de idioma
**Todo lo del proyecto va en inglés** (app global): UI, código, comentarios, docs, README, changelog y títulos/descripciones de release en GitHub. El chat con el usuario es en español, pero cualquier entregable que viva en el repo o se muestre al usuario final es en inglés.

## NO volver a intentar
- **Moxfield API**: rechazado por su soporte (WotC). No reintentar ni scrapear.
- **Integrar venta con la app / mencionar ventas**: prohibido por el usuario.
- **Voseo argentino**: usuario es chileno, español neutro/tuteo.
- **START/PowerShell/explorer para relanzar** el exe tras update: NO funciona en su PC; usar ejecución directa (cmd hijo).
- **timeout en .bat sin consola**: falla; usar ping para pausas, rutas System32 absolutas.
- **Peso proporcional en deepen border**: causa moteado; usar snap binario.
- **Detección de borde por carta completa**: rechaza SPG (arte 3 lados + banda inferior); usar por-lado/por-línea.
- **Peso mean/std en detección**: outliers lo rompen; usar percentiles.

## Flujo de release (cada versión)
1. Editar version.py + installer.iss (subir versión)
2. Compilar: `python -m PyInstaller --noconfirm --onefile --windowed --name ProxyForge --icon "...icon.ico" --add-data "...icon.ico;." --collect-all customtkinter --collect-all tkinterdnd2 --workpath SCRATCH/build --distpath SCRATCH/dist --specpath SCRATCH main.py`
3. cp exe a raíz; ISCC installer.iss; rm installer viejo
4. git commit + push
5. Usuario crea release en GitHub (exe primero, installer con "_" después)
6. Actualizar docs/changelog_ai.md

## Deps
customtkinter 6.0.0, pillow, requests, tkinterdnd2, reportlab, numpy, pyinstaller. Bash tool = Git Bash (ojo: `timeout` resuelve al Unix; usar rutas absolutas).
