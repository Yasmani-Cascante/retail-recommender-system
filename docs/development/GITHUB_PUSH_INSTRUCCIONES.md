# Instrucciones para Subir el Código a GitHub

Este documento te guiará paso a paso para subir tu código al repositorio de GitHub de forma segura, evitando problemas con la protección de secretos.

## Paso 1: Limpiar los Secretos de los Archivos

Ejecuta el script para reemplazar los secretos en los archivos:

```powershell
.\replace_secrets.ps1
```

## Paso 2: Configurar tus Secretos de Forma Segura

1. Crea el archivo `.env.secrets` basado en el ejemplo:

```powershell
copy .env.secrets.example .env.secrets
```

2. Edita el archivo `.env.secrets` con tus credenciales reales:

```powershell
notepad .env.secrets
```

## Paso 3: Confirmar y Subir los Cambios

Añade, confirma y sube tus cambios:

```powershell
git add -A
git commit -m "Removed sensitive information and implemented secure configuration"
git push origin main
```

O si estás trabajando en una rama específica:

```powershell
git push origin fixes
```

## Paso 4: Si GitHub sigue bloqueando el Push

Si GitHub sigue bloqueando el push, sigue estos pasos:

1. Revisa el mensaje de error para obtener el enlace para desbloquear el secreto.
2. Abre el enlace en tu navegador.
3. En la página de GitHub, selecciona la opción "I understand, allow me to push this secret".
4. Una vez desbloqueado, intenta hacer push nuevamente.

## Configuración Adicional (Opcional)

Para que no tengas que introducir tus credenciales cada vez:

```powershell
git config --global user.name "Tu Nombre"
git config --global user.email "tu.email@ejemplo.com"
git config --global credential.helper store
```

## Recursos Adicionales

- [Documentación de Git](https://git-scm.com/doc)
- [Guía de GitHub sobre Push Protection](https://docs.github.com/code-security/secret-scanning/working-with-secret-scanning-and-push-protection/working-with-push-protection-from-the-command-line#resolving-a-blocked-push)
