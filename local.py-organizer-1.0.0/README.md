# py-organizer — VS Code Extension

Auto-organizes Python files **on every save** (or via `Ctrl+Shift+I`).

## What it does

### Import order (PEP 8)
```
import os                        # 1. stdlib plain
from pathlib import Path         # 2. stdlib from

import requests                  # 3. third-party plain
from pydantic import BaseModel   # 4. third-party from

import myutils                   # 5. local plain
from .models import Job          # 6. local / relative from
```
Blank lines are inserted between each group automatically.

### Class method order
1. `__init__` — always first
2. Other dunder methods (`__repr__`, `__eq__`, …) — A-Z
3. Private methods (`_foo`, `_bar`) — A-Z
4. Public methods — A-Z

Decorators and docstrings are preserved.

---

## Installation (no marketplace needed)

### Option A — Copy folder to VS Code extensions dir
```bash
# macOS / Linux
cp -r py-organizer ~/.vscode/extensions/

# Windows (PowerShell)
Copy-Item -Recurse py-organizer $env:USERPROFILE\.vscode\extensions\
```
Then **restart VS Code** (or run `Developer: Reload Window`).

### Option B — Install via VSIX (recommended for teams)
```bash
# 1. Install vsce if you don't have it
npm install -g @vscode/vsce

# 2. Inside the py-organizer folder
cd py-organizer
vsce package          # produces py-organizer-1.0.0.vsix

# 3. Install in VS Code
code --install-extension py-organizer-1.0.0.vsix
```

---

## Configuration

In your `settings.json`:
```json
{
  "py-organizer.pythonPath": "/path/to/your/venv/bin/python"
}
```
Defaults to `python3` on PATH.

---

## Manual trigger
- **Keyboard**: `Ctrl+Shift+I` / `Cmd+Shift+I`
- **Command palette**: `Python Organizer: Organize current file`

---

## How it works

The VS Code extension calls `scripts/organize.py` (pure stdlib, no pip install needed) which:
1. Parses the file with Python's `ast` module
2. Classifies each import into its PEP-8 bucket
3. Sorts class methods by visibility then name
4. Prints the reorganized source to stdout
5. The extension replaces the editor content in-place before the file is written

Files with syntax errors are left untouched.
