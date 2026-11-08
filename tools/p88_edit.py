"""Patch 0088 generator: pe_init_fiq GICR/CPU-interface readback + vtimer
pending (tick) probe — diagnoses why timer callouts never fire on merlin."""
import os, shutil, subprocess, tarfile

repo = r'C:\Users\gycioc\Documents\I-hate-my-self-Ios.port\merlin2'
tmp = os.environ['TEMP'].replace('\\', '/')
work = tmp + '/p88'
shutil.rmtree(work, ignore_errors=True)
os.makedirs(work + '/a/pexpert/arm', exist_ok=True)
os.makedirs(work + '/b/pexpert/arm', exist_ok=True)

with tarfile.open(repo + r'\artifacts\buildtree\buildtree.tgz') as t:
    data = t.extractfile('xnu/pexpert/arm/pe_fiq.c').read()
io_open = open
io_open(work + '/a/pexpert/arm/pe_fiq.c', 'wb').write(data)
shutil.copy(repo + r'\artifacts\buildtree\xnu\pexpert\arm\pe_fiq.c',
            work + '/b/pexpert/arm/pe_fiq.c')

r = subprocess.run(['git', 'diff', '--no-index', '--src-prefix=a/', '--dst-prefix=b/',
                    work + '/a/pexpert/arm/pe_fiq.c', work + '/b/pexpert/arm/pe_fiq.c'],
                   capture_output=True, text=True)
assert r.returncode == 1, r.stdout + r.stderr
out = []
for ln in r.stdout.splitlines(True):
    if ln.startswith(('diff --git', 'index ')):
        continue
    if ln.startswith('--- '):
        ln = '--- a/pexpert/arm/pe_fiq.c\n'
    elif ln.startswith('+++ '):
        ln = '+++ b/pexpert/arm/pe_fiq.c\n'
    out.append(ln)
io_open(repo + r'\xnu\patches\0088-merlin-gic-boot-probe.patch',
        'w', encoding='utf-8', newline='').write(''.join(out))
print('patch 0088 written')

# Verify it applies to the pristine tree.
chk = subprocess.run(['git', 'apply', '--check', '-p2', repo + r'\xnu\patches\0088-merlin-gic-boot-probe.patch'],
                     cwd=work + '/a', capture_output=True, text=True)
if chk.returncode != 0:
    # git apply --check needs a repo context for -p2; retry with --unsafe-paths in temp dir
    chk2 = subprocess.run(['git', 'apply', '--check', repo + r'\xnu\patches\0088-merlin-gic-boot-probe.patch'],
                          cwd=work + '/a', capture_output=True, text=True)
    print('apply-check rc', chk.returncode, chk.stderr or 'ok(-p2)')
    print('apply-check2 rc', chk2.returncode, chk2.stderr or 'ok')
else:
    print('apply-check rc 0 (ok)')
