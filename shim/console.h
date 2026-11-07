#pragma once
#include <stdint.h>

#define FB_BASE		0x9c000000UL	/* reserved-memory cont_splash_region */
#define FB_W		1080
#define FB_H		2400
#define FB_STRIDE	(FB_W * 4)	/* a8r8g8b8, matches mainline simplefb */

#define RED	0xffff0000U
#define BLUE	0xff0000a0U
#define WHITE	0xffffffffU
#define YELLOW	0xffffff00U
#define GREEN	0xff00ff00U
#define MAGENTA	0xffff00ffU

extern volatile uint32_t *con_fb;
/* Runtime console geometry; defaults are the sweet framebuffer until
 * con_init() replaces them (merlin gets its values from the live display
 * registers). MTK splits tall panels across OVL layers: rows below
 * con_split draw from con_l1 (a separate buffer), pitch in PIXELS. */
extern uint32_t con_w, con_h, con_stride;
extern uint32_t con_scale;
extern volatile uint32_t *con_l1;
extern uint32_t con_split;
void con_init(uint64_t base, uint32_t w, uint32_t h, uint32_t stride_px);
void con_init2(uint64_t base, uint64_t base1, uint32_t w, uint32_t h,
	       uint32_t stride_px, uint32_t split);

void con_clear(uint32_t bg);
void con_skip(void);
void con_str(const char *label, const char *s);
void con_hex(const char *label, uint64_t v);
/* label, then "a=xxxxxxxx b=xxxxxxxx" style pairs of 32-bit values */
void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb);
