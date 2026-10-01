#include "app.h"
#include "config.h"
#include "cJSON.h"
#include <ctype.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int string_field(const cJSON *obj, const char *key, char *out, size_t size) {
    const cJSON *value = cJSON_GetObjectItemCaseSensitive(obj, key);
    if (!cJSON_IsString(value) || !value->valuestring ||
        strlen(value->valuestring) >= size || !value->valuestring[0]) return -1;
    strcpy(out, value->valuestring);
    return 0;
}

static int number_field(const cJSON *obj, const char *key, int *out) {
    const cJSON *value = cJSON_GetObjectItemCaseSensitive(obj, key);
    if (!cJSON_IsNumber(value)) return -1;
    *out = value->valueint;
    return 0;
}

int config_load(const char *path, Config *config) {
    if (path && config) {
        snprintf(config->config_path, sizeof(config->config_path), "%s", path);
    }
    FILE *file = fopen(path, "rb");
    if (!file) return -1;
    char text[8192];
    size_t len = fread(text, 1, sizeof(text) - 1, file);
    int too_large = !feof(file);
    fclose(file);
    if (too_large) return -1;
    text[len] = 0;
    cJSON *root = cJSON_Parse(text);
    if (!root) return -1;
    const cJSON *audio = cJSON_GetObjectItemCaseSensitive(root, "audio");
    const cJSON *capture = cJSON_GetObjectItemCaseSensitive(root, "capture");
    const cJSON *battery = cJSON_GetObjectItemCaseSensitive(root, "battery");
    char fps_fraction[16], codec[16], container[16];
    int ok = cJSON_IsObject(root) && cJSON_IsObject(audio) &&
        cJSON_IsObject(capture) && cJSON_IsObject(battery) &&
        string_field(root, "device_id", config->device_id, sizeof(config->device_id)) == 0 &&
        string_field(root, "wifi_ssid", config->wifi_ssid, sizeof(config->wifi_ssid)) == 0 &&
        string_field(root, "pc_base_url", config->pc_base_url, sizeof(config->pc_base_url)) == 0 &&
        number_field(audio, "volume", &config->volume) == 0 &&
        number_field(capture, "width", &config->width) == 0 &&
        number_field(capture, "height", &config->height) == 0 &&
        string_field(capture, "fps_fraction", fps_fraction, sizeof(fps_fraction)) == 0 &&
        string_field(capture, "codec", codec, sizeof(codec)) == 0 &&
        string_field(capture, "container", container, sizeof(container)) == 0 &&
        number_field(capture, "bitrate_kbps", &config->bitrate_kbps) == 0 &&
        number_field(capture, "duration_ms", &config->duration_ms) == 0 &&
        cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(battery, "present"));
    cJSON_Delete(root);
    if (!ok) return -1;
    if (strncmp(config->pc_base_url, "http://", 7) ||
        strchr(config->pc_base_url + 7, '/') ||
        strcmp(fps_fraction, "60/2") || strcmp(codec, "h265") ||
        strcmp(container, "mp4") || config->width != 1280 ||
        config->height != 1080 || config->bitrate_kbps != 4000 ||
        config->duration_ms != 10000 || config->volume < 0 || config->volume > 100)
        return -1;
    for (const char *p = config->device_id; *p; p++)
        if (!isalnum((unsigned char)*p) && *p != '-') return -1;
    config->fps = 30;
    config->gop = 30;
    return 0;
}

int config_save_volume(const char *path, int volume) {
    if (!path || volume < 0 || volume > 30) return -1;
    FILE *file = fopen(path, "rb");
    if (!file) return -1;
    char text[8192];
    size_t len = fread(text, 1, sizeof(text) - 1, file);
    int too_large = !feof(file);
    fclose(file);
    if (too_large) return -1;
    text[len] = 0;

    cJSON *root = cJSON_Parse(text);
    if (!root) return -1;

    cJSON *audio = cJSON_GetObjectItemCaseSensitive(root, "audio");
    if (!audio) {
        audio = cJSON_CreateObject();
        if (!audio) {
            cJSON_Delete(root);
            return -1;
        }
        cJSON_AddItemToObject(root, "audio", audio);
    }

    if (cJSON_GetObjectItemCaseSensitive(audio, "volume")) {
        cJSON_ReplaceItemInObject(audio, "volume", cJSON_CreateNumber(volume));
    } else {
        cJSON_AddNumberToObject(audio, "volume", volume);
    }

    char *new_text = cJSON_Print(root);
    cJSON_Delete(root);
    if (!new_text) return -1;

    char tmp_path[512];
    int n = snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", path);
    if (n < 0 || (size_t)n >= sizeof(tmp_path)) {
        cJSON_free(new_text);
        return -1;
    }

    FILE *out = fopen(tmp_path, "wb");
    if (!out) {
        cJSON_free(new_text);
        return -1;
    }

    size_t out_len = strlen(new_text);
    int ok = fwrite(new_text, 1, out_len, out) == out_len &&
             fwrite("\n", 1, 1, out) == 1 &&
             fflush(out) == 0 &&
             fsync(fileno(out)) == 0;
    if (fclose(out) != 0) ok = 0;
    cJSON_free(new_text);

    if (!ok) {
        unlink(tmp_path);
        return -1;
    }

    if (rename(tmp_path, path) != 0) {
        unlink(tmp_path);
        return -1;
    }

    const char *last_slash = strrchr(path, '/');
    if (last_slash) {
        char dir_buf[512];
        size_t dirlen = (size_t)(last_slash - path);
        if (dirlen == 0) dirlen = 1;
        if (dirlen < sizeof(dir_buf)) {
            memcpy(dir_buf, path, dirlen);
            dir_buf[dirlen] = 0;
            int dfd = open(dir_buf, O_RDONLY | O_DIRECTORY);
            if (dfd >= 0) {
                (void)fsync(dfd);
                close(dfd);
            }
        }
    }

    return 0;
}
