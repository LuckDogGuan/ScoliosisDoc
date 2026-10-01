#include "app.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <unistd.h>

int wifi_address(char *out, size_t size) {
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return -1;
    struct ifreq req = {0};
    strncpy(req.ifr_name, "wlan0", IFNAMSIZ - 1);
    int result = ioctl(fd, SIOCGIFADDR, &req);
    close(fd);
    if (result < 0) return -1;
    const struct sockaddr_in *addr = (const struct sockaddr_in *)&req.ifr_addr;
    return inet_ntop(AF_INET, &addr->sin_addr, out, (socklen_t)size) ? 0 : -1;
}

int wifi_rssi(void) {
    FILE *poll = popen("wpa_cli -i wlan0 signal_poll 2>/dev/null", "r");
    if (poll) {
        char line[128];
        int value;
        while (fgets(line, sizeof(line), poll)) {
            if (sscanf(line, "RSSI=%d", &value) == 1) { pclose(poll); return value; }
        }
        pclose(poll);
    }
    FILE *file = fopen("/proc/net/wireless", "r");
    if (!file) return -100;
    char line[256];
    int rssi = -100;
    while (fgets(line, sizeof(line), file)) {
        char *wlan = strstr(line, "wlan0:");
        float quality, level;
        if (wlan && sscanf(wlan, "wlan0: %*d %f %f", &quality, &level) == 2) {
            (void)quality;
            rssi = (int)level;
            break;
        }
    }
    fclose(file);
    return rssi;
}

int wifi_gateway_reachable(void) {
    FILE *routes = fopen("/proc/net/route", "r");
    if (!routes) return -1;
    char line[256], iface[16];
    unsigned long destination, gateway;
    unsigned int flags;
    int result = -1;
    while (fgets(line, sizeof(line), routes)) {
        if (sscanf(line, "%15s %lx %lx %x", iface, &destination, &gateway, &flags) != 4 ||
            strcmp(iface, "wlan0") || destination || !(flags & 1)) continue;
        struct in_addr address = {.s_addr = (in_addr_t)gateway};
        char host[INET_ADDRSTRLEN];
        if (inet_ntop(AF_INET, &address, host, sizeof(host))) {
            char *const args[] = {"arping", "-f", "-q", "-c", "1", "-w", "2",
                                  "-I", "wlan0", host, NULL};
            result = run_command(args) == 0;
        }
        break;
    }
    fclose(routes);
    return result;
}

int wifi_reconnect(void) {
    char *const disconnect[] = {"wpa_cli", "-i", "wlan0", "disconnect", NULL};
    char *const reconnect[] = {"wpa_cli", "-i", "wlan0", "reconnect", NULL};
    int first = run_command(disconnect);
    int second = run_command(reconnect);
    return first || second ? -1 : 0;
}
