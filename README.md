# Sincronización automática Garmin → Google Drive

Este proyecto revisa tu cuenta de Garmin Connect una vez al día y guarda un
archivo `garmin_historial.csv` en tu Google Drive con: pasos, calorías,
frecuencia cardiaca (reposo, promedio, máxima), sueño (horas y fases),
Body Battery y estrés promedio.

Cada día se agrega o actualiza una fila. Vas a tener un solo archivo con
todo tu historial, que podés abrir desde cualquier dispositivo.

No necesitás saber programar para activarlo — segui estos pasos una sola vez.

---

## Cómo funciona (para que entiendas el conjunto)

- **GitHub**: es una plataforma gratuita donde vamos a "guardar" este
  proyecto y donde va a correr el script automáticamente todos los días
  (usando una función llamada **GitHub Actions**). No hace falta que sepas
  programar, solo subir estos archivos.
- **Cuenta de servicio de Google**: es como un "usuario robot" que Google te
  deja crear, con permiso limitado solo para escribir en una carpeta
  específica de tu Drive. No es tu usuario personal — es más seguro, porque
  si algo sale mal, ese "robot" solo puede tocar esa carpeta y nada más.
- **Secreto (secret)**: en GitHub, un "secret" es una variable con
  información sensible (contraseñas, claves) que se guarda cifrada y que el
  script puede usar sin que quede visible en el código.

---

## Paso 1: Crear la cuenta de servicio de Google

1. Andá a [Google Cloud Console](https://console.cloud.google.com/) (podés
   entrar con tu cuenta normal de Gmail, es gratis).
2. Creá un proyecto nuevo (arriba a la izquierda, "Select a project" →
   "New Project"). Ponele un nombre como `garmin-finca`.
3. En el buscador de arriba, escribí **"Google Drive API"** y hacé clic en
   **Enable** (habilitar) para ese proyecto.
4. En el menú lateral, andá a **APIs & Services → Credentials**.
5. Hacé clic en **Create Credentials → Service Account**.
6. Ponele un nombre (ej. `garmin-sync-bot`) y hacé clic en **Create and
   Continue**, luego **Done** (no necesitás asignar roles adicionales).
7. En la lista de cuentas de servicio, hacé clic en la que acabás de crear.
8. Andá a la pestaña **Keys → Add Key → Create new key → JSON**. Esto va a
   descargar un archivo `.json` a tu computadora. **Guardalo, lo vas a
   necesitar en el Paso 3.** No lo compartas con nadie.
9. Copiá el **email** de la cuenta de servicio (se ve algo como
   `garmin-sync-bot@garmin-finca.iam.gserviceaccount.com`), lo necesitás
   en el siguiente paso.

## Paso 2: Compartir una carpeta de Drive con la cuenta de servicio

1. En tu Google Drive normal, creá una carpeta nueva, por ejemplo
   `Datos Garmin`.
2. Click derecho → **Compartir** → pegá el email de la cuenta de servicio
   (el que copiaste en el paso anterior) → dale permiso de **Editor**.
3. Abrí esa carpeta y mirá la URL en el navegador. Se va a ver algo así:
   `https://drive.google.com/drive/folders/1A2B3C4D5E6F...`
   La parte después de `/folders/` es el **ID de la carpeta**
   (`1A2B3C4D5E6F...`). Copiala, la necesitás en el Paso 3.

## Paso 3: Subir este proyecto a GitHub

1. Si no tenés cuenta, creá una gratis en [github.com](https://github.com).
2. Creá un repositorio nuevo (podés marcarlo como **privado**, para que
   nadie más lo vea).
3. Subí todos los archivos de esta carpeta al repositorio (podés arrastrar
   los archivos desde la página web de GitHub, opción "Add file → Upload
   files").
4. Dentro del repositorio, andá a **Settings → Secrets and variables →
   Actions → New repository secret**, y creá estos 4 secretos:

   | Nombre del secreto             | Valor                                                   |
   |---------------------------------|----------------------------------------------------------|
   | `GARMIN_EMAIL`                  | El correo con el que entrás a Garmin Connect             |
   | `GARMIN_PASSWORD`                | Tu contraseña de Garmin Connect                          |
   | `GDRIVE_FOLDER_ID`               | El ID de carpeta que copiaste en el Paso 2                |
   | `GOOGLE_SERVICE_ACCOUNT_JSON`    | Abrí el archivo `.json` que descargaste en el Paso 1 con un editor de texto y pegá **todo** el contenido |

5. Listo. El workflow (`.github/workflows/sync.yml`) va a correr
   automáticamente todos los días a la hora configurada (1:00 am hora de
   Guatemala — lo podés cambiar editando el archivo, te dejé un comentario
   ahí explicando cómo).

## Cómo probarlo manualmente (sin esperar al día siguiente)

En GitHub, andá a la pestaña **Actions** de tu repositorio, elegí el
workflow "Sincronizar datos de Garmin a Google Drive", y hacé clic en
**Run workflow**. En un par de minutos debería aparecer (o actualizarse)
el archivo `garmin_historial.csv` en tu carpeta de Drive.

## Notas importantes

- Esto usa una librería **no oficial** (`garminconnect`) que imita el
  login normal de la web de Garmin Connect. Funciona bien para uso
  personal, pero si Garmin cambia algo en su sitio, podría dejar de
  funcionar temporalmente — normalmente se arregla actualizando la
  librería (`pip install --upgrade garminconnect`).
- Tu contraseña de Garmin queda guardada como "secret" en GitHub, cifrada
  y no visible ni siquiera para vos una vez guardada — solo el script
  puede usarla al correr.
- Cuando tengas el CSV en Drive, avisame y lo leemos juntos para empezar a
  ver patrones y trabajar en mejorar sueño, recuperación, etc.
