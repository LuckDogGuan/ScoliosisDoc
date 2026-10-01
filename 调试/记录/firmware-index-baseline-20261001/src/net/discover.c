#include "app.h"
#include "cJSON.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <syslog.h>
#include <sys/socket.h>
#include <unistd.h>

static int discover_fd = -1;

int discover_open(void) {
    discover_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (discover_fd < 0) return -1;
    int yes = 1;
    if (setsockopt(discover_fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes))) {
        close(discover_fd);
        discover_fd = -1;
        return -1;
    }
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(DISCOVER_PORT);
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(discover_fd, (struct sockaddr *)&address, sizeof(address))) {
        close(discover_fd);
        discover_fd = -1;
        return -1;
    }
    int flags = fcntl(discover_fd, F_GETFL, 0);
    if (flags < 0 || fcntl(discover_fd, F_SETFL, flags | O_NONBLOCK)) {
        close(discover_fd);
        discover_fd = -1;
        return -1;
    }
    syslog(LOG_INFO, "UDP discover listening on %d", DISCOVER_PORT);
    return 0;
}

static int nonce_ok(const char *nonce) {
    size_t length = strlen(nonce);
    if (length < 4 || length > 64) return 0;
    for (const char *p = nonce; *p; p++) {
        if (!((*p >= '0' && *p <= '9') || (*p >= 'A' && *p <= 'Z') ||
              (*p >= 'a' && *p <= 'z')))
            return 0;
    }
    return 1;
}

int discover_poll(Config *config) {
    if (discover_fd < 0) return 0;
    int changed = 0;
    for (;;) {
        char buffer[1024];
        struct sockaddr_in from = {0};
        socklen_t from_len = sizeof(from);
        ssize_t count = recvfrom(discover_fd, buffer, sizeof(buffer) - 1, 0,
                                 (struct sockaddr *)&from, &from_len);
        if (count < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            break;
        }
        buffer[count] = 0;
        cJSON *root = cJSON_Parse(buffer);
        if (!root) continue;
        const cJSON *version = cJSON_GetObjectItemCaseSensitive(root, "version");
        const cJSON *op = cJSON_GetObjectItemCaseSensitive(root, "op");
        const cJSON *nonce = cJSON_GetObjectItemCaseSensitive(root, "nonce");
        const cJSON *http_port = cJSON_GetObjectItemCaseSensitive(root, "http_port");
        int ok = cJSON_IsNumber(version) && version->valueint == 2 &&
                 cJSON_IsString(op) && op->valuestring && !strcmp(op->valuestring, "discover") &&
                 cJSON_IsString(nonce) && nonce->valuestring && nonce_ok(nonce->valuestring) &&
                 cJSON_IsNumber(http_port) && http_port->valueint >= 1 &&
                 http_port->valueint <= 65535;
        char nonce_copy[65];
        int port = 0;
        if (ok) {
            snprintf(nonce_copy, sizeof(nonce_copy), "%s", nonce->valuestring);
            port = http_port->valueint;
        }
        cJSON_Delete(root);
        if (!ok) continue;

        char host[INET_ADDRSTRLEN];
        if (!inet_ntop(AF_INET, &from.sin_addr, host, sizeof(host))) continue;
        cJSON *reply = cJSON_CreateObject();
        if (!reply) continue;
        cJSON_AddNumberToObject(reply, "version", 2);
        cJSON_AddStringToObject(reply, "op", "here");
        cJSON_AddStringToObject(reply, "nonce", nonce_copy);
        cJSON_AddStringToObject(reply, "device_id", config->device_id);
        cJSON_AddStringToObject(reply, "firmware", INSTRUMENT_VERSION);
        char *text = cJSON_PrintUnformatted(reply);
        cJSON_Delete(reply);
        if (!text) continue;
        sendto(discover_fd, text, strlen(text), 0, (struct sockaddr *)&from, from_len);
        cJSON_free(text);

        char url[192];
        int written = snprintf(url, sizeof(url), "http://%s:%d", host, port);
        if (written > 0 && (size_t)written < sizeof(url) && strcmp(config->pc_base_url, url)) {
            snprintf(config->pc_base_url, sizeof(config->pc_base_url), "%s", url);
            syslog(LOG_INFO, "UDP discover selected %s", config->pc_base_url);
            changed = 1;
        }
    }
    return changed;
}
