# Translayer for Windows

Double-click `Translayer.exe`. It starts a local Translayer server and opens the
web UI in your default browser.

Keep the console window open while translating files. Closing it stops the local
server.

This package contains the Translayer app. For full PPTX preview and local OCR
features, Windows must also have these command-line tools available on `PATH`:

- LibreOffice (`soffice.exe`)
- Poppler (`pdftoppm.exe`)
- Tesseract OCR (`tesseract.exe`) with the language packs you need, such as
  English, German, and Simplified Chinese

Cloud translation providers are called only when you select and configure them
in the web UI. Uploaded documents and intermediate files are processed on the
local machine.
