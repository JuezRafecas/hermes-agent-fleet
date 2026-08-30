#!/usr/bin/env node
// Upload temporary human-facing artifacts to an S3-compatible shared prefix.
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { readFileSync, statSync, readdirSync } from "node:fs";
import { basename, join, extname, relative } from "node:path";

const need = (key) => {
  const value = (process.env[key] || "").trim();
  if (!value) {
    console.error(`missing ${key}`);
    process.exit(2);
  }
  return value;
};

const endpoint = need("S3_ENDPOINT");
const bucket = need("S3_BUCKET");
const publicBase = need("SHARE_PUBLIC_URL").replace(/\/$/, "");
const client = new S3Client({
  region: process.env.S3_REGION || "auto",
  endpoint,
  credentials: {
    accessKeyId: need("S3_ACCESS_KEY_ID"),
    secretAccessKey: need("S3_SECRET_ACCESS_KEY"),
  },
});

const args = process.argv.slice(2);
let uploadName = null;
let uploadDirectory = null;
let source = null;
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === "--name") uploadName = args[++index];
  else if (args[index] === "--dir") uploadDirectory = args[++index];
  else source = args[index];
}
if (!source) {
  console.error("usage: shared-file-upload <file-or-directory> [--name name] [--dir subdirectory]");
  process.exit(2);
}

const safe = (value) => value.replace(/[^A-Za-z0-9._/-]/g, "-");
const profile = (
  process.env.HERMES_SESSION_PROFILE
  || process.env.HERMES_PROFILE
  || process.env.HERMES_PROFILE_NAME
  || basename(process.env.HERMES_HOME || "")
  || "default"
).replace(/[^a-z0-9_-]/gi, "-").toLowerCase() || "default";
const day = new Date().toISOString().slice(0, 10).replace(/-/g, "");
const prefix = ["shared", profile, day, uploadDirectory ? safe(uploadDirectory) : null]
  .filter(Boolean)
  .join("/");
const expires = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
const contentTypes = {
  html: "text/html; charset=utf-8",
  htm: "text/html; charset=utf-8",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  gif: "image/gif",
  svg: "image/svg+xml",
  mp4: "video/mp4",
  webm: "video/webm",
  pdf: "application/pdf",
  json: "application/json",
  csv: "text/csv; charset=utf-8",
  txt: "text/plain; charset=utf-8",
  md: "text/markdown; charset=utf-8",
  js: "text/javascript; charset=utf-8",
  css: "text/css; charset=utf-8",
};

async function put(file, key) {
  const extension = extname(file).slice(1).toLowerCase();
  await client.send(new PutObjectCommand({
    Bucket: bucket,
    Key: key,
    Body: readFileSync(file),
    ContentType: contentTypes[extension] || "application/octet-stream",
    CacheControl: "public, max-age=300",
    Expires: expires,
    Tagging: "retention=30d",
  }));
  return `${publicBase}/${key}`;
}

function walk(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => (
    entry.isDirectory() ? walk(join(directory, entry.name)) : [join(directory, entry.name)]
  ));
}

if (statSync(source).isDirectory()) {
  let indexUrl = null;
  for (const file of walk(source)) {
    const url = await put(file, `${prefix}/${safe(relative(source, file))}`);
    if (basename(file) === "index.html") indexUrl = url;
    console.error("uploaded", url);
  }
  console.log(indexUrl || `${publicBase}/${prefix}/`);
} else {
  console.log(await put(source, `${prefix}/${safe(uploadName || basename(source))}`));
}
