/*
 * Just enough flattened-device-tree parsing to find what ABL put in
 * /chosen (initrd location). Big-endian, 4-byte aligned tokens.
 */
#include "fdt.h"

#define FDT_MAGIC	0xd00dfeed
#define FDT_BEGIN_NODE	1
#define FDT_END_NODE	2
#define FDT_PROP	3
#define FDT_NOP		4
#define FDT_END		9

static uint32_t be32(uintptr_t a)
{
	return __builtin_bswap32(*(volatile uint32_t *)a);
}

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static uintptr_t align4(uintptr_t a)
{
	return (a + 3) & ~3UL;
}

static uintptr_t skip_str(uintptr_t p)
{
	/* byte loads are fine on Device memory as long as they are aligned to 1 */
	while (*(volatile char *)p)
		p++;
	return p + 1;
}

int fdt_chosen_u64(uintptr_t fdt, const char *prop, uint64_t *out)
{
	if (!fdt || be32(fdt) != FDT_MAGIC)
		return 0;
	uintptr_t p = fdt + be32(fdt + 8);		/* off_dt_struct */
	uintptr_t strings = fdt + be32(fdt + 12);	/* off_dt_strings */
	int depth = 0, in_chosen = 0;

	for (;;) {
		uint32_t tok = be32(p);
		p += 4;
		switch (tok) {
		case FDT_BEGIN_NODE: {
			const char *name = (const char *)p;
			depth++;
			in_chosen = depth == 2 && streq(name, "chosen");
			p = align4(skip_str(p));
			break;
		}
		case FDT_END_NODE:
			if (in_chosen)
				return 0;
			depth--;
			break;
		case FDT_PROP: {
			uint32_t len = be32(p), nameoff = be32(p + 4);
			uintptr_t val = p + 8;
			if (in_chosen && streq((const char *)(strings + nameoff), prop)) {
				if (len == 4)
					*out = be32(val);
				else if (len == 8)
					*out = (uint64_t)be32(val) << 32 | be32(val + 4);
				else
					return 0;
				return 1;
			}
			p = align4(val + len);
			break;
		}
		case FDT_NOP:
			break;
		default:	/* FDT_END or garbage */
			return 0;
		}
	}
}

/* ---- memory map walker ---- */

struct walk_state {
	int (*cb)(const struct fdt_mem_ent *, void *ctx);
	void *ctx;
	int count;
	int addr_cells, size_cells;
	char n1[40], n2[40];
	int n1_len, n2_len;
};

static int name_is(const char *nm, int len, const char *want)
{
	int w = 0;
	while (want[w])
		w++;
	if (len != w)
		return 0;
	for (int i = 0; i < len; i++)
		if (nm[i] != want[i])
			return 0;
	return 1;
}

static int emit_range(struct walk_state *w, const char *kind, const char *name,
		      int name_len, uint64_t base, uint64_t size, int nomap)
{
	struct fdt_mem_ent e;
	e.base = base;
	e.size = size;
	e.kind = kind;
	e.name = name;
	e.name_len = name_len;
	e.nomap = nomap;
	w->count++;
	return w->cb(&e, w->ctx);
}

int fdt_walk_mem(uintptr_t fdt,
		 int (*cb)(const struct fdt_mem_ent *, void *ctx), void *ctx)
{
	if (!fdt || be32(fdt) != FDT_MAGIC)
		return 0;
	struct walk_state w = { .cb = cb, .ctx = ctx, .addr_cells = 2, .size_cells = 2 };
	uintptr_t p = fdt + be32(fdt + 8);		/* off_dt_struct */
	uintptr_t strings = fdt + be32(fdt + 12);	/* off_dt_strings */
	int depth = 0;
	int collecting = 0;	/* 1: /memory, 2: /reserved-memory child */
	int nomap = 0;

	for (;;) {
		uint32_t tok = be32(p);
		p += 4;
		if (tok == FDT_END || tok == 0)
			break;
		if (tok == FDT_NOP)
			continue;
		if (tok == FDT_BEGIN_NODE) {
			const char *nm = (const char *)p;
			p = align4(skip_str(p));
			depth++;
			int len = 0;
			while (nm[len] && len < 38)
				len++;
			if (depth == 1) {
				for (int i = 0; i < len; i++) w.n1[i] = nm[i];
				w.n1_len = len;
				w.n2_len = 0;
			} else if (depth == 2) {
				for (int i = 0; i < len; i++) w.n2[i] = nm[i];
				w.n2_len = len;
			}
			collecting = 0;
			nomap = 0;
			if (depth == 1 && name_is(nm, len, "memory"))
				collecting = 1;
			else if (depth == 2 && name_is(w.n1, w.n1_len, "reserved-memory"))
				collecting = 2;
			continue;
		}
		if (tok == FDT_END_NODE) {
			(void)collecting;
			depth--;
			if (depth < 0)
				depth = 0;
			collecting = (depth == 1 && name_is(w.n1, w.n1_len, "memory")) ? 1
				: (depth == 2 && name_is(w.n1, w.n1_len, "reserved-memory")) ? 2 : 0;
			continue;
		}
		if (tok == FDT_PROP) {
			uint32_t plen = be32(p), nameoff = be32(p + 4);
			uintptr_t val = p + 8;
			const char *pn = (const char *)(strings + nameoff);
			p = align4(val + plen);
			if (!collecting)
				continue;
			if (name_is(pn, -1, "no-map")) {
				nomap = 1;
				continue;
			}
			if (depth == 1 && w.n1_len >= 1 && w.n1[0] == '#' )
				continue;	/* #address-cells etc. */
			if (name_is(pn, -1, "#address-cells") && plen == 4 && depth == 1
			    && name_is(w.n1, w.n1_len, "reserved-memory")) {
				w.addr_cells = (int)be32(val);
				continue;
			}
			if (name_is(pn, -1, "#size-cells") && plen == 4 && depth == 1
			    && name_is(w.n1, w.n1_len, "reserved-memory")) {
				w.size_cells = (int)be32(val);
				continue;
			}
			if (!name_is(pn, -1, "reg") && !name_is(pn, -1, "size"))
				continue;
			uint32_t cellbytes = (uint32_t)(w.addr_cells + w.size_cells) * 4;
			if (name_is(pn, -1, "size")) {
				/* reserved child with only a size: dynamic allocation */
				uint64_t sz = 0;
				for (uint32_t i = 0; i < plen && i < 8; i++)
					sz = (sz << 8) | ((const unsigned char *)val)[i];
				emit_range(&w, "reserved", w.n2, w.n2_len, 0, sz, nomap);
				continue;
			}
			uintptr_t q = val;
			uint32_t left = plen;
			while (left >= cellbytes && w.count < 24) {
				uint64_t base = 0, size = 0;
				for (int i = 0; i < w.addr_cells; i++)
					base = (base << 32) | be32(q + i * 4);
				for (int i = 0; i < w.size_cells; i++)
					size = (size << 32) | be32(q + (w.addr_cells + i) * 4);
				q += cellbytes;
				left -= cellbytes;
				if (emit_range(&w, collecting == 1 ? "mem" : "reserved",
					       collecting == 1 ? w.n1 : w.n2,
					       collecting == 1 ? w.n1_len : w.n2_len,
					       base, size, nomap) == 1)
					return w.count;
			}
			continue;
		}
	}
	return w.count;
}
