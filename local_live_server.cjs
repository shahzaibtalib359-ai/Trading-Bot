const http = require("http")
const fs = require("fs")
const path = require("path")
const { handler } = require("./netlify/functions/api.cjs")

const root = path.join(__dirname, "dist")
const port = Number(process.env.PORT || 8899)

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.url.startsWith("/api/")) {
      const body = await readBody(req)
      const response = await handler({
        httpMethod: req.method,
        path: req.url.split("?")[0],
        body,
        headers: req.headers,
      })
      res.writeHead(response.statusCode, response.headers)
      res.end(response.body)
      return
    }

    const requested = decodeURIComponent(req.url.split("?")[0])
    const candidate = path.normalize(path.join(root, requested === "/" ? "index.html" : requested))
    const filePath = candidate.startsWith(root) && fs.existsSync(candidate) && fs.statSync(candidate).isFile()
      ? candidate
      : path.join(root, "index.html")
    const ext = path.extname(filePath)
    res.writeHead(200, { "content-type": mimeTypes[ext] || "application/octet-stream" })
    fs.createReadStream(filePath).pipe(res)
  } catch (error) {
    res.writeHead(500, { "content-type": "application/json" })
    res.end(JSON.stringify({ detail: error instanceof Error ? error.message : "Local server error" }))
  }
})

server.listen(port, "127.0.0.1", () => {
  console.log(`Local live app running at http://127.0.0.1:${port}`)
})

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on("data", (chunk) => chunks.push(chunk))
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")))
    req.on("error", reject)
  })
}
