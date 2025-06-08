# main.py
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List
import os

app = FastAPI()

# Serve HTML
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/download-tree")
def download_tree():
    return FileResponse("directory_structure.txt", media_type="text/plain", filename="directory_structure.txt")

@app.post("/upload-preview")
async def upload_preview(
    files: List[UploadFile] = File(...),
    include_hidden: str = Form(default="off")
):
    # reuse your existing logic, but return `PlainTextResponse(output)` instead of FileResponse
    from fastapi.responses import PlainTextResponse

    include_hidden = include_hidden == "on"
    file_paths = [f.filename for f in files]
    root_folder = file_paths[0].split('/')[0]

    stripped = [p[len(root_folder) + 1:] for p in file_paths if p.startswith(root_folder + "/")]
    if not include_hidden:
        stripped = [path for path in stripped if not any(part.startswith('.') for part in path.split('/'))]

    tree = {}
    for path in stripped:
        parts = path.split('/')
        current = tree
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current.setdefault('__files__', []).append(parts[-1])

    def format_tree(d, prefix=""):
        lines = []
        for key in sorted(d):
            if key == '__files__':
                for file in sorted(d['__files__']):
                    lines.append(f"{prefix}└── {file}")
            else:
                lines.append(f"{prefix}├── {key}/")
                lines.extend(format_tree(d[key], prefix + "│   "))
        return lines

    output_lines = [f"{root_folder}/"] + format_tree(tree)
    output = "\n".join(output_lines)
    with open("directory_structure.txt", "w", encoding="utf-8") as f:
        f.write(output)

    return PlainTextResponse(output)
