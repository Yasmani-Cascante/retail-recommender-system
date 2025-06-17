@echo off
echo Revirtiendo cambios a la versión previa...
cd C:\Users\yasma\Desktop\retail-recommender-system

echo Descartando cambios locales no comprometidos...
git reset --hard

echo Volviendo a la versión previa estable...
git reset --hard 2364767a2c5e94f922edb81a07728aa379168d23

echo Restaurando el archivo main.py original...
git checkout 2364767a2c5e94f922edb81a07728aa379168d23 -- src/api/main.py

echo Restaurando el archivo app.yaml original...
git checkout 2364767a2c5e94f922edb81a07728aa379168d23 -- app.yaml

echo Forzando la actualización al repositorio remoto...
git push origin main --force

echo Los cambios han sido revertidos a la versión previa estable.
pause
