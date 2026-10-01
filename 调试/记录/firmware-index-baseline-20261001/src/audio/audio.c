#include "app.h"
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static const char *const sounds[] = {
    "capture_done", "uploaded", "saved_on_device", "storage_low", "capture_failed",
    "please_connect", "pair_success", "pair_failed", "wifi_connected",
    "wifi_disconnected", "pair_disconnected"
};
static time_t last_played[sizeof(sounds) / sizeof(sounds[0])];

void audio_set_volume(int volume) {
    char number[16];
    snprintf(number, sizeof(number), "%d", volume);
    char *const args[] = {"amixer", "-c", "0", "cset", "name=DAC LINEOUT Volume", number, NULL};
    (void)run_command(args);
}

int audio_play(const char *name) {
    size_t index;
    for (index = 0; index < sizeof(sounds) / sizeof(sounds[0]); index++)
        if (!strcmp(name, sounds[index])) break;
    if (index == sizeof(sounds) / sizeof(sounds[0])) return -1;
    struct timespec clock_time;
    if (clock_gettime(CLOCK_MONOTONIC, &clock_time)) return -1;
    time_t now = clock_time.tv_sec;
    if (last_played[index] && now - last_played[index] < 30) return 0;
    char path[192];
    int n = snprintf(path, sizeof(path), "%s/%s.wav", SOUND_DIR, name);
    if (n < 0 || (size_t)n >= sizeof(path)) return -1;
    if (access(path, R_OK)) {
        n = snprintf(path, sizeof(path), "%s/%s.wav", LEGACY_SOUND_DIR, name);
        if (n < 0 || (size_t)n >= sizeof(path) || access(path, R_OK)) return -1;
    }
    char *const args[] = {"aplay", "-q", "-D", "plughw:0,0", path, NULL};
    int result = run_command(args);
    if (!result) last_played[index] = now;
    return result;
}
