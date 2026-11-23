# RUNBOOK -- Higiene de Docker Desktop en Windows (limpieza y compactacion del disco virtual)

Procedimiento probado el 21-22/11/2026 en el equipo de desarrollo de Yasmani (Windows, Docker Desktop con WSL 2).
Resultado de aquella vez: dentro de Docker, de ~256 GB a ~65 GB; el archivo `docker_data.vhdx`, de **647,6 GB a
68,5 GB**; espacio libre en C:, de 11 a **590,8 GB**. Detalle en
`docs/0_plans/Transformers/Visual_search/Composite_Embedding_Granular/Evaluacion_Integral_16092026/DCT_Frescura_Contenido_KB_20112026.md`
(seccion 4, observaciones).

---

## 1. Por que hace falta

Docker Desktop guarda imagenes, contenedores y cache de construccion **dentro** de un disco virtual
(`%LOCALAPPDATA%\Docker\wsl\disk\docker_data.vhdx`). Ese archivo crece cuando hace falta espacio, pero **no se
reduce solo**: borrar imagenes (desde la terminal o desde Docker Desktop) libera espacio dentro del disco virtual,
no en Windows. Por eso se acumulan cientos de GB aunque se borren imagenes.

Dos mediciones distintas, las dos correctas:

| Que mide | Comando | Ejemplo del 21/11 |
|---|---|---|
| Lo que hay dentro de Docker | `docker system df` | ~256 GB |
| Lo que ocupa el archivo en Windows | tamano de `docker_data.vhdx` | 647,6 GB |

La diferencia es espacio borrado que el archivo no devolvio. Solo la **compactacion** (seccion 5) lo recupera.

## 2. Cuando hacerlo

- Despues de varios despliegues validados (cada imagen del servicio ocupa ~8 GB).
- Si el espacio libre en C: baja de ~50 GB.
- **Antes** de un `docker build` si el disco esta justo: un disco lleno no falla al arrancar, falla en la primera
  escritura (`ENOSPC`), con mensajes que parecen de la herramienta y no del entorno.

Habito minimo tras cada despliegue validado: `docker builder prune -f --filter "until=168h"`.

## 3. Diagnostico (solo lectura)

Con Docker Desktop en marcha:

```powershell
"vhdx: {0:N1} GB" -f ((Get-Item "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx").Length / 1GB)
Get-PSDrive C | Select-Object @{n='LibreGB';e={[math]::Round($_.Free/1GB,1)}}
docker system df
docker images --digests --format "table {{.Repository}}\t{{.Tag}}\t{{.Digest}}\t{{.CreatedSince}}\t{{.Size}}"
"imagenes huerfanas (dangling): " + (docker images -f dangling=true -q | Measure-Object).Count
```

**Que conservar** (comprobarlo antes de borrar):
- La imagen en produccion (ver `spec.template.spec.containers[0].image` de `gcloud run services describe`).
- La anterior, que es la de vuelta atras.
- `redis:7-alpine` (Redis local para los tests).

Todas las imagenes del servicio estan tambien en el registro de GCP: borrarlas en local no las pierde.

## 4. Limpieza dentro de Docker

Docker Desktop en marcha. Ninguna linea toca las imagenes etiquetadas que se conservan:

```powershell
docker image prune -f                                  # solo huerfanas (dangling)
docker container prune -f                              # contenedores parados (no toca volumenes ni imagenes)
docker builder prune -f --filter "until=168h"          # cache de construccion de mas de 7 dias
# Imagenes concretas que ya no se necesitan (sustituir por las del diagnostico):
# docker image rm <repositorio>:<etiqueta>
docker images --digests --format "{{.Tag}} {{.Digest}}" gcr.io/retail-recommendations-449216/retail-recommender   # comprobar lo conservado
docker system df
```

Nota: borrar la cache de construccion hace que la siguiente construccion sea lenta (el 22/11 tardo 24 min).

## 5. Compactacion del disco virtual (devuelve el espacio a Windows)

**Condiciones, todas obligatorias** (el primer intento del 21/11 no compacto nada, probablemente porque Docker
seguia en marcha):
1. Salir de Docker Desktop: icono de la bandeja > *Quit Docker Desktop*.
2. Abrir **PowerShell como administrador**.
3. No interrumpir el proceso (tarda varios minutos).

Riesgo: pequeno, si se interrumpe la compactacion. Lo peor que se perderia son las imagenes locales
(recuperables desde el registro) y los volumenes locales (Redis de pruebas).

```powershell
# 0. Comprobaciones previas (si alguna falla, parar)
([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)   # esperado: True
Get-Process "Docker Desktop","com.docker.backend" -ErrorAction SilentlyContinue | Select-Object Name, Id                                                    # esperado: nada
wsl --shutdown
wsl --list --verbose                                                                                                                                        # esperado: todas Stopped
$vhdPath = "C:\Users\yasma\AppData\Local\Docker\wsl\disk\docker_data.vhdx"
"antes: {0:N1} GB" -f ((Get-Item $vhdPath).Length / 1GB)

# 1. Compactacion con diskpart (cualquier edicion de Windows)
@"
select vdisk file="$vhdPath"
attach vdisk readonly
compact vdisk
detach vdisk
"@ | Set-Content -Encoding ascii "$env:TEMP\compact_docker.txt"
diskpart /s "$env:TEMP\compact_docker.txt"          # esperado: "DiskPart successfully compacted the virtual disk file."

# 2. Resultado
"despues: {0:N1} GB" -f ((Get-Item $vhdPath).Length / 1GB)
Get-PSDrive C | Select-Object @{n='LibreGB';e={[math]::Round($_.Free/1GB,1)}}
```

Alternativa en Windows Pro con Hyper-V (`Get-Command Optimize-VHD` disponible): `Optimize-VHD -Path $vhdPath -Mode Full`
en lugar del paso 1.

Despues: arrancar Docker Desktop y repetir la comprobacion de imagenes conservadas de la seccion 4.

**Como leer el resultado**: el archivo debe quedar cerca de lo que `docker system df` dice que hay dentro. Si no
cambia nada, la compactacion no se hizo (Docker en marcha o consola sin administrador).

## 6. Registro de ejecuciones

| Fecha | Dentro de Docker | `docker_data.vhdx` | Libre en C: | Notas |
|---|---|---|---|---|
| 21-22/11/2026 | ~256 GB -> ~65 GB | 647,6 GB -> 68,5 GB | 11 GB -> 590,8 GB | Primera vez; 33 imagenes -> 6, 74 contenedores -> 1, cache 134 GB -> 47 GB. Un primer intento de compactacion no hizo nada (Docker en marcha) |

Fuentes: [Windows OS Hub, shrink WSL2 and Docker Desktop VHDX files](https://woshub.com/shrink-wsl2-and-docker-desktop-vhdx-files-in-windows/);
[DEV Community, reclaiming over 350 GB from bloated VHDX files](https://dev.to/hamada147/docker-on-windows-eating-your-c-drive-how-i-reclaimed-over-350gb-from-bloated-vhdx-files-11dm).
