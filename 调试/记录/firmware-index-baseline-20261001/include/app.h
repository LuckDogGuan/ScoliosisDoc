#ifndef INSTRUMENT_APP_H
#define INSTRUMENT_APP_H

/* 源码按目录分模块：
 * src/app      主循环
 * src/net      UDP 发现、HTTP 回执、Wi-Fi
 * src/capture  录像
 * src/storage  目录、待传文件、命令状态
 * src/audio    喇叭
 * src/board    电池、按键、灯
 * src/config   配置
 */

#include <stddef.h>

#define INSTRUMENT_VERSION "0.0.1"
#define INSTRUMENT_ROOT "/opt/instrument"
#define STATE_DIR INSTRUMENT_ROOT "/state"
#define SOUND_DIR INSTRUMENT_ROOT "/sounds"
#define LEGACY_SOUND_DIR "/userdata/sounds"
#define WRITING_DIR INSTRUMENT_ROOT "/capture/writing"
#define PENDING_DIR INSTRUMENT_ROOT "/capture/pending"
#define LEGACY_PENDING_DIR "/userdata/capture/pending"
#define VIDEO_DIR "/video0"
#define DISCOVER_PORT 37020

enum {
    COMMAND_NONE = 0,
    COMMAND_SEEN = 1,
    COMMAND_ACKED = 2,
    COMMAND_STARTED = 3
};

typedef struct {
    char device_id[64];
    char wifi_ssid[64];
    char pc_base_url[192];
    int volume;
    int width, height, fps, bitrate_kbps, duration_ms, gop;
    char config_path[256];
} Config;

int config_load(const char *path, Config *config);
int config_save_volume(const char *path, int volume);
int wifi_address(char *out, size_t size);
int wifi_rssi(void);
int wifi_gateway_reachable(void);
int wifi_reconnect(void);
int storage_prepare(void);
long storage_free_mb(void);
long storage_total_mb(void);
int storage_memory_mb(long *available, long *total);
int storage_pending_count(void);
int storage_capture_id(const Config *config, char *out, size_t size);
int storage_next_pending(char *out, size_t size);
int storage_write_metadata(const Config *config, const char *capture_id);
int storage_command_load(char *command_id, size_t command_n, char *capture_id, size_t capture_n, int *phase);
int storage_command_save(const char *command_id, const char *capture_id, int phase);
int audio_play(const char *name);
void audio_set_volume(int volume);
int http_hello(Config *config, const char *ip, const char *event_id, int *paired,
               char *pair_event, size_t pair_n, char *unpair_event, size_t unpair_n);
int http_event_ack(const Config *config, const char *event_id, const char *kind);
int http_capture_status(const Config *config, const char *capture_id, const char *phase);
int http_poll(const Config *config, int *capture, char *command_id, size_t command_n);
int http_command_receipt(const Config *config, char *command_id, size_t command_n,
                         int *capture, int *acked, int *started);
int http_command_ack(const Config *config, const char *command_id);
int http_capture_start(const Config *config, const char *capture_id);
int http_upload(const Config *config, const char *capture_id, const char *path);
int http_file_stored(const Config *config, const char *capture_id, int *stored,
                     long long *size_bytes, char *sha256, size_t sha_n);
int capture_record(const Config *config, const char *capture_id);
int discover_open(void);
int discover_poll(Config *config);
int battery_present(void);
int button_capture_pressed(void);
void light_update(int paired);
int run_command(char *const argv[]);

#endif
