# Brand assets

- `source/ral_wordmark.png` — RAL's master wordmark, copied verbatim from
  the main RAL workspace repo (`assets/branding/logo_main.png`). If that
  master file changes, re-copy it here rather than editing this one.
- `generate-logos.py` — renders the workspace icons from the source
  wordmark using RAL's real brand colors (Plum `#2B1B3D` / Lilac `#D1C4E9`).
- `out/` — generated output, committed so the icons are available without
  running Python:
  - `ral-crm-icon-512.png` / `ral-crm-icon-1024.png` — plum background,
    lilac wordmark. Upload `-512` (or `-1024` for higher-DPI displays) in
    Twenty's Settings → General → Workspace as the workspace logo.
  - `ral-crm-icon-transparent-512.png` — lilac-on-transparent removed,
    plum wordmark on transparent background, for light-background contexts
    (e.g. embedding in docs).

Regenerate after changing the source or the target sizes:
```bash
pip install pillow   # if not already installed
python brand/generate-logos.py
```
