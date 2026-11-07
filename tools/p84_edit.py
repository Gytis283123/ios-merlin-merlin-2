"""Patch 0084 generator: trace every STARTUP hook in kernel_startup_initialize_upto."""
import io, os, shutil, subprocess

tmp = os.environ['TEMP'].replace('\\', '/')
work = tmp + '/p84'
tree = r'C:\Users\gycioc\Documents\I-hate-my-self-Ios.port\merlin2\artifacts\buildtree\xnu'
shutil.rmtree(work, ignore_errors=True)
os.makedirs(work + '/a/osfmk/kern', exist_ok=True)
os.makedirs(work + '/b/osfmk/kern', exist_ok=True)
shutil.copy(tree + '/osfmk/kern/startup.c', work + '/a/osfmk/kern/startup.c')

s = io.open(work + '/a/osfmk/kern/startup.c', encoding='utf-8', newline='').read()

old = """	while (cur < startup_entries_end && cur->subsystem <= upto) {
		if ((startup_debug & STARTUP_DEBUG_VERBOSE) &&
		    startup_phase >= STARTUP_SUB_KPRINTF) {
			kprintf("%s[%d, rank %d]: %p(%p)\\n", __func__,
			    cur->subsystem, cur->rank, cur->func, cur->arg);
		}
		startup_phase = cur->subsystem - 1;
		kernel_startup_log(cur->subsystem);
		cur->func(cur->arg);
		startup_entry_cur = ++cur;
	}"""
assert s.count(old) == 1, "hook loop anchor"
new = """	while (cur < startup_entries_end && cur->subsystem <= upto) {
		if ((startup_debug & STARTUP_DEBUG_VERBOSE) &&
		    startup_phase >= STARTUP_SUB_KPRINTF) {
			kprintf("%s[%d, rank %d]: %p(%p)\\n", __func__,
			    cur->subsystem, cur->rank, cur->func, cur->arg);
		}
#if SWEET
		/* patch 0084: name every startup hook - the merlin boot went
		 * silent inside this chain (last console output: "VM bootstrap
		 * done", a STARTUP_SUB_ZALLOC hook). func addresses
		 * symbolicate against the link image. printf is safe here:
		 * the early fbcon console is already up. */
		if (cur->subsystem >= STARTUP_SUB_LOCKS) {
			printf("SWEET STARTUP: [%d r%d] %p\\n",
			    cur->subsystem, cur->rank, cur->func);
		}
#endif
		startup_phase = cur->subsystem - 1;
		kernel_startup_log(cur->subsystem);
		cur->func(cur->arg);
		startup_entry_cur = ++cur;
	}"""
s = s.replace(old, new)

old2 = """	kernel_startup_log(upto);

	if ((startup_debug & STARTUP_DEBUG_VERBOSE) &&
	    upto >= STARTUP_SUB_KPRINTF) {
		kprintf("%s: reached phase %d\\n", __func__, upto);
	}
	startup_phase = upto;
}"""
assert s.count(old2) == 1, "upto tail anchor"
new2 = """	kernel_startup_log(upto);

#if SWEET
	printf("SWEET STARTUP: reached phase %d\\n", upto);
#endif
	if ((startup_debug & STARTUP_DEBUG_VERBOSE) &&
	    upto >= STARTUP_SUB_KPRINTF) {
		kprintf("%s: reached phase %d\\n", __func__, upto);
	}
	startup_phase = upto;
}"""
s = s.replace(old2, new2)

io.open(work + '/b/osfmk/kern/startup.c', 'w', encoding='utf-8', newline='').write(s)

r = subprocess.run(['git', 'diff', '--no-index', '--src-prefix=a/', '--dst-prefix=b/',
                    work + '/a/osfmk/kern/startup.c', work + '/b/osfmk/kern/startup.c'],
                   capture_output=True, text=True)
assert r.returncode == 1, r.stdout + r.stderr
out = []
for ln in r.stdout.splitlines(True):
    if ln.startswith(('diff --git', 'index ')):
        continue
    if ln.startswith('--- '):
        ln = '--- a/osfmk/kern/startup.c\n'
    elif ln.startswith('+++ '):
        ln = '+++ b/osfmk/kern/startup.c\n'
    out.append(ln)
io.open(r'C:\Users\gycioc\Documents\I-hate-my-self-Ios.port\merlin2\xnu\patches\0084-sweet-startup-trace.patch',
        'w', encoding='utf-8', newline='').write(''.join(out))
print('patch written')
