# main.py
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional
import os, zipfile, tempfile

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
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    zip_upload: Optional[UploadFile] = File(None),
    include_hidden: str = Form(default="off"),
    ignore_list: Optional[str] = Form(default="")
):
    include_hidden = include_hidden == "on"
    ignore_names = [name.strip() for name in ignore_list.split(',') if name.strip()]

    def should_ignore(path):
        parts = path.split('/')
        return any(
            part.startswith('.') and not include_hidden or
            any(part == pattern for pattern in ignore_names)
            for part in parts
        )
    
    def is_user_intentionally_ignoring(path):
        # Looser check: match if any ignore pattern is a substring of the path.
        lowered_path = path.lower()
        return any(pattern.lower() in lowered_path for pattern in ignore_names)

    if zip_upload:
        with tempfile.TemporaryDirectory() as tmpdirname:
            zip_path = os.path.join(tmpdirname, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(await zip_upload.read())
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                skipped = []
                MAX_PATH_LEN = 250  # Conservative limit to avoid Windows errors

                for member in zip_ref.infolist():
                    extracted_path = os.path.normpath(os.path.join(tmpdirname, *member.filename.split('/')))

                    # Skip paths that are too long (Windows path limit ~260)
                    if len(extracted_path) > MAX_PATH_LEN:
                        # print(f"[SKIP – too long] {member.filename}")
                        if not is_user_intentionally_ignoring(member.filename):
                            skipped.append(member.filename)
                        continue

                    # Prevent zip-slip attacks
                    if not extracted_path.startswith(os.path.abspath(tmpdirname)):
                        continue

                    try:
                        zip_ref.extract(member, tmpdirname)
                    except Exception as e:
                        # print(f"[EXTRACT FAIL] {member.filename} -> {e}")
                        if not is_user_intentionally_ignoring(member.filename):
                            skipped.append(member.filename)

            # Assume the first folder in the zip is root
            root_folder = next((f for f in os.listdir(tmpdirname) if os.path.isdir(os.path.join(tmpdirname, f))), None)
            if not root_folder:
                return PlainTextResponse("Invalid ZIP: no folder found", status_code=400)
            root_path = os.path.join(tmpdirname, root_folder)

            file_paths = []
            for dirpath, _, filenames in os.walk(root_path):
                for filename in filenames:
                    full_path = os.path.join(dirpath, filename)
                    rel_path = os.path.relpath(full_path, root_path)
                    file_paths.append(rel_path.replace("\\", "/"))
    else:
        if not files:
            return PlainTextResponse("No files uploaded", status_code=400)

        file_paths = [f.filename for f in files]
        root_folder = file_paths[0].split('/')[0]
        file_paths = [p[len(root_folder) + 1:] for p in file_paths if p.startswith(root_folder + "/")]

    filtered = [p for p in file_paths if not should_ignore(p)]

    tree = {}
    for path in filtered:
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

    # Append zip warning if needed
    if zip_upload and skipped:
        output += f"\n\n⚠️Skipped {len(skipped)} file(s) due to long path errors in extraction."
    with open("directory_structure.txt", "w", encoding="utf-8") as f:
        f.write(output)

    return PlainTextResponse(output)
