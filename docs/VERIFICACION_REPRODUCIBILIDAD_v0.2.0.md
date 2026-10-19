# Informe de reproducibilidad — SALEM Neurociencia V2

Fecha: 2026-10-19

## Identificación

- Repositorio: https://github.com/salemlenguaje-hue/Salem-Neuro.git
- Etiqueta: `v0.2.0`
- Commit: `f2012ce27b454976886455fa5b3d73b962ebbc35`
- Entorno: Android con Termux
- Python: 3.14.6
- Git: 2.56.0
- OpenSSL: 3.6.5

## Procedimiento y resultados

Se clonó la versión etiquetada en un directorio separado, sin utilizar el árbol de trabajo original para ejecutar las comprobaciones.

- Se verificó que la etiqueta `v0.2.0` apunta al commit indicado.
- La compilación sintáctica de los cinco archivos Python comprobados finalizó correctamente.
- La suite `test_firma_salem`, `test_adversarial_salem` y `test_trazas_salem` terminó con 18 pruebas aprobadas y resultado `OK`.
- Tiempo informado por esa ejecución: 2,609 segundos.

## Limitaciones

La comprobación se realizó en un solo entorno Android/Termux; no constituye una reproducción independiente en otro dispositivo ni una auditoría externa. Una cadena de hashes puede reconstruirse si alguien puede reescribir toda la historia. Un recibo sin firma requiere conservación independiente. Una firma Ed25519 acredita correspondencia con una clave pública confiable, pero no demuestra la verdad científica de los datos ni proporciona por sí misma una marca de tiempo confiable. Las pruebas aprobadas no demuestran cobertura de todos los ataques posibles.

## Próximos pasos

1. Repetir las pruebas en otro entorno independiente.
2. Registrar las versiones de las herramientas en cada ejecución.
3. Documentar la confianza en la clave pública.
4. Conservar anclajes fuera del entorno experimental.
5. Ampliar las pruebas adversariales con casos reproducibles.

## Declaración

Este documento registra resultados observados y sus limitaciones. No afirma validación científica ni auditoría externa. Su creación no modifica el código ni crea, firma o publica una nueva versión.
