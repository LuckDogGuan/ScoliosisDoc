#include "app.h"
#include <dirent.h>
#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <syslog.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t running = 1;
static pid_t upload_pid = -1;
static time_t retry_upload_after = 0;
static char upload_capture_id[128];
static char warned_capture_id[128];

static void stop(int signal_number) { (void)signal_number; running = 0; }

int run_command(char *const argv[]) {
    pid_t child = fork();
    if (child < 0) return -1;
    if (!child) { execvp(argv[0], argv); _exit(127); }
    int status;
    while (waitpid(child, &status, 0) < 0) if (errno != EINTR) return -1;
    return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -1;
}

static int persist(const char *command_id, const char *capture_id, int phase) {
    if (storage_command_save(command_id ? command_id : "",
                             capture_id ? capture_id : "", phase)) {
        syslog(LOG_ERR, "cannot persist command state");
        return -1;
    }
    return 0;
}

static void clear_command(char *command_id, char *capture_id, int *phase) {
    (void)persist("", "", COMMAND_NONE);
    command_id[0] = 0;
    capture_id[0] = 0;
    *phase = COMMAND_NONE;
}

static int capture_pending(const char *capture_id) {
    char path[384];
    struct stat info;
    int n = snprintf(path, sizeof(path), "%s/%s.mp4", PENDING_DIR, capture_id);
    return n > 0 && (size_t)n < sizeof(path) && !stat(path, &info) && S_ISREG(info.st_mode);
}

static int file_digest(const char *path, char hash[65], long long *size_bytes) {
    struct stat info;
    if (stat(path, &info) || !S_ISREG(info.st_mode)) return -1;
    int pipe_fd[2];
    if (pipe(pipe_fd)) return -1;
    pid_t child = fork();
    if (child < 0) { close(pipe_fd[0]); close(pipe_fd[1]); return -1; }
    if (!child) {
        close(pipe_fd[0]);
        if (dup2(pipe_fd[1], STDOUT_FILENO) < 0) _exit(127);
        close(pipe_fd[1]);
        execlp("sha256sum", "sha256sum", path, (char *)NULL);
        _exit(127);
    }
    close(pipe_fd[1]);
    char output[128];
    size_t count = 0;
    while (count < 65) {
        ssize_t got = read(pipe_fd[0], output + count, sizeof(output) - count);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) break;
        count += (size_t)got;
    }
    close(pipe_fd[0]);
    int status;
    while (waitpid(child, &status, 0) < 0) if (errno != EINTR) return -1;
    if (count < 65 || !WIFEXITED(status) || WEXITSTATUS(status)) return -1;
    for (int i = 0; i < 64; i++) {
        char c = output[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return -1;
    }
    memcpy(hash, output, 64);
    hash[64] = 0;
    *size_bytes = (long long)info.st_size;
    return 0;
}

static int has_writing_file(void) {
    DIR *dir = opendir(WRITING_DIR);
    if (!dir) return 0;
    struct dirent *entry;
    int found = 0;
    while ((entry = readdir(dir))) {
        if (entry->d_name[0] == '.') continue;
        found = 1;
        break;
    }
    closedir(dir);
    return found;
}

static int remove_capture_files(const char *capture_id, const char *path) {
    if (unlink(path)) {
        syslog(LOG_ERR, "uploaded but cannot remove local file: %s", path);
        return -1;
    }
    char metadata[384];
    int n = snprintf(metadata, sizeof(metadata), "%s/%s.json", PENDING_DIR, capture_id);
    if (n > 0 && (size_t)n < sizeof(metadata)) (void)unlink(metadata);
    syslog(LOG_INFO, "upload acknowledged: %s", capture_id);
    return 0;
}

static int upload_and_remove(const Config *config, const char *capture_id, const char *path) {
    char local_hash[65], remote_hash[65];
    long long local_size, remote_size;
    if (file_digest(path, local_hash, &local_size)) return -1;
    int stored = 0;
    if (http_file_stored(config, capture_id, &stored, &remote_size,
                         remote_hash, sizeof(remote_hash)) || !stored) {
        (void)http_capture_status(config, capture_id, "uploading");
        (void)http_upload(config, capture_id, path);
        stored = 0;
        (void)http_file_stored(config, capture_id, &stored, &remote_size,
                               remote_hash, sizeof(remote_hash));
    }
    if (stored && local_size == remote_size && !strcmp(local_hash, remote_hash)) {
        (void)http_capture_status(config, capture_id, "stored");
        return remove_capture_files(capture_id, path);
    }
    (void)http_capture_status(config, capture_id, "pending_local");
    syslog(LOG_WARNING, "upload failed: %s", capture_id);
    return -1;
}

static void spawn_upload(const Config *config, const char *capture_id, const char *path) {
    upload_pid = fork();
    if (!upload_pid) _exit(upload_and_remove(config, capture_id, path) ? 1 : 0);
    if (upload_pid > 0) snprintf(upload_capture_id, sizeof(upload_capture_id), "%s", capture_id);
    if (upload_pid < 0) syslog(LOG_ERR, "cannot start upload worker: %s", strerror(errno));
}

static void retry_one_pending(const Config *config) {
    if (upload_pid > 0) return;
    char path[384], capture_id[128];
    if (storage_next_pending(path, sizeof(path)) != 1) return;
    const char *name = strrchr(path, '/');
    name = name ? name + 1 : path;
    size_t length = strlen(name);
    if (length < 5 || strcmp(name + length - 4, ".mp4") || length - 4 >= sizeof(capture_id))
        return;
    memcpy(capture_id, name, length - 4);
    capture_id[length - 4] = 0;
    spawn_upload(config, capture_id, path);
}

static void reap_upload(void) {
    if (upload_pid <= 0) return;
    int status;
    pid_t result = waitpid(upload_pid, &status, WNOHANG);
    if (!result) return;
    upload_pid = -1;
    if (result > 0 && WIFEXITED(status) && !WEXITSTATUS(status))
        (void)audio_play("uploaded");
    else {
        if (strcmp(warned_capture_id, upload_capture_id)) {
            (void)audio_play("saved_on_device");
            snprintf(warned_capture_id, sizeof(warned_capture_id), "%s", upload_capture_id);
        }
        struct timespec now;
        if (!clock_gettime(CLOCK_MONOTONIC, &now)) retry_upload_after = now.tv_sec + 10;
    }
}

static int refuse_if_low_space(const Config *config) {
    long free_mb = storage_free_mb();
    long expected_mb = ((long)config->bitrate_kbps * config->duration_ms + 7999999) / 8000000;
    if (free_mb < 16 + 2 * expected_mb) {
        syslog(LOG_WARNING, "capture refused: free space %ld MB", free_mb);
        (void)audio_play("storage_low");
        return -1;
    }
    return 0;
}

static void after_record(const Config *config, const char *capture_id, int network_ready) {
    (void)audio_play("capture_done");
    if (network_ready) (void)http_capture_status(config, capture_id, "pending_local");
    else (void)audio_play("saved_on_device");
}

static void ack_current(const Config *config, char *command_id, char *capture_id, int *phase) {
    if (!http_command_ack(config, command_id) &&
        !persist(command_id, capture_id, COMMAND_ACKED))
        *phase = COMMAND_ACKED;
}

static int accept_seen(const Config *config, char *command_id, char *capture_id, int *phase) {
    if (persist(command_id, capture_id, COMMAND_SEEN)) return -1;
    *phase = COMMAND_SEEN;
    ack_current(config, command_id, capture_id, phase);
    return 0;
}

static void apply_receipt(const Config *config, char *command_id, size_t command_n,
                          char *capture_id, int *phase) {
    char receipt_id[128];
    int capture = 0, acked = 0, started = 0;
    if (http_command_receipt(config, receipt_id, sizeof(receipt_id), &capture, &acked, &started))
        return;
    if (started && command_id[0] && receipt_id[0] && !strcmp(command_id, receipt_id)) {
        if (!persist(command_id, capture_id, COMMAND_STARTED)) *phase = COMMAND_STARTED;
        return;
    }
    if (acked && command_id[0] && receipt_id[0] && !strcmp(command_id, receipt_id)) {
        if (!persist(command_id, capture_id, COMMAND_ACKED)) *phase = COMMAND_ACKED;
        return;
    }
    if (capture && receipt_id[0] && (!command_id[0] || !strcmp(command_id, receipt_id))) {
        if (!command_id[0]) {
            if (strlen(receipt_id) >= command_n) return;
            strcpy(command_id, receipt_id);
        }
        (void)accept_seen(config, command_id, capture_id, phase);
    }
}

static void start_and_record(const Config *config, char *command_id, char *capture_id,
                             size_t capture_n, int *phase, time_t *last_hello) {
    if (refuse_if_low_space(config)) return;
    if (!capture_id[0]) {
        if (storage_capture_id(config, capture_id, capture_n)) {
            syslog(LOG_ERR, "capture id generation failed");
            return;
        }
        if (persist(command_id, capture_id, COMMAND_ACKED)) return;
    }
    int start = http_capture_start(config, capture_id);
    if (start == -1) {
        char receipt_id[128];
        int capture = 0, acked = 0, started = 0;
        if (!http_command_receipt(config, receipt_id, sizeof(receipt_id),
                                  &capture, &acked, &started) &&
            started && (!receipt_id[0] || !strcmp(receipt_id, command_id)))
            start = 0;
        else
            return;
    }
    if (start == -2) {
        syslog(LOG_WARNING, "capture start was not accepted: %s", capture_id);
        (void)audio_play("capture_failed");
        clear_command(command_id, capture_id, phase);
        return;
    }
    if (persist(command_id, capture_id, COMMAND_STARTED)) return;
    *phase = COMMAND_STARTED;
    (void)http_capture_status(config, capture_id, "recording");
    if (capture_record(config, capture_id)) {
        syslog(LOG_ERR, "recording failed: %s", capture_id);
        (void)http_capture_status(config, capture_id, "failed");
        (void)audio_play("capture_failed");
        return;
    }
    after_record(config, capture_id, 1);
    clear_command(command_id, capture_id, phase);
    *last_hello = 0;
}

static void handle_local_capture(const Config *config, int network_ready, time_t *last_hello) {
    if (refuse_if_low_space(config)) return;
    char capture_id[128];
    if (storage_capture_id(config, capture_id, sizeof(capture_id))) {
        syslog(LOG_ERR, "capture id generation failed");
        return;
    }
    if (network_ready) {
        int start = http_capture_start(config, capture_id);
        if (start == -2) {
            syslog(LOG_WARNING, "capture start was not accepted; recording cancelled: %s",
                   capture_id);
            (void)audio_play("capture_failed");
            return;
        }
    }
    if (network_ready) (void)http_capture_status(config, capture_id, "recording");
    if (capture_record(config, capture_id)) {
        syslog(LOG_ERR, "recording failed: %s", capture_id);
        if (network_ready) (void)http_capture_status(config, capture_id, "failed");
        (void)audio_play("capture_failed");
        return;
    }
    after_record(config, capture_id, network_ready);
    *last_hello = 0;
}

static void handle_legacy_capture(const Config *config, time_t *last_hello) {
    if (refuse_if_low_space(config)) return;
    char capture_id[128];
    if (storage_capture_id(config, capture_id, sizeof(capture_id))) {
        syslog(LOG_ERR, "capture id generation failed");
        return;
    }
    int start = http_capture_start(config, capture_id);
    if (start == -2) {
        syslog(LOG_WARNING, "capture start was not accepted; recording cancelled: %s", capture_id);
        (void)audio_play("capture_failed");
        return;
    }
    if (start == -1) return;
    (void)http_capture_status(config, capture_id, "recording");
    if (capture_record(config, capture_id)) {
        syslog(LOG_ERR, "recording failed: %s", capture_id);
        (void)http_capture_status(config, capture_id, "failed");
        (void)audio_play("capture_failed");
        return;
    }
    after_record(config, capture_id, 1);
    *last_hello = 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--version")) {
        puts(INSTRUMENT_VERSION);
        return 0;
    }
    if (argc == 4 && !strcmp(argv[1], "--save-volume")) {
        int vol = atoi(argv[3]);
        return config_save_volume(argv[2], vol) ? 1 : 0;
    }
    const char *config_path = argc > 1 && argv[1][0] != '-' ? argv[1] :
                              "/userdata/instrument/config.json";
    if (argc == 3 && !strcmp(argv[1], "--check-config")) config_path = argv[2];
    if (argc == 3 && !strcmp(argv[1], "--hello")) config_path = argv[2];
    if (argc == 5 && !strcmp(argv[1], "--upload-file")) config_path = argv[2];
    Config config = {0};
    if (config_load(config_path, &config)) {
        fprintf(stderr, "invalid config: %s\n", config_path);
        return 2;
    }
    if (argc == 3 && !strcmp(argv[1], "--check-config")) {
        puts("config OK");
        return 0;
    }
    if (argc == 3 && !strcmp(argv[1], "--hello")) {
        int paired = 0;
        char pair_event[128] = {0}, unpair_event[128] = {0};
        char ip[INET_ADDRSTRLEN] = "127.0.0.1";
        (void)wifi_address(ip, sizeof(ip));
        return http_hello(&config, ip, "test-boot-event", &paired,
                          pair_event, sizeof(pair_event),
                          unpair_event, sizeof(unpair_event)) ? 1 : 0;
    }
    openlog("instrument_app", LOG_PID | LOG_CONS, LOG_DAEMON);
    if (argc == 5 && !strcmp(argv[1], "--upload-file"))
        return http_upload(&config, argv[3], argv[4]) ? 1 : 0;
    signal(SIGINT, stop);
    signal(SIGTERM, stop);
    signal(SIGPIPE, SIG_IGN);
    signal(SIGHUP, SIG_IGN);
    if (storage_prepare()) {
        syslog(LOG_ERR, "cannot create pending directory");
        return 1;
    }
    audio_set_volume(config.volume);
    FILE *version_file = fopen(STATE_DIR "/version", "wb");
    if (version_file) {
        fputs(INSTRUMENT_VERSION "\n", version_file);
        fclose(version_file);
    }
    if (discover_open()) syslog(LOG_ERR, "UDP discover socket failed");
    syslog(LOG_INFO, "instrument %s started; volume %d", INSTRUMENT_VERSION, config.volume);
    int paired = 0;
    int wifi_seen = 0, wifi_up = 0, hello_seen = 0;
    char boot_event_id[128];
    if (storage_capture_id(&config, boot_event_id, sizeof(boot_event_id))) {
        syslog(LOG_ERR, "cannot generate boot event id");
        return 1;
    }
    time_t last_hello = 0;
    time_t last_gateway_check = 0;
    int gateway_failures = 0;
    while (running) {
        reap_upload();
        char command_id[128], capture_id[128];
        int phase = COMMAND_NONE;
        if (storage_command_load(command_id, sizeof(command_id), capture_id, sizeof(capture_id),
                                 &phase)) {
            syslog(LOG_WARNING, "command state unreadable; ignoring");
            command_id[0] = 0;
            capture_id[0] = 0;
            phase = COMMAND_NONE;
        }
        if (phase == COMMAND_STARTED && capture_id[0] && capture_pending(capture_id)) {
            clear_command(command_id, capture_id, &phase);
        } else if (phase == COMMAND_STARTED && !has_writing_file()) {
            syslog(LOG_WARNING, "command started but no capture file remains; clearing command");
            clear_command(command_id, capture_id, &phase);
        }

        if (discover_poll(&config)) last_hello = 0;
        char ip[INET_ADDRSTRLEN];
        int local_trigger = button_capture_pressed();
        int has_wifi_address = !wifi_address(ip, sizeof(ip));
        struct timespec clock_time;
        int clock_ok = !clock_gettime(CLOCK_MONOTONIC, &clock_time);
        time_t now = clock_ok ? clock_time.tv_sec : 0;
        if (clock_ok && (!last_gateway_check || now - last_gateway_check >= 10)) {
            int reachable = has_wifi_address ? wifi_gateway_reachable() : 0;
            if (reachable >= 0) gateway_failures = reachable ? 0 : gateway_failures + 1;
            last_gateway_check = now;
            if (gateway_failures >= 3) {
                syslog(LOG_WARNING, "Wi-Fi gateway ARP failed 3 times; reconnecting wlan0");
                if (wifi_reconnect()) syslog(LOG_ERR, "Wi-Fi reconnect command failed");
                gateway_failures = 0;
                last_hello = 0;
                paired = 0;
                light_update(paired);
                sleep(1);
                continue;
            }
        }
        if (!has_wifi_address) {
            if (wifi_up) (void)audio_play("wifi_disconnected");
            wifi_seen = 1;
            wifi_up = 0;
            paired = 0;
            light_update(paired);
            if (local_trigger && phase == COMMAND_NONE) handle_local_capture(&config, 0, &last_hello);
            sleep(1);
            continue;
        }
        if (!wifi_seen || !wifi_up) (void)audio_play("wifi_connected");
        wifi_seen = 1;
        wifi_up = 1;
        if (!clock_ok) { sleep(1); continue; }
        if (!last_hello || now - last_hello >= 3) {
            char pair_event[128], unpair_event[128];
            if (http_hello(&config, ip, boot_event_id, &paired, pair_event,
                           sizeof(pair_event), unpair_event, sizeof(unpair_event))) paired = 0;
            else {
                if (!hello_seen && !paired && !unpair_event[0])
                    (void)audio_play("please_connect");
                hello_seen = 1;
                if (paired && pair_event[0]) {
                    (void)audio_play("pair_success");
                    (void)http_event_ack(&config, pair_event, "paired");
                } else if (!paired && unpair_event[0]) {
                    (void)audio_play("pair_disconnected");
                    (void)http_event_ack(&config, unpair_event, "unpaired");
                }
                if (paired && now >= retry_upload_after) retry_one_pending(&config);
            }
            last_hello = now;
            light_update(paired);
        }

        if (local_trigger && phase == COMMAND_NONE)
            handle_local_capture(&config, 1, &last_hello);

        if (paired && !local_trigger) {
            if (phase == COMMAND_NONE) {
                int remote_capture = 0;
                char poll_id[128];
                if (http_poll(&config, &remote_capture, poll_id, sizeof(poll_id)))
                    syslog(LOG_WARNING, "command poll failed");
                else if (remote_capture && poll_id[0]) {
                    strcpy(command_id, poll_id);
                    (void)accept_seen(&config, command_id, capture_id, &phase);
                } else if (remote_capture)
                    handle_legacy_capture(&config, &last_hello);
                else
                    apply_receipt(&config, command_id, sizeof(command_id), capture_id, &phase);
            } else if (phase == COMMAND_SEEN)
                apply_receipt(&config, command_id, sizeof(command_id), capture_id, &phase);
            if (phase == COMMAND_ACKED)
                start_and_record(&config, command_id, capture_id, sizeof(capture_id),
                                 &phase, &last_hello);
        }
        sleep(1);
    }
    if (upload_pid > 0) (void)waitpid(upload_pid, NULL, 0);
    closelog();
    return 0;
}
