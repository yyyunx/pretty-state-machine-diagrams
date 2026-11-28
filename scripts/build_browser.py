"""Build an install-free, same-origin Pyodide site from the project wheel."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tarfile
from urllib.request import urlopen

from build_gallery import build as build_gallery

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.29.3"
ARCHIVE = f"pyodide-core-{VERSION}.tar.bz2"
ARCHIVE_HASH = "83b764fe1a0ab6a2d76dba035fbef7284e06dac945a958be2d6447eced592f5a"
RELEASE = f"https://github.com/pyodide/pyodide/releases/download/{VERSION}/"
PACKAGES = f"https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/"
FILES = ("pyodide.js","pyodide.asm.js","pyodide.asm.wasm","python_stdlib.zip","pyodide-lock.json")


def checked(url, expected, path):
    if path.is_file():
        data = path.read_bytes()
        if sha256(data).hexdigest()==expected:
            return data
    with urlopen(url,timeout=45) as response:
        data = response.read(32*1024*1024+1)
    if sha256(data).hexdigest()!=expected:
        raise ValueError(f"Integrity check failed for {path.name}.")
    path.write_bytes(data)
    return data


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")


def runtime_files(target, cache):
    target.mkdir(parents=True,exist_ok=True)
    cache.mkdir(parents=True,exist_ok=True)
    archive = cache/ARCHIVE
    checked(RELEASE+ARCHIVE,ARCHIVE_HASH,archive)
    with tarfile.open(archive,"r:bz2") as release:
        for name in FILES:
            member = release.getmember("pyodide/"+name)
            if not member.isfile():
                raise ValueError(f"Expected a regular runtime file {name}.")
            with release.extractfile(member) as source:
                (target/name).write_bytes(source.read())
    lock = json.loads((target/"pyodide-lock.json").read_bytes())
    records = {key.replace("_","-"):value for key,value in lock["packages"].items()}
    if records["jsonschema"]["version"]!="4.23.0":
        raise ValueError("Runtime must match the native jsonschema version.")
    seen = set()
    queue = ["jsonschema"]
    while queue:
        name = queue.pop().replace("_","-")
        if name in seen:
            continue
        seen.add(name)
        details = records[name]
        filename = details["file_name"]
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl",filename):
            raise ValueError(f"Invalid runtime dependency file {filename}.")
        data = checked(PACKAGES+filename,details["sha256"],cache/filename)
        (target/filename).write_bytes(data)
        queue.extend(details["depends"])
    return {key:records[key]["version"] for key in sorted(seen)}


def build(output,wheel,cache):
    # Examples come from the project's existing adapters and benchmark generator.
    from pretty_smd.benchmark import cases, resource
    from pretty_smd.stress import generated_case, holdout_cases

    output.mkdir(parents=True,exist_ok=True)
    build_gallery(output/"gallery")
    runtime = output/"runtime"/VERSION
    packages = runtime_files(runtime,cache)
    wheel_data = wheel.read_bytes()
    if not re.fullmatch(r"pretty_smd-[0-9.]+-py3-none-any\.whl",wheel.name):
        raise ValueError("Use the built pure-Python pretty_smd wheel.")
    digest = sha256(wheel_data).hexdigest()
    destination = output/"engine"/digest[:16]/wheel.name
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(wheel_data)
    for name in ("app.css","app.js"):
        shutil.copyfile(ROOT/"pretty_smd/static"/name,output/name)
    html = (ROOT/"pretty_smd/static/index.html").read_text(encoding="utf-8")
    html = html.replace('href="/app.css"','href="./app.css"')
    html = html.replace('<script src="/app.js" defer></script>',
                        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                        'script-src \'self\' \'wasm-unsafe-eval\'; style-src \'self\'; connect-src \'self\'; '
                        'worker-src \'self\'; img-src \'self\' blob:; base-uri \'none\'; object-src \'none\'">\n'
                        '<script src="./browser-transport.js" defer></script>\n'
                        '<script src="./app.js" defer></script>')
    html = html.replace('<button id="theme"', '<a class="header-link" href="./gallery/">Gallery</a>\n  <button id="theme"')
    (output/"index.html").write_text(html,encoding="utf-8")
    gallery = output/"gallery/index.html"
    gallery.write_text(gallery.read_text(encoding="utf-8").replace(
        '<h2 id="gallery-title">','<a href="../">線上編輯器</a> · <a id="edit-case">在編輯器開啟案例</a>\n      <h2 id="gallery-title">'),
        encoding="utf-8")
    for src in sorted((ROOT/"pretty_smd/browser").glob("*.js")):
        shutil.copyfile(src,output/src.name)
    examples = {}
    for revision in ("p1","p2"):
        examples.update({name:model for name,model in json.loads(resource(f"mock-converter-{revision}.json")).items()
                         if isinstance(model,dict)})
    for name,sample in (("benchmark-sparse",("sparse",50)),("benchmark-cycles",("cycles",25)),
                        ("benchmark-loops",("loops",25))):
        examples[name] = generated_case(*sample)
    examples.update({f"gallery-{name}":model for name,model in (*cases(),*holdout_cases())})
    write_json(output/"examples.json",examples)
    config = {"version":VERSION,"runtime":runtime.relative_to(output).as_posix()+"/",
              "wheel":destination.relative_to(output).as_posix(),"wheelSha256":digest,
              "runtimeBytes":sum(path.stat().st_size for path in runtime.iterdir()),
              "wheelBytes":len(wheel_data),"dependencies":packages}
    (output/"runtime-config.js").write_text("self.PRETTY_RUNTIME="+json.dumps(config)+";\n",encoding="utf-8")
    write_json(output/"runtime-metadata.json",config)
    (output/".nojekyll").touch()
    print(f"Pyodide {VERSION}, {config['runtimeBytes']:,} runtime/dependency bytes; wheel {len(wheel_data):,} bytes.")
    return config


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--wheel",type=Path,required=True)
    parser.add_argument("--cache",type=Path,default=Path("build/browser-cache"))
    args = parser.parse_args()
    build(args.output,args.wheel,args.cache)
