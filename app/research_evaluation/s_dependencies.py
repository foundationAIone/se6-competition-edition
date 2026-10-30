"""Small pinned source/kernel dependencies, extracted into isolated Linux root."""
from pathlib import Path
import hashlib,json,zipfile
LANE=Path(__file__).resolve().parents[2]
def main():
    destination=LANE/'linux-deps';rows=[]
    for path in sorted((LANE/'linux-s-wheels').glob('*.whl')):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if not (destination/member.filename).resolve().is_relative_to(destination.resolve()):raise ValueError('WHEEL_PATH_ESCAPE')
            archive.extractall(destination)
        rows.append(dict(name=path.name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    output=LANE/'s-evaluation/LINUX_S_DEPENDENCIES.json';output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(dict(python='CPython3.12.3 Linux WSL',dependencies=rows,model_downloads=0),indent=2))
    print(json.dumps(rows))
if __name__=='__main__':main()
