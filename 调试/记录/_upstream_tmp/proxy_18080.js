const http = require('node:http');

http.createServer((request, response) => {
  const upstream = http.request({
    host: '127.0.0.1', port: 8080,
    path: request.url, method: request.method,
    headers: request.headers,
  }, result => {
    process.stdout.write(`${request.method} ${request.url} ${result.statusCode}\n`);
    response.writeHead(result.statusCode, result.headers);
    result.pipe(response);
  });
  upstream.on('error', error => {
    process.stderr.write(`${request.method} ${request.url} ${error.message}\n`);
    if (!response.headersSent) response.writeHead(502);
    response.end();
  });
  request.pipe(upstream);
}).listen(18080, '192.168.0.20', () => process.stdout.write('proxy 192.168.0.20:18080 -> 127.0.0.1:8080\n'));
