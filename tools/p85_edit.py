"""Patch 0085 generator (careful): mark SUBSYSTEM transitions only in
kernel_startup_initialize_upto - ~12 lines over the whole boot, nothing else."""
import io, os, shutil, subprocess

tmp = os.environ['TEMP'].replace('\\', '/')
work = tmp + '/p85'
tree = r'C:\Users\gycioc\Documents\I-hate-my-self-Ios.port\merlin2\artifacts\buildtree\xnu'
shutil.rmtree(work, ignore_errors=True)
os.makedirs(work + '/a/osfmk/kern', exist_ok=True)
os.makedirs(work + '/b/osfmk/kern', exist_ok=True)
shutil.copy(tree + '/osfmk/kern/startup.c', work + '/a/osfmk/kern/startup.c')

s = io.open(work + '/a/osfmk/kern/startup.c', encoding='utf-8', newline='').read()

old = """	struct startup_entry *cur = startup_entry_cur;

	assert(startup_phase < upto);

	while (cur < startup_entries_end && cur->subsystem <= upto) {
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

new = """	struct startup_entry *cur = startup_entry_cur;
#if SWEET
	/* patch 0085 (careful): one line per SUBSYSTEM transition, nothing
	 * else - the merlin boot goes silent after the ZALLOC-era hooks
	 * ("VM bootstrap done" is its last output). ~12 lines total; printf
	 * is proven working at this stage ("VM bootstrap done" is printf). */
	startup_subsystem_id_t sweet_last_sub = STARTUP_SUB_NONE;
#endif

	assert(startup_phase < upto);

	while (cur < startup_entries_end && cur->subsystem <= upto) {
		if ((startup_debug & STARTUP_DEBUG_VERBOSE) &&
		    startup_phase >= STARTUP_SUB_KPRINTF) {
			kprintf("%s[%d, rank %d]: %p(%p)\\n", __func__,
			    cur->subsystem, cur->rank, cur->func, cur->arg);
		}
#if SWEET
		if (cur->subsystem != sweet_last_sub &&
		    cur->subsystem >= STARTUP_SUB_KMEM) {
			printf("SWEET SUBSYS: entering %d (hook %p)\\n",
			    cur->subsystem, cur->func);
		}
		sweet_last_sub = cur->subsystem;
#endif
		startup_phase = cur->subsystem - 1;
		kernel_startup_log(cur->subsystem);
		cur->func(cur->arg);
		startup_entry_cur = ++cur;
	}"""
s = s.replace(old, new)

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
io.open(r'C:\Users\gycioc\Documents\I-hate-my-self-Ios.port\merlin2\xnu\patches\0085-sweet-subsys-trace.patch',
        'w', encoding='utf-8', newline='').write(''.join(out))
print('patch 0085 written')
