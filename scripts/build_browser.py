"""Build an install-free, same-origin Pyodide site from the project wheel."""

import argparse
from base64 import b64decode
from hashlib import sha256, sha512
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
PYODIDE_LICENSE_HASH = "1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5"
RELEASE = f"https://github.com/pyodide/pyodide/releases/download/{VERSION}/"
PACKAGES = f"https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/"
FILES = ("pyodide.js","pyodide.asm.js","pyodide.asm.wasm","python_stdlib.zip","pyodide-lock.json")
ELK_VERSION = "0.11.0"
ELK_HASH = b64decode("u4J8h9mwEDaYMqo0RYJpqNMFDoMK7f+pu4GjcV+N8jIC7TRdORgzkfSjTJemhqONFfH6fBI3wpysgWbhgVWIXw==").hex()


def checked(url, expected, path, digest=sha256):
    if path.is_file():
        data = path.read_bytes()
        if digest(data).hexdigest()==expected:
            return data
    with urlopen(url,timeout=45) as response:
        data = response.read(32*1024*1024+1)
    if digest(data).hexdigest()!=expected:
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


def notices(output,cache):
    license_url = f"https://raw.githubusercontent.com/pyodide/pyodide/{VERSION}/LICENSE"
    data = checked(license_url,PYODIDE_LICENSE_HASH,cache/f"pyodide-{VERSION}-LICENSE")
    (output/"pyodide-LICENSE.txt").write_bytes(data)
    (output/"THIRD_PARTY.txt").write_text(
        f"Pyodide {VERSION} (MPL-2.0)\n"
        f"Source: https://github.com/pyodide/pyodide/tree/{VERSION}\n"
        "License: pyodide-LICENSE.txt\n\n"
        f"elkjs {ELK_VERSION} (EPL-2.0)\n"
        f"Source: https://www.npmjs.com/package/elkjs/v/{ELK_VERSION}\n"
        f"License: vendor/elkjs-{ELK_VERSION}/LICENSE.md\n\n"
        "Python dependency versions are listed in runtime-metadata.json. See the metadata in their wheels.\n",
        encoding="utf-8")


def elk_files(output,cache):
    archive = f"elkjs-{ELK_VERSION}.tgz"
    checked("https://registry.npmjs.org/elkjs/-/"+archive,ELK_HASH,cache/archive,sha512)
    target = output/"vendor"/f"elkjs-{ELK_VERSION}"
    target.mkdir(parents=True,exist_ok=True)
    with tarfile.open(cache/archive,"r:gz") as bundle:
        for name in ("elk-api.js","elk-worker.min.js"):
            with bundle.extractfile("package/lib/"+name) as source:
                (target/name).write_bytes(source.read())
        for item in bundle.getmembers():
            if item.isfile() and re.fullmatch(r"package/(LICENSE|NOTICE)(\.[A-Za-z]+)?",item.name,re.I):
                with bundle.extractfile(item) as source:
                    (target/Path(item.name).name).write_bytes(source.read())
    return target.relative_to(output).as_posix()+"/"


def build(output,wheel,cache):
    # Examples come from the project's existing adapters and benchmark generator.
    from pretty_smd.benchmark import cases, resource
    from pretty_smd.pipeline import generate
    from pretty_smd.stress import generated_case, holdout_cases

    output.mkdir(parents=True,exist_ok=True)
    build_gallery(output/"gallery")
    runtime = output/"runtime"/VERSION
    packages = runtime_files(runtime,cache)
    elk = elk_files(output,cache)
    notices(output,cache)
    wheel_data = wheel.read_bytes()
    if not re.fullmatch(r"pretty_smd-[0-9.]+-py3-none-any\.whl",wheel.name):
        raise ValueError("Use the built pure-Python pretty_smd wheel.")
    digest = sha256(wheel_data).hexdigest()
    destination = output/"engine"/digest[:16]/wheel.name
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(wheel_data)
    for name in ("app.css","app.js","editor.js"):
        shutil.copyfile(ROOT/"pretty_smd/static"/name,output/name)
    html = (ROOT/"pretty_smd/static/index.html").read_text(encoding="utf-8")
    html = html.replace('href="/app.css"','href="./app.css"').replace('src="/editor.js"','src="./editor.js"')
    html = html.replace('<script src="/app.js" defer></script>',
                        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                        'script-src \'self\' \'wasm-unsafe-eval\'; style-src \'self\'; connect-src \'self\'; '
                        'worker-src \'self\'; img-src \'self\' blob:; base-uri \'none\'; object-src \'none\'">\n'
                        '<script src="./browser-transport.js" defer></script>\n'
                        '<script src="./app.js" defer></script>')
    html = html.replace('<label for="language">', '<a class="header-link" href="./gallery/">Gallery</a>\n    <label for="language">')
    html = html.replace('</body>','<footer><a href="./THIRD_PARTY.txt">Third-party licenses</a></footer>\n</body>')
    (output/"index.html").write_text(html,encoding="utf-8")
    gallery = output/"gallery/index.html"
    html = gallery.read_text(encoding="utf-8").replace(
        '<h2 id="gallery-title">','<a href="../">線上編輯器</a> · <a id="edit-case">在編輯器開啟案例</a>\n      <h2 id="gallery-title">')
    hybrid_card = ('<figure data-engine="hybrid"><figcaption>Auto / Hybrid</figcaption>'
        '<div class="view"><img alt="Hybrid 的 UML 排版" hidden></div><p><a hidden>開啟 SVG</a> <span></span></p>'
        '</figure>')
    html = html.replace('    </div>\n    <noscript>',f'      {hybrid_card}\n    </div>\n    <noscript>')
    gallery.write_text(html,encoding="utf-8")
    for src in sorted((ROOT/"pretty_smd/browser").glob("*.js")):
        shutil.copyfile(src,output/src.name)
    examples = {}
    for revision in ("p1","p2"):
        examples.update({name:model for name,model in json.loads(resource(f"mock-converter-{revision}.json")).items()
                         if isinstance(model,dict)})
    for name,sample in (("benchmark-sparse",("sparse",50)),("benchmark-cycles",("cycles",25)),
                        ("benchmark-loops",("loops",25))):
        examples[name] = generated_case(*sample)
    samples = dict((*cases(),*holdout_cases()))
    examples.update({f"gallery-{name}":model for name,model in samples.items()})
    target = output/"gallery/benchmarks/phase4/hybrid"
    target.mkdir(parents=True,exist_ok=True)
    hybrid_rows = []
    for name in ("pseudostates","self-loop","nested","orthogonal","synthetic-48","holdout-cycles-16"):
        try:
            result = generate(samples[name],algorithm="hybrid",timeout=10)
            (target/f"{name}.svg").write_text(result.svg,encoding="utf-8")
            quality = result.quality
            hybrid_rows.append(dict(case=name,algorithm="hybrid",status="ok",edge_crossings=quality["edge_crossings"],
                       edge_bends=quality["edge_bends"],layout_ms=quality["execution_ms"]))
        except ValueError as error:
            hybrid_rows.append(dict(case=name,algorithm="hybrid",status="unavailable",reason=str(error)[:200]))
    write_json(target/"comparison.json",hybrid_rows)
    write_json(output/"examples.json",examples)
    config = {"version":VERSION,"runtime":runtime.relative_to(output).as_posix()+"/","elk":elk,
              "wheel":destination.relative_to(output).as_posix(),"wheelSha256":digest,
              "runtimeBytes":sum(path.stat().st_size for path in runtime.iterdir()),
              "wheelBytes":len(wheel_data),"dependencies":packages}
    (output/"runtime-config.js").write_text("self.PRETTY_RUNTIME="+json.dumps(config)+";\n",encoding="utf-8")
    write_json(output/"runtime-metadata.json",config)
    paths = [path for path in sorted(output.rglob("*")) if path.is_file()
             and path.name not in (".nojekyll","sw.js","offline-manifest.js")
             and (path.suffix!=".whl" or path==destination or path.is_relative_to(runtime))]
    hashes = {path.relative_to(output).as_posix():sha256(path.read_bytes()).hexdigest() for path in paths}
    manifest = {"version":sha256(json.dumps(hashes).encode()).hexdigest()[:20],
                "files":list(hashes)}
    (output/"offline-manifest.js").write_text("self.PRETTY_OFFLINE="+json.dumps(manifest)+";\n",
                                             encoding="utf-8")
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
