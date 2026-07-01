#!/usr/bin/env python3
"""
ImageFlow — Internal Image Processing Service
Home lab deployment. Not for production.

Security model (intentional design):
  SECURE  — allowlist extensions, magic byte check, UUID rename
  SECURE  — plugin uploads: .py only, AST safety check at upload time
  VULNERABLE — processor.py exec() fallback with no re-validation at runtime
               Developer's blind spot: "a valid image can't contain Python code"
               Polyglot attack path: GIF89a header passes magic check,
               fails Pillow parsing, falls into exec() in the processor.
"""

import os
import ast
import uuid
from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from processor import process_image

app = Flask(__name__)

# ── Folders ───────────────────────────────────────────────────────────────────
BASE = os.path.dirname(__file__)
UPLOAD_FOLDER    = os.path.join(BASE, "uploads")
PROCESSED_FOLDER = os.path.join(BASE, "processed")
PLUGIN_FOLDER    = os.path.join(BASE, "plugins")

for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER, PLUGIN_FOLDER]:
    os.makedirs(folder, exist_ok=True)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# ── Image allowlist: extension → accepted magic byte prefixes ─────────────────
ALLOWED_IMAGES = {
    ".jpg":  [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png":  [b"\x89PNG\r\n\x1a\n"],
    ".gif":  [b"GIF87a", b"GIF89a"],   # ← polyglot attack lands here
    ".webp": [b"RIFF"],
    ".bmp":  [b"BM"],
}

# ── AST safety check config ───────────────────────────────────────────────────
# Blocks direct dangerous imports and calls.
# DOES NOT catch: importlib.import_module('socket'),
#                 getattr(__builtins__, 'exec'), vars()['__builtins__'], etc.
BLOCKED_IMPORTS = {
    "os", "subprocess", "socket", "pty", "sys", "shutil",
    "ctypes", "threading", "multiprocessing", "signal",
    "resource", "platform", "popen2", "commands",
}
BLOCKED_BUILTINS = {
    "exec", "eval", "__import__", "compile", "execfile",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def magic_bytes_ok(data: bytes, ext: str) -> bool:
    for magic in ALLOWED_IMAGES.get(ext, []):
        if data[:len(magic)] == magic:
            return True
    return False


def ast_safety_check(source: str) -> tuple[bool, str]:
    """
    Parse the plugin source and walk the AST looking for dangerous patterns.
    Returns (safe: bool, reason: str).

    Intentional blind spots (the vulnerability):
    - importlib.import_module('socket') → AST sees Import of 'importlib' (allowed)
    - getattr(__builtins__, 'exec')     → attribute access, not tracked
    - vars()['__builtins__']            → runtime dict access, not resolvable statically
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    for node in ast.walk(tree):

        # Direct imports: import os / import subprocess
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in BLOCKED_IMPORTS:
                    return False, f"Blocked import: '{alias.name}'"

        # From imports: from os import system / from subprocess import run
        if isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in BLOCKED_IMPORTS:
                    return False, f"Blocked import: 'from {node.module}'"

        # Direct builtin calls: exec(...) / eval(...)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in BLOCKED_BUILTINS:
                    return False, f"Blocked call: '{node.func.id}()'"

    return True, "OK"


def file_info(folder: str, filename: str, original_name: str = "") -> dict:
    path = os.path.join(folder, filename)
    size = os.path.getsize(path)
    if size < 1024:
        size_str = f"{size} B"
    elif size < 1024 ** 2:
        size_str = f"{size / 1024:.1f} KB"
    else:
        size_str = f"{size / 1024 ** 2:.1f} MB"
    return {
        "filename": filename,
        "original_name": original_name or filename,
        "size": size_str,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload/image", methods=["POST"])
def upload_image():
    """
    Secure upload gate for images.
    Checks: allowlist extension, magic bytes, size limit, UUID rename.
    Does NOT check whether the file contains executable code — developer's
    reasoning: 'a real image binary can't be Python source'.
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file in request."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Filename is empty."}), 400

    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_IMAGES:
        allowed = ", ".join(ALLOWED_IMAGES.keys())
        return jsonify({"ok": False, "error": f"'{ext}' is not an allowed image type. Accepted: {allowed}"}), 400

    data = f.read()

    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"ok": False, "error": "File exceeds 10 MB limit."}), 400

    if not magic_bytes_ok(data, ext):
        return jsonify({"ok": False, "error": "File header does not match its extension. Upload rejected."}), 400

    file_id  = str(uuid.uuid4())
    filename = file_id + ext
    dest     = os.path.join(UPLOAD_FOLDER, filename)

    with open(dest, "wb") as out:
        out.write(data)

    return jsonify({
        "ok":           True,
        "file_id":      file_id,
        "filename":     filename,
        "original_name": f.filename,
        "url":          f"/uploads/{filename}",
        **file_info(UPLOAD_FOLDER, filename, f.filename),
    })


@app.route("/upload/plugin", methods=["POST"])
def upload_plugin():
    """
    Secure upload gate for Python filter plugins.
    Checks: .py extension only, AST-based code safety analysis.
    The AST check is real and blocks naive attacks — but not importlib-based ones.
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file in request."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Filename is empty."}), 400

    _, ext = os.path.splitext(f.filename.lower())
    if ext != ".py":
        return jsonify({"ok": False, "error": "Only .py files are accepted for filter plugins."}), 400

    try:
        source = f.read().decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({"ok": False, "error": "File is not valid UTF-8 text."}), 400

    safe, reason = ast_safety_check(source)
    if not safe:
        return jsonify({"ok": False, "error": f"Security check failed — {reason}"}), 400

    file_id  = str(uuid.uuid4())
    filename = file_id + ".py"
    dest     = os.path.join(PLUGIN_FOLDER, filename)

    with open(dest, "w") as out:
        out.write(source)

    return jsonify({
        "ok":            True,
        "file_id":       file_id,
        "filename":      filename,
        "original_name": f.filename,
    })


@app.route("/process/<file_id>", methods=["POST"])
def process(file_id):
    """
    Passes the uploaded file to the processing service with user-supplied params.
    No re-validation happens here — the upload gate is trusted unconditionally.
    """
    filename = next(
        (fn for fn in os.listdir(UPLOAD_FOLDER) if fn.startswith(file_id)),
        None,
    )
    if not filename:
        return jsonify({"ok": False, "error": "File not found."}), 404

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    params   = request.get_json(silent=True) or {}
    result   = process_image(filepath, PROCESSED_FOLDER, file_id, params)
    return jsonify(result)


@app.route("/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/processed/<filename>")
def serve_processed(filename):
    return send_from_directory(PROCESSED_FOLDER, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
