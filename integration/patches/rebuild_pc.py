"""Repack the user's own PyInstaller onedir executable from its original archive.

Keep every untouched compressed module and PE prefix byte-for-byte identical.
Fail if the expected UI bytecode patterns differ from the inspected build.
"""
from __future__ import annotations

import dis
import hashlib
import marshal
import struct
import types
import zlib
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter

SOURCE = Path(__file__).resolve().parent / "pc-input/VoidEye.exe"
TARGET = Path(__file__).resolve().parent / "pc-update/VoidEye.exe"
EXPECTED = "ac3c3be58c47597f4d5f6efba7ded92f42c813dba7c71598929fffd47242cd03"
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED, "Unexpected Windows executable"
reader = CArchiveReader(str(SOURCE))
pyz = reader.open_embedded_archive("PYZ.pyz")


def hide_call(code: types.CodeType, label: str, begin: int, end: int) -> types.CodeType:
    instructions = list(dis.get_instructions(code))
    matches = [i for i in instructions if i.opname == "LOAD_CONST" and i.argval == label]
    assert len(matches) == 1, f"UI pattern missing: {label}"
    load = matches[0]
    assert begin < load.offset < end
    assert any(i.offset == begin and i.opname == "LOAD_GLOBAL" for i in instructions)
    assert any(i.offset == end - 2 and i.opname == "POP_TOP" for i in instructions)
    raw = bytearray(code.co_code)
    assert (end - begin) % 2 == 0
    for offset in range(begin, end, 2):
        raw[offset] = dis.opmap["NOP"]
        raw[offset + 1] = 0
    updated = code.replace(co_code=bytes(raw))
    assert not any(i.opname == "LOAD_CONST" and i.argval == label for i in dis.get_instructions(updated))
    return updated


def patch_nested(code: types.CodeType, klass: str, method: str, label: str, begin: int, end: int) -> types.CodeType:
    count = 0
    def walk(node: types.CodeType, inside: bool = False) -> types.CodeType:
        nonlocal count
        children = []
        for child in node.co_consts:
            if isinstance(child, types.CodeType):
                in_class = inside or child.co_name == klass
                if in_class and child.co_name == method:
                    child = hide_call(child, label, begin, end)
                    count += 1
                else:
                    child = walk(child, in_class)
            children.append(child)
        return node.replace(co_consts=tuple(children))
    result = walk(code)
    assert count == 1, (klass, method, count)
    return result


replace = {}
for module in ("background_jobs", "cloud_sync", "event_panel", "ui_theme", "clip_core", "clip_transfer", "clip_player", "clip_analysis", "clip_widgets", "fast_preview"):
    name = f"velkozlab_agent.{module}"
    source = Path(__file__).resolve().parent / "pc/velkozlab_agent" / (module + ".py")
    replace[name] = compile(source.read_text(encoding="utf-8"), name.replace(".", "/") + ".py", "exec")

# Preserve original desktop methods, then install the reviewed UI overrides.
# Preserve the recorder's original bytecode and attach reviewed Voice hooks at
# its public manager methods and first-video-clock LiveIndexer construction.
voice_src=(Path(__file__).resolve().parent / "pc/velkozlab_agent/voice_integration.py").read_text(encoding="utf-8")
replace["velkozlab_agent.voice_integration"]=compile(voice_src,"velkozlab_agent/voice_integration.py","exec")
original_main=pyz.extract("velkozlab_agent.main")
original_main=original_main.replace(co_consts=tuple("__preserved_main_disabled__" if x=="__main__" else x for x in original_main.co_consts))
main_skin=compile('exec("__ORIGINAL_MAIN__")\nfrom velkozlab_agent.voice_integration import patch_main\npatch_main(globals())\nif __name__ == "__main__": main()\n', 'velkozlab_agent/main.py','exec')
main_skin=main_skin.replace(co_consts=tuple(original_main if x=="__ORIGINAL_MAIN__" else x for x in main_skin.co_consts))
replace["velkozlab_agent.main"]=main_skin

original_desktop=pyz.extract("velkozlab_agent.desktop")
original_desktop=original_desktop.replace(co_consts=tuple("__preserved_main_disabled__" if x=="__main__" else x for x in original_desktop.co_consts))
skin=(Path(__file__).resolve().parent / "pc/velkozlab_agent/desktop_skin.py").read_text()
wrapper=compile('exec("__ORIGINAL_DESKTOP__")\n'+skin+'\nif __name__ == "__main__": main()\n', 'velkozlab_agent/desktop.py','exec')
wrapper=wrapper.replace(co_consts=tuple(original_desktop if x=="__ORIGINAL_DESKTOP__" else x for x in wrapper.co_consts))
replace["velkozlab_agent.desktop"]=wrapper

# Rebuild PYZ using original compressed blobs for every unchanged module.
with SOURCE.open("rb") as stream:
    stream.seek(pyz._start_offset)
    original_pyz = stream.read(reader.toc["PYZ.pyz"][2])
assert original_pyz[:4] == b"PYZ\0"
out_pyz = bytearray(original_pyz[:16])
new_toc = []
for name, (kind, offset, length) in pyz.toc.items():
    blob = (zlib.compress(marshal.dumps(replace[name]), 6) if name in replace
            else original_pyz[offset:offset + length])
    new_toc.append((name, (kind, len(out_pyz), len(blob))))
    out_pyz.extend(blob)
for name,code in replace.items():
    if name not in pyz.toc:
        blob=zlib.compress(marshal.dumps(code),6)
        new_toc.append((name,(0,len(out_pyz),len(blob))));out_pyz.extend(blob)
struct.pack_into("!i", out_pyz, 8, len(out_pyz))
out_pyz.extend(marshal.dumps(new_toc))

# Preserve the original Windows bootloader and its other CArchive entries.
raw_exe = SOURCE.read_bytes()
assert reader._end_offset == len(raw_exe)
archive = bytearray()
entries = []
for name, (offset, stored, length, compressed, kind) in reader.toc.items():
    data = (bytes(out_pyz) if name == "PYZ.pyz"
            else raw_exe[reader._start_offset + offset:reader._start_offset + offset + stored])
    entries.append((len(archive), len(data), len(out_pyz) if name == "PYZ.pyz" else length, compressed, kind, name))
    archive.extend(data)
for option in reader.options:
    entries.append((len(archive), 0, 0, 0, "o", option))
toc_offset = len(archive)
serialized = CArchiveWriter._serialize_toc(entries)
archive.extend(serialized)
archive.extend(struct.pack(CArchiveWriter._COOKIE_FORMAT, CArchiveWriter._COOKIE_MAGIC_PATTERN,
    len(archive) + CArchiveWriter._COOKIE_LENGTH, toc_offset, len(serialized), 312,
    b"python312.dll"))
TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_bytes(raw_exe[:reader._start_offset] + archive)

verify = CArchiveReader(str(TARGET))
assert verify.toc.keys() == reader.toc.keys()
assert verify.options == reader.options
new = verify.open_embedded_archive("PYZ.pyz")
assert set(new.toc)==set(pyz.toc)|set(replace)
def same_code(a, b):
    if not isinstance(a, types.CodeType):return a == b
    return (isinstance(b, types.CodeType) and a.co_code == b.co_code and a.co_names == b.co_names
            and a.co_filename == b.co_filename and len(a.co_consts) == len(b.co_consts)
            and all(same_code(x, y) for x, y in zip(a.co_consts, b.co_consts)))
for name in replace:
    assert same_code(new.extract(name), replace[name]), name
print("Repacked", TARGET, TARGET.stat().st_size, "bytes; modules replaced:", len(replace))
