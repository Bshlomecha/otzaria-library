import subprocess
from pathlib import Path

dar_files_path = Path("/workspaces/patriots/new/pninim")
target_folder = Path("/workspaces/patriots/new/html")

for root, dirs, files in dar_files_path.walk():
    for file in files:
        file_path = root / file
        if file_path.name != "index":
            continue
        rel = f"{file_path.relative_to(dar_files_path).parent}.html"
        target_path = target_folder / rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["dar", str(file_path), "-t", "html", "-f", "dar", "-e", "-o", str(target_path)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error processing {file_path}: {e}")
