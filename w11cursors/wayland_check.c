/*
 * Load cursors through libwayland-cursor, the loader GTK, Qt, Chromium,
 * Firefox and most compositors use on Wayland.  It has its own XCursor parser,
 * so passing libXcursor alone does not prove the theme works there.
 *
 * usage: wayland_check THEME SIZE [SIZE...] < names.txt
 * prints one line per (size, name):  <size> <name> <frames> <w> <h> <xhot> <yhot>
 * or "<size> <name> MISSING".  Connects to $WAYLAND_DISPLAY only to obtain a
 * wl_shm global; it never creates a surface or touches the pointer.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>
#include <wayland-cursor.h>

static struct wl_shm *shm;

static void on_global(void *data, struct wl_registry *reg, uint32_t id,
                      const char *iface, uint32_t version)
{
    (void)data; (void)version;
    if (!strcmp(iface, "wl_shm"))
        shm = wl_registry_bind(reg, id, &wl_shm_interface, 1);
}

static void on_remove(void *data, struct wl_registry *reg, uint32_t id)
{
    (void)data; (void)reg; (void)id;
}

static const struct wl_registry_listener listener = { on_global, on_remove };

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s THEME SIZE...\n", argv[0]);
        return 64;
    }
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) {
        puts("SKIP no wayland display");
        return 2;
    }
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &listener, NULL);
    wl_display_roundtrip(display);
    if (!shm) {
        puts("SKIP compositor has no wl_shm");
        return 2;
    }

    char **names = NULL;
    size_t count = 0, cap = 0;
    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!*line)
            continue;
        if (count == cap) {
            cap = cap ? cap * 2 : 128;
            names = realloc(names, cap * sizeof *names);
        }
        names[count++] = strdup(line);
    }

    int status = 0;
    for (int a = 2; a < argc; a++) {
        int size = atoi(argv[a]);
        struct wl_cursor_theme *theme = wl_cursor_theme_load(argv[1], size, shm);
        if (!theme) {
            printf("%d THEME-LOAD-FAILED\n", size);
            status = 1;
            continue;
        }
        for (size_t i = 0; i < count; i++) {
            struct wl_cursor *cursor = wl_cursor_theme_get_cursor(theme, names[i]);
            if (!cursor || cursor->image_count == 0) {
                printf("%d %s MISSING\n", size, names[i]);
                status = 1;
                continue;
            }
            struct wl_cursor_image *im = cursor->images[0];
            printf("%d %s %u %u %u %u %u\n", size, names[i], cursor->image_count,
                   im->width, im->height, im->hotspot_x, im->hotspot_y);
        }
        wl_cursor_theme_destroy(theme);
    }
    wl_display_disconnect(display);
    return status;
}
