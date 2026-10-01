#include "app.h"
#include "cJSON.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

static int ensure_dir(const char *path) {
    if (!mkdir(path, 0755) || errno == EEXIST) return 0;
    return -1;
}

static int copy_file(const char *from, const char *to) {
    FILE *in = fopen(from, "rb");
    if (!in) return -1;
    FILE *out = fopen(to, "wb");
    if (!out) { fclose(in); return -1; }
    char buffer[8192];
    size_t count;
    int ok = 1;
    while ((count = fread(buffer, 1, sizeof(buffer), in)) > 0) {
        if (fwrite(buffer, 1, count, out) != count) { ok = 0; break; }
    }
    if (ferror(in)) ok = 0;
    if (fclose(out)) ok = 0;
    fclose(in);
    return ok ? 0 : -1;
}

static void migrate_tree(const char *from_dir, const char *to_dir) {
    DIR *dir = opendir(from_dir);
    if (!dir) return;
    struct dirent *entry;
    while ((entry = readdir(dir))) {
        size_t len = strlen(entry->d_name);
        int wav = len > 4 && !strcmp(entry->d_name + len - 4, ".wav");
        int media = wav || (len > 4 && !strcmp(entry->d_name + len - 4, ".mp4")) ||
                    (len > 5 && !strcmp(entry->d_name + len - 5, ".json"));
        if (!media) continue;
        char from[512], to[512];
        int n = snprintf(from, sizeof(from), "%s/%s", from_dir, entry->d_name);
        int m = snprintf(to, sizeof(to), "%s/%s", to_dir, entry->d_name);
        if (n < 0 || m < 0 || (size_t)n >= sizeof(from) || (size_t)m >= sizeof(to)) continue;
        if (!access(to, F_OK)) continue;
        if (rename(from, to)) (void)copy_file(from, to);
    }
    closedir(dir);
}

int storage_prepare(void) {
    if (ensure_dir(INSTRUMENT_ROOT) || ensure_dir(INSTRUMENT_ROOT "/bin") ||
        ensure_dir(STATE_DIR) || ensure_dir(SOUND_DIR) ||
        ensure_dir(INSTRUMENT_ROOT "/capture") || ensure_dir(WRITING_DIR) ||
        ensure_dir(PENDING_DIR)) return -1;
    migrate_tree(LEGACY_SOUND_DIR, SOUND_DIR);
    migrate_tree(LEGACY_PENDING_DIR, PENDING_DIR);
    return 0;
}

long storage_free_mb(void) {
    struct statvfs info;
    if (statvfs(PENDING_DIR, &info)) return -1;
    return (long)((unsigned long long)info.f_bavail * info.f_frsize / (1024 * 1024));
}

long storage_total_mb(void) {
    struct statvfs info;
    if (statvfs(PENDING_DIR, &info)) return -1;
    return (long)((unsigned long long)info.f_blocks * info.f_frsize / (1024 * 1024));
}

int storage_memory_mb(long *available, long *total) {
    FILE *file = fopen("/proc/meminfo", "r");
    if (!file) return -1;
    char line[128];
    long free_kb = -1, total_kb = -1;
    while (fgets(line, sizeof(line), file)) {
        (void)sscanf(line, "MemAvailable: %ld kB", &free_kb);
        (void)sscanf(line, "MemTotal: %ld kB", &total_kb);
    }
    fclose(file);
    if (free_kb < 0 || total_kb <= 0) return -1;
    *available = free_kb / 1024;
    *total = total_kb / 1024;
    return 0;
}

int storage_pending_count(void) {
    DIR *dir = opendir(PENDING_DIR);
    if (!dir) return -1;
    int count = 0;
    struct dirent *entry;
    while ((entry = readdir(dir))) {
        size_t len = strlen(entry->d_name);
        if (len > 4 && !strcmp(entry->d_name + len - 4, ".mp4")) count++;
    }
    closedir(dir);
    return count;
}

int storage_capture_id(const Config *config, char *out, size_t size) {
    unsigned char random[4];
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0) return -1;
    ssize_t count = read(fd, random, sizeof(random));
    close(fd);
    if (count != (ssize_t)sizeof(random)) return -1;
    int written = snprintf(out, size, "%s-%02x%02x%02x%02x", config->device_id,
                           random[0], random[1], random[2], random[3]);
    return written > 0 && (size_t)written < size ? 0 : -1;
}

int storage_next_pending(char *out, size_t size) {
    DIR *dir = opendir(PENDING_DIR);
    if (!dir) return -1;
    struct dirent *entry;
    int result = 0;
    while ((entry = readdir(dir))) {
        size_t len = strlen(entry->d_name);
        if (len < 5 || strcmp(entry->d_name + len - 4, ".mp4")) continue;
        int written = snprintf(out, size, "%s/%s", PENDING_DIR, entry->d_name);
        if (written < 0 || (size_t)written >= size) { result = -1; break; }
        result = 1;
        break;
    }
    closedir(dir);
    return result;
}

int storage_write_metadata(const Config *config, const char *capture_id) {
    char path[320], temp[324];
    int n = snprintf(path, sizeof(path), "%s/%s.json", PENDING_DIR, capture_id);
    if (n < 0 || (size_t)n >= sizeof(path)) return -1;
    n = snprintf(temp, sizeof(temp), "%s.tmp", path);
    if (n < 0 || (size_t)n >= sizeof(temp)) return -1;
    cJSON *root = cJSON_CreateObject();
    if (!root) return -1;
    cJSON_AddStringToObject(root, "capture_id", capture_id);
    cJSON_AddNumberToObject(root, "width", config->width);
    cJSON_AddNumberToObject(root, "height", config->height);
    cJSON_AddNumberToObject(root, "fps", config->fps);
    cJSON_AddNumberToObject(root, "duration_ms", config->duration_ms);
    char *json = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!json) return -1;
    FILE *file = fopen(temp, "wb");
    if (!file) { cJSON_free(json); return -1; }
    size_t len = strlen(json);
    int ok = fwrite(json, 1, len, file) == len && fflush(file) == 0 &&
             fsync(fileno(file)) == 0;
    if (fclose(file)) ok = 0;
    cJSON_free(json);
    if (!ok || rename(temp, path)) return -1;
    int directory = open(PENDING_DIR, O_RDONLY | O_DIRECTORY);
    if (directory < 0) return -1;
    int synced = fsync(directory);
    close(directory);
    return synced ? -1 : 0;
}

static const char *phase_name(int phase) {
    if (phase == COMMAND_SEEN) return "seen";
    if (phase == COMMAND_ACKED) return "acked";
    if (phase == COMMAND_STARTED) return "started";
    return "none";
}

static int phase_value(const char *name) {
    if (!strcmp(name, "seen")) return COMMAND_SEEN;
    if (!strcmp(name, "acked")) return COMMAND_ACKED;
    if (!strcmp(name, "started")) return COMMAND_STARTED;
    return COMMAND_NONE;
}

int storage_command_load(char *command_id, size_t command_n, char *capture_id, size_t capture_n, int *phase) {
    command_id[0] = 0;
    capture_id[0] = 0;
    *phase = COMMAND_NONE;
    FILE *file = fopen(STATE_DIR "/command.json", "rb");
    if (!file) return 0;
    char text[1024];
    size_t len = fread(text, 1, sizeof(text) - 1, file);
    int too_large = !feof(file);
    fclose(file);
    if (too_large) return -1;
    text[len] = 0;
    cJSON *root = cJSON_Parse(text);
    if (!root) return -1;
    const cJSON *command = cJSON_GetObjectItemCaseSensitive(root, "command_id");
    const cJSON *capture = cJSON_GetObjectItemCaseSensitive(root, "capture_id");
    const cJSON *state = cJSON_GetObjectItemCaseSensitive(root, "phase");
    if (cJSON_IsString(command) && command->valuestring && strlen(command->valuestring) < command_n)
        strcpy(command_id, command->valuestring);
    if (cJSON_IsString(capture) && capture->valuestring && strlen(capture->valuestring) < capture_n)
        strcpy(capture_id, capture->valuestring);
    if (cJSON_IsString(state) && state->valuestring) *phase = phase_value(state->valuestring);
    cJSON_Delete(root);
    return 0;
}

int storage_command_save(const char *command_id, const char *capture_id, int phase) {
    cJSON *root = cJSON_CreateObject();
    if (!root) return -1;
    cJSON_AddStringToObject(root, "command_id", command_id ? command_id : "");
    cJSON_AddStringToObject(root, "capture_id", capture_id ? capture_id : "");
    cJSON_AddStringToObject(root, "phase", phase_name(phase));
    char *json = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!json) return -1;
    char temp[] = STATE_DIR "/command.json.tmp";
    FILE *file = fopen(temp, "wb");
    if (!file) { cJSON_free(json); return -1; }
    size_t len = strlen(json);
    int ok = fwrite(json, 1, len, file) == len && fflush(file) == 0 &&
             fsync(fileno(file)) == 0;
    if (fclose(file)) ok = 0;
    cJSON_free(json);
    if (!ok) { unlink(temp); return -1; }
    if (rename(temp, STATE_DIR "/command.json")) return -1;
    int directory = open(STATE_DIR, O_RDONLY | O_DIRECTORY);
    if (directory < 0) return -1;
    int synced = fsync(directory);
    close(directory);
    return synced ? -1 : 0;
}
