"""Create matching source from the frozen Git revision plus recorder recovery input."""
import hashlib, json, os, subprocess, zipfile
from pathlib import Path

out=Path('integration/output'); out.mkdir(exist_ok=True)
target=out/'VoidEye-VLabVoice-0.40-Recovery-Source.zip'
revision=os.environ.get('SOURCE_REVISION') or subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
subprocess.run(['git','archive','--format=zip','--output='+str(target),revision,'vlab-voice','integration','.github/workflows/package-void-eye-voice-040.yml'],check=True)
with zipfile.ZipFile(target,'a',zipfile.ZIP_DEFLATED) as z:
    recovery=Path('integration/restore/VoidEye-PC-0.39')
    for p in sorted(recovery.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and 'pc-update' not in p.parts:
            z.write(p,'recovery/VoidEye-PC-0.39/'+p.relative_to(recovery).as_posix())
    z.write('integration/models/faster-whisper-small/MODEL-SHA256.json','MODEL-SHA256.json')
    hashes={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith('/')}
    setup=next(out.glob('*Setup.exe'))
    manifest=dict(version='0.40.0',source_revision=revision,installer=setup.name,
        installer_sha256=hashlib.file_digest(setup.open('rb'),'sha256').hexdigest(),files=hashes,
        source_type='recovery reconstruction; full original recorder source unavailable')
    z.writestr('SOURCE-MANIFEST.json',json.dumps(manifest,indent=2))
print('SOURCE_PACKAGE_PASS',target,target.stat().st_size)
