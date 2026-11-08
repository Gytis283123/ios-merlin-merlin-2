"""Patch 0086 generator: fbcon scrolls instead of wrapping."""
import io, os, shutil, subprocess, tarfile

repo = r'C:\Users\gycioc\Documents\I-hate-my-self-Ios.port\merlin2'
tmp = os.environ['TEMP'].replace('\\', '/')
work = tmp + '/p86'
shutil.rmtree(work, ignore_errors=True)
os.makedirs(work + '/a/pexpert/arm', exist_ok=True)
os.makedirs(work + '/b/pexpert/arm', exist_ok=True)

# pristine = fresh extract from the CI buildtree artifact
with tarfile.open(repo + r'\artifacts\buildtree\buildtree.tgz') as t:
    f = t.extractfile('xnu/pexpert/arm/pe_serial.c')
    data = f.read()
io.open(work + '/a/pexpert/arm/pe_serial.c', 'wb').write(data)
# edited = the in-place-modified buildtree copy
shutil.copy(repo + r'\artifacts\buildtree\xnu\pexpert\arm\pe_serial.c',
            work + '/b/pexpert/arm/pe_serial.c')

r = subprocess.run(['git', 'diff', '--no-index', '--src-prefix=a/', '--dst-prefix=b/',
                    work + '/a/pexpert/arm/pe_serial.c', work + '/b/pexpert/arm/pe_serial.c'],
                   capture_output=True, text=True)
assert r.returncode == 1, r.stdout + r.stderr
out = []
for ln in r.stdout.splitlines(True):
    if ln.startswith(('diff --git', 'index ')):
        continue
    if ln.startswith('--- '):
        ln = '--- a/pexpert/arm/pe_serial.c\n'
    elif ln.startswith('+++ '):
        ln = '+++ b/pexpert/arm/pe_serial.c\n'
    out.append(ln)
io.open(repo + r'\xnu\patches\0086-sweet-fbcon-scroll.patch',
        'w', encoding='utf-8', newline='').write(''.join(out))
print('patch 0086 written')
