import socket, struct, sys, time

PATH = "/var/tmp/rkipc"


def rd(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError("closed after %d bytes" % len(b))
        b += c
    return b


def call(name, ints=(), string=None, nreply=1):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(PATH)
    hello = struct.unpack("<i", rd(s, 4))[0]
    n = name.encode() + b"\0"
    msg = struct.pack("<i", len(n)) + n
    for v in ints:
        msg += struct.pack("<i", v)
    if string is not None:
        sb = string.encode() + b"\0"
        msg += struct.pack("<i", len(sb)) + sb
    t0 = time.time()
    s.sendall(msg)
    out = [struct.unpack("<i", rd(s, 4))[0] for _ in range(nreply)]
    dt = time.time() - t0
    s.close()
    return hello, out, dt


if __name__ == "__main__":
    a = sys.argv[1:]
    name = a[0]
    ints = []
    string = None
    nreply = 1
    for x in a[1:]:
        if x.startswith("s="):
            string = x[2:]
        elif x.startswith("n="):
            nreply = int(x[2:])
        else:
            ints.append(int(x))
    h, out, dt = call(name, ints, string, nreply)
    print("%s hello=%d reply=%s %.3fs" % (name, h, out, dt))
