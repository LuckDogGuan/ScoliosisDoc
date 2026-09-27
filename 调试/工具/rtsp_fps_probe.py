"""Count RTSP-over-TCP video frames by RTP marker bit. Usage: rtsp_fps_probe.py host port seconds"""
import socket
import sys
import time


def exchange(sock, lines):
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    head, rest = data.split(b"\r\n\r\n", 1)
    text = head.decode("latin1", "replace")
    length = 0
    for line in text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    while len(rest) < length:
        chunk = sock.recv(4096)
        if not chunk:
            break
        rest += chunk
    return text, rest[:length], rest[length:]


def measure(host, port, seconds):
    path = "/live/0"
    base = f"rtsp://{host}:{port}{path}"
    sock = socket.create_connection((host, port), timeout=5)
    sock.settimeout(5)
    cseq = 1

    def request(extra):
        nonlocal cseq
        lines = [extra[0], f"CSeq: {cseq}", "User-Agent: fpsprobe", *extra[1:]]
        cseq += 1
        return exchange(sock, lines)

    text, _, _ = request([f"OPTIONS {base} RTSP/1.0"])
    if "200" not in text.split("\r\n", 1)[0]:
        print(text)
        return 2
    text, body, _ = request([f"DESCRIBE {base} RTSP/1.0", "Accept: application/sdp"])
    if "200" not in text.split("\r\n", 1)[0]:
        print(text)
        print(body.decode("latin1", "replace")[:500])
        return 2
    sdp = body.decode("latin1", "replace")
    control = None
    in_video = False
    for line in sdp.splitlines():
        if line.startswith("m=video"):
            in_video = True
        elif line.startswith("m="):
            in_video = False
        if in_video and line.startswith("a=control:"):
            control = line.split(":", 1)[1].strip()
    if not control:
        control = "trackID=0"
    setup_url = control if control.startswith("rtsp://") else base.rstrip("/") + "/" + control
    text, _, _ = request([
        f"SETUP {setup_url} RTSP/1.0",
        "Transport: RTP/AVP/TCP;unicast;interleaved=0-1",
    ])
    if "200" not in text.split("\r\n", 1)[0]:
        print(text)
        return 2
    session = ""
    for line in text.split("\r\n"):
        if line.lower().startswith("session:"):
            session = line.split(":", 1)[1].strip().split(";")[0].strip()
    text, _, extra = request([
        f"PLAY {base} RTSP/1.0",
        f"Session: {session}",
        "Range: npt=0.000-",
    ])
    if "200" not in text.split("\r\n", 1)[0]:
        print(text)
        return 2

    buf = extra
    sock.settimeout(1.0)
    frames = 0
    packets = 0
    first = None
    last = None
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if len(buf) < 4:
            try:
                chunk = sock.recv(65535)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            continue
        if buf[0:1] != b"$":
            mark = buf.find(b"$")
            buf = b"" if mark < 0 else buf[mark:]
            continue
        length = int.from_bytes(buf[2:4], "big")
        if len(buf) < 4 + length:
            try:
                chunk = sock.recv(65535)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            continue
        channel = buf[1]
        payload = buf[4:4 + length]
        buf = buf[4 + length:]
        if channel == 0 and len(payload) >= 2:
            packets += 1
            if payload[1] & 0x80:
                now = time.monotonic()
                first = now if first is None else first
                last = now
                frames += 1
    span = (last - first) if first is not None and last is not None and last > first else 0.0
    fps = ((frames - 1) / span) if span > 0 and frames > 1 else 0.0
    print(f"frames={frames} packets={packets} span={span:.2f}s fps={fps:.1f}")
    try:
        sock.sendall(
            f"TEARDOWN {base} RTSP/1.0\r\nCSeq: {cseq}\r\nSession: {session}\r\n\r\n".encode()
        )
    except OSError:
        pass
    sock.close()
    return 0 if frames > 1 else 1


if __name__ == "__main__":
    sys.exit(measure(sys.argv[1], int(sys.argv[2]), float(sys.argv[3])))
