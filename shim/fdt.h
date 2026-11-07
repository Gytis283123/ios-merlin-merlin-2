#pragma once
#include <stdint.h>

/* Read a u32/u64 (cell-size agnostic) property of /chosen. Returns 0 if absent. */
int fdt_chosen_u64(uintptr_t fdt, const char *prop, uint64_t *out);

/* Memory-map walker for the LK device tree: reports /memory ranges and
 * /reserved-memory children (base, size, no-map) as LK patched them at
 * boot. cb returns 1 to stop. Returns the number of reported entries. */
struct fdt_mem_ent {
	uint64_t base, size;
	const char *kind;	/* "mem" or "reserved" */
	const char *name;	/* node name (not NUL-terminated!) */
	int name_len;
	int nomap;
};
int fdt_walk_mem(uintptr_t fdt,
		 int (*cb)(const struct fdt_mem_ent *, void *ctx), void *ctx);
