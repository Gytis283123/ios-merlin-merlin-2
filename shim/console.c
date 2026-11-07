/*
 * Minimal text console on the ABL splash framebuffer. With the MMU off
 * every access is Device memory, so stay aligned (-mstrict-align).
 */
#include "console.h"
#include "font.h"


#define MARGIN		24
#define LABEL_COLS	8

volatile uint32_t *con_fb = (volatile uint32_t *)FB_BASE;
uint32_t con_w = FB_W, con_h = FB_H, con_stride = FB_STRIDE;
uint32_t con_scale = 3;
volatile uint32_t *con_l1 = 0;
uint32_t con_split = 0xFFFFFFFF;
static uint32_t con_bg;
static int row;

/* pixel pointer for console row y, column x (two OVL layers) */
static volatile uint32_t *px(uint32_t y, uint32_t x)
{
	if (y >= con_split && con_l1)
		return con_l1 + (y - con_split) * (con_stride / 4) + x;
	return con_fb + y * (con_stride / 4) + x;
}

void con_init(uint64_t base, uint32_t w, uint32_t h, uint32_t stride)
{
	con_init2(base, 0, w, h, stride, 0xFFFFFFFF);
}

void con_init2(uint64_t base, uint64_t base1, uint32_t w, uint32_t h,
	       uint32_t stride, uint32_t split)
{
	con_fb = (volatile uint32_t *)base;
	con_l1 = base1 ? (volatile uint32_t *)base1 : 0;
	con_split = base1 ? split : 0xFFFFFFFF;
	con_w = w;
	con_h = h;
	con_stride = stride;
}

void con_clear(uint32_t bg)
{
	for (uint32_t y = 0; y < con_h; y++) {
		volatile uint32_t *line = px(y, 0);
		for (uint32_t x = 0; x < con_w; x++)
			line[x] = bg;
	}
	con_bg = bg;
	row = 0;
}

static void put_char(int col, char ch, uint32_t fg)
{
	if (ch < 0x20 || ch > 0x7e)
		ch = '?';
	const unsigned char *g = font8x16[ch - 0x20];
	int ch_w = 8 * con_scale, ch_h = 16 * con_scale;
	int x0 = MARGIN + col * ch_w, y0 = MARGIN + row * ch_h;
	if (x0 + ch_w > (int)con_w || y0 + ch_h > (int)con_h)
		return;
	for (int gy = 0; gy < 16; gy++)
		for (int gx = 0; gx < 8; gx++) {
			uint32_t c = (g[gy] & (0x80 >> gx)) ? fg : con_bg;
			for (int sy = 0; sy < SCALE; sy++) {
				volatile uint32_t *p = con_fb + (y0 + gy * SCALE + sy) * (con_stride / 4)
						       + x0 + gx * SCALE;
				for (int sx = 0; sx < SCALE; sx++)
					p[sx] = c;
			}
		}
}

static int put_str(int col, const char *s, uint32_t fg)
{
	while (*s)
		put_char(col++, *s++, fg);
	return col;
}

static void fmt_hex(char *buf, uint64_t v, int digits)
{
	static const char hex[] = "0123456789ABCDEF";
	for (int i = 0; i < digits; i++)
		buf[i] = hex[(v >> (4 * (digits - 1 - i))) & 0xf];
	buf[digits] = 0;
}

void con_skip(void)
{
	row++;
}

void con_str(const char *label, const char *s)
{
	put_str(0, label, YELLOW);
	put_str(LABEL_COLS, s, WHITE);
	row++;
}

void con_hex(const char *label, uint64_t v)
{
	char buf[17];
	fmt_hex(buf, v, 16);
	con_str(label, buf);
}

void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb)
{
	char buf[9];
	int col = put_str(0, label, YELLOW);
	col = col < LABEL_COLS ? LABEL_COLS : col + 1;
	col = put_str(col, a, YELLOW);
	fmt_hex(buf, va, 8);
	col = put_str(col, buf, WHITE);
	if (b) {
		col = put_str(col + 1, b, YELLOW);
		fmt_hex(buf, vb, 8);
		put_str(col, buf, WHITE);
	}
	row++;
}
