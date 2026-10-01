#include "app.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <syslog.h>
#include <time.h>
#include <unistd.h>

#define MAX_EXISTING 512

static int read_all(int fd, void *data, size_t count) {
    unsigned char *at = data;
    while (count) {
        ssize_t n = read(fd, at, count);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        at += n;
        count -= (size_t)n;
    }
    return 0;
}

static int write_all(int fd, const void *data, size_t count) {
    const unsigned char *at = data;
    while (count) {
        ssize_t n = write(fd, at, count);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        at += n;
        count -= (size_t)n;
    }
    return 0;
}

static int rpc_open(const char *name) {
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    struct timeval timeout = {.tv_sec = 4};
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, "/var/tmp/rkipc");
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) ||
        connect(fd, (struct sockaddr *)&address, sizeof(address))) { close(fd); return -1; }
    int32_t hello = -1, length = (int32_t)strlen(name) + 1;
    if (read_all(fd, &hello, sizeof(hello)) || hello ||
        write_all(fd, &length, sizeof(length)) || write_all(fd, name, (size_t)length)) {
        close(fd); return -1;
    }
    return fd;
}

static int rpc_simple(const char *name) {
    int fd = rpc_open(name);
    if (fd < 0) return -1;
    int32_t error = -1;
    int result = read_all(fd, &error, sizeof(error));
    close(fd);
    return result || error ? -1 : 0;
}

static int rpc_status(int *status) {
    int fd = rpc_open("rk_storage_record_statue_get");
    if (fd < 0) return -1;
    int32_t value = -1, error = -1;
    int result = read_all(fd, &value, sizeof(value));
    if (!result) result = read_all(fd, &error, sizeof(error));
    close(fd);
    if (result || error) return -1;
    *status = value;
    return 0;
}

static int rpc_int(const char *name, int *value, int set) {
    int fd = rpc_open(name);
    if (fd < 0) return -1;
    int32_t channel = 0, number = *value, error = -1;
    int result = write_all(fd, &channel, sizeof(channel));
    if (!result && set) result = write_all(fd, &number, sizeof(number));
    if (!result && !set) result = read_all(fd, &number, sizeof(number));
    if (!result) result = read_all(fd, &error, sizeof(error));
    close(fd);
    if (result || error) return -1;
    if (!set) *value = number;
    return 0;
}

static int rpc_rate(const char *name, char *rate, size_t size, int set) {
    int fd = rpc_open(name);
    if (fd < 0) return -1;
    int32_t channel = 0, length = (int32_t)strlen(rate) + 1, error = -1;
    int result = write_all(fd, &channel, sizeof(channel));
    if (!result && set) {
        result = write_all(fd, &length, sizeof(length));
        if (!result) result = write_all(fd, rate, (size_t)length);
    }
    if (!result && !set) {
        result = read_all(fd, &length, sizeof(length));
        if (!result && (length <= 0 || (size_t)length >= size)) result = -1;
        if (!result) result = read_all(fd, rate, (size_t)length);
        if (!result) rate[length] = 0;
    }
    if (!result) result = read_all(fd, &error, sizeof(error));
    close(fd);
    return result || error ? -1 : 0;
}

static int is_mp4(const char *name) {
    size_t n = strlen(name);
    return n > 4 && !strcmp(name + n - 4, ".mp4");
}

static int snapshot(char names[MAX_EXISTING][256], int *count) {
    DIR *dir = opendir(VIDEO_DIR);
    if (!dir) return -1;
    struct dirent *entry;
    *count = 0;
    while ((entry = readdir(dir))) {
        if (!is_mp4(entry->d_name)) continue;
        if (*count == MAX_EXISTING) { closedir(dir); return -1; }
        strcpy(names[(*count)++], entry->d_name);
    }
    closedir(dir);
    return 0;
}

static int collision_near_now(void) {
    for (int offset = 0; offset < 3; offset++) {
        time_t when = time(NULL) + offset;
        struct tm calendar;
        if (!localtime_r(&when, &calendar)) return -1;
        char name[64], path[128];
        if (!strftime(name, sizeof(name), "%Y%m%d%H%M%S.mp4", &calendar)) return -1;
        snprintf(path, sizeof(path), "%s/%s", VIDEO_DIR, name);
        if (!access(path, F_OK)) return -1;
    }
    return 0;
}

static int find_new(char names[MAX_EXISTING][256], int count, char *path, size_t size) {
    DIR *dir = opendir(VIDEO_DIR);
    if (!dir) return -1;
    struct dirent *entry;
    int found = 0;
    while ((entry = readdir(dir))) {
        if (!is_mp4(entry->d_name)) continue;
        int old = 0;
        for (int i = 0; i < count; i++) if (!strcmp(names[i], entry->d_name)) old = 1;
        if (!old) {
            int n = snprintf(path, size, "%s/%s", VIDEO_DIR, entry->d_name);
            if (n < 0 || (size_t)n >= size) { found = -1; break; }
            found++;
        }
    }
    closedir(dir);
    return found == 1 ? 0 : -1;
}

static int valid_mp4(const char *path) {
    struct stat info;
    if (stat(path, &info) || !S_ISREG(info.st_mode) || info.st_size < 100000) return -1;
    FILE *file = fopen(path, "rb");
    if (!file) return -1;
    unsigned char header[8];
    int ok = fread(header, 1, sizeof(header), file) == sizeof(header) &&
             !memcmp(header + 4, "ftyp", 4);
    fclose(file);
    return ok ? 0 : -1;
}

int capture_record(const Config *config, const char *capture_id) {
    char old_rate[32] = {0};
    int old_bitrate = 0, old_gop = 0;
    if (rpc_rate("rk_video_get_frame_rate", old_rate, sizeof(old_rate), 0) ||
        rpc_int("rk_video_get_max_rate", &old_bitrate, 0) ||
        rpc_int("rk_video_get_gop", &old_gop, 0)) return -1;
    char names[MAX_EXISTING][256];
    int count = 0;
    if (snapshot(names, &count) || collision_near_now()) return -1;
    char target_rate[] = "60/2";
    int bitrate = config->bitrate_kbps, gop = config->gop;
    int started = 0, ok = 0;
    if (!rpc_rate("rk_video_set_frame_rate", target_rate, sizeof(target_rate), 1) &&
        !rpc_int("rk_video_set_max_rate", &bitrate, 1) &&
        !rpc_int("rk_video_set_gop", &gop, 1) &&
        !rpc_simple("rk_storage_record_start")) {
        started = 1;
        struct timespec delay = {.tv_sec = config->duration_ms / 1000,
                                 .tv_nsec = (config->duration_ms % 1000) * 1000000L};
        while (nanosleep(&delay, &delay) && errno == EINTR) {}
        ok = rpc_simple("rk_storage_record_stop") == 0;
        if (!ok) {
            syslog(LOG_ERR, "record stop failed; retrying once");
            ok = rpc_simple("rk_storage_record_stop") == 0;
        }
        if (!ok) {
            int status = -1;
            if (!rpc_status(&status) && status == 0) ok = 1;
            else {
                syslog(LOG_CRIT, "record stop unresolved (status %d); manual board check required", status);
            }
        }
    }
    int restore_rate = rpc_rate("rk_video_set_frame_rate", old_rate, sizeof(old_rate), 1);
    int restore_bitrate = rpc_int("rk_video_set_max_rate", &old_bitrate, 1);
    int restore_gop = rpc_int("rk_video_set_gop", &old_gop, 1);
    if (restore_rate || restore_bitrate || restore_gop)
        syslog(LOG_ERR, "preview parameter restoration incomplete: fps=%d rate=%d gop=%d",
               restore_rate, restore_bitrate, restore_gop);
    if (!started || !ok || restore_rate || restore_bitrate || restore_gop) return -1;
    char source[384], temp[384], final[384];
    if (find_new(names, count, source, sizeof(source))) {
        syslog(LOG_ERR, "recorded MP4 count ambiguous; original files retained in video directory");
        return -1;
    }
    if (valid_mp4(source)) {
        syslog(LOG_ERR, "recorded MP4 failed basic validation: %s", source);
        return -1;
    }
    int n = snprintf(temp, sizeof(temp), "%s/%s.tmp", WRITING_DIR, capture_id);
    if (n < 0 || (size_t)n >= sizeof(temp)) return -1;
    n = snprintf(final, sizeof(final), "%s/%s.mp4", PENDING_DIR, capture_id);
    if (n < 0 || (size_t)n >= sizeof(final) || !access(temp, F_OK) || !access(final, F_OK)) return -1;
    if (rename(source, temp) || rename(temp, final)) return -1;
    int file = open(final, O_RDONLY);
    if (file < 0) return -1;
    int synced = fsync(file);
    close(file);
    if (synced) return -1;
    int directory = open(PENDING_DIR, O_RDONLY | O_DIRECTORY);
    if (directory < 0) return -1;
    synced = fsync(directory);
    close(directory);
    if (synced) return -1;
    return storage_write_metadata(config, capture_id);
}
