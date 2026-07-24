# Translayer for Windows

Double-click `Translayer.exe`. It starts a local Translayer server and opens the
web UI in your default browser.

Keep the console window open while translating files. Closing it stops the local
server.

This portable package includes:

- Translayer.exe
- Tesseract OCR with English, German, and Simplified Chinese language data
- Poppler's `pdftoppm.exe` and its runtime files

For full PPTX slide previews, Windows must still have LibreOffice available on
`PATH` as `soffice.exe`. Document translation and local OCR can run from this
portable package without installing Tesseract or Poppler separately.

Cloud translation providers are called only when you select and configure them
in the web UI. Uploaded documents and intermediate files are processed on the
local machine.
