// Oodle (Mermaid/Kraken) decompression helper for pbzsave.py.
// Usage: node ooz_decode.mjs <oozextract_dir> <jobs.json>
// jobs.json: [{"in": path, "out": path, "size": uncompressed_size}, ...]
// <oozextract_dir> holds oozextract.js + oozextract_bg.wasm (oozextract 0.5.7, MIT),
// installed by setup_oodle.sh; pbzsave.py verifies the wasm SHA-256 before calling this.
import fs from 'fs';
import path from 'path';
import { pathToFileURL } from 'url';

const [dir, jobsPath] = process.argv.slice(2);
const mod = await import(pathToFileURL(path.join(dir, 'oozextract.js')).href);
await mod.default({ module_or_path: fs.readFileSync(path.join(dir, 'oozextract_bg.wasm')) });
for (const job of JSON.parse(fs.readFileSync(jobsPath, 'utf8'))) {
  const x = mod.Extractor.new();
  try {
    const out = x.extract(fs.readFileSync(job.in), job.size);
    if (out.length !== job.size) throw new Error(`size mismatch for ${job.in}`);
    fs.writeFileSync(job.out, out);
  } finally {
    x.free();
  }
}
