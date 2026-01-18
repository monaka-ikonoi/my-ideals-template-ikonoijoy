#!/usr/bin/env node
import 'dotenv/config';
import { S3Client, PutObjectCommand, HeadObjectCommand, ListObjectsV2Command } from '@aws-sdk/client-s3';
import { NodeHttpHandler } from '@smithy/node-http-handler';
import { createHash } from 'crypto';
import { readFileSync, statSync, readdirSync, existsSync, writeFileSync } from 'fs';
import { readFile } from 'fs/promises';
import { join, relative, extname } from 'path';
import { HttpsProxyAgent } from 'https-proxy-agent';

// ============== Configuration ==============
const CONFIG = {
  accountId: process.env.R2_ACCOUNT_ID,
  accessKeyId: process.env.R2_ACCESS_KEY_ID,
  secretAccessKey: process.env.R2_SECRET_ACCESS_KEY,
  bucketName: process.env.R2_BUCKET_NAME,

  cacheControl: 'public, max-age=31536000, immutable',
  supportedExtensions: ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.svg'],
  concurrency: 10,
  cacheFile: '.upload-cache.json',
};

const CONTENT_TYPES = {
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.avif': 'image/avif',
  '.svg': 'image/svg+xml',
};

// ============== Proxy Setup ==============
function createHttpHandler() {
  const proxyUrl = process.env.https_proxy || process.env.HTTPS_PROXY ||
                   process.env.http_proxy || process.env.HTTP_PROXY;

  if (proxyUrl) {
    console.log(`[INFO] Using proxy: ${proxyUrl}\n`);
    const agent = new HttpsProxyAgent(proxyUrl);
    return new NodeHttpHandler({
      httpAgent: agent,
      httpsAgent: agent,
    });
  }

  return new NodeHttpHandler();
}

// ============== S3 Client ==============
const client = new S3Client({
  region: 'auto',
  endpoint: `https://${CONFIG.accountId}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: CONFIG.accessKeyId,
    secretAccessKey: CONFIG.secretAccessKey,
  },
  requestHandler: createHttpHandler(),
});

// ============== Local Cache ==============
class UploadCache {
  constructor(cacheFile) {
    this.cacheFile = cacheFile;
    this.cache = this.load();
  }

  load() {
    if (existsSync(this.cacheFile)) {
      try {
        return JSON.parse(readFileSync(this.cacheFile, 'utf-8'));
      } catch {
        return { files: {} };
      }
    }
    return { files: {} };
  }

  save() {
    writeFileSync(this.cacheFile, JSON.stringify(this.cache, null, 2));
  }

  get(remotePath) {
    return this.cache.files[remotePath];
  }

  set(remotePath, hash, size) {
    this.cache.files[remotePath] = { hash, size, uploadedAt: new Date().toISOString() };
  }

  has(remotePath, hash) {
    const cached = this.cache.files[remotePath];
    return cached && cached.hash === hash;
  }
}

// ============== R2 Operations ==============
async function putObject(key, body, contentType) {
  const command = new PutObjectCommand({
    Bucket: CONFIG.bucketName,
    Key: key,
    Body: body,
    ContentType: contentType,
    CacheControl: CONFIG.cacheControl,
  });

  const response = await client.send(command);
  return response.ETag?.replace(/"/g, '');
}

async function headObject(key) {
  try {
    const command = new HeadObjectCommand({
      Bucket: CONFIG.bucketName,
      Key: key,
    });
    const response = await client.send(command);
    return {
      etag: response.ETag?.replace(/"/g, ''),
      size: response.ContentLength,
    };
  } catch (err) {
    if (err.name === 'NotFound' || err.$metadata?.httpStatusCode === 404) {
      return null;
    }
    throw err;
  }
}

async function listObjects(prefix) {
  const remoteFiles = new Map();
  let continuationToken;

  do {
    const command = new ListObjectsV2Command({
      Bucket: CONFIG.bucketName,
      Prefix: prefix || undefined,
      ContinuationToken: continuationToken,
    });

    const response = await client.send(command);

    for (const obj of response.Contents || []) {
      if (obj.Key && obj.ETag) {
        remoteFiles.set(obj.Key, obj.ETag.replace(/"/g, ''));
      }
    }

    continuationToken = response.NextContinuationToken;
  } while (continuationToken);

  return remoteFiles;
}

// ============== File Scanner ==============
function getImageFiles(dir, baseDir = dir) {
  const files = [];

  function scan(currentDir) {
    const entries = readdirSync(currentDir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = join(currentDir, entry.name);

      if (entry.isDirectory()) {
        scan(fullPath);
      } else if (entry.isFile()) {
        const ext = extname(entry.name).toLowerCase();
        if (CONFIG.supportedExtensions.includes(ext)) {
          const stat = statSync(fullPath);
          files.push({
            localPath: fullPath,
            relativePath: relative(baseDir, fullPath).replace(/\\/g, '/'),
            extension: ext,
            size: stat.size,
          });
        }
      }
    }
  }

  scan(dir);
  return files;
}

// ============== Utils ==============
function md5(buffer) {
  return createHash('md5').update(buffer).digest('hex');
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

// ============== Concurrency Control ==============
async function asyncPool(concurrency, items, fn) {
  const results = [];
  const executing = new Set();

  for (const item of items) {
    const promise = fn(item).then(result => {
      executing.delete(promise);
      return result;
    });

    results.push(promise);
    executing.add(promise);

    if (executing.size >= concurrency) {
      await Promise.race(executing);
    }
  }

  return Promise.all(results);
}

// ============== Main ==============
async function main() {
  const args = process.argv.slice(2);
  const flags = {
    force: args.includes('--force') || args.includes('-f'),
    dryRun: args.includes('--dry-run') || args.includes('-n'),
    help: args.includes('--help') || args.includes('-h'),
    noCache: args.includes('--no-cache'),
    listRemote: args.includes('--list-remote') || args.includes('-l'),
  };

  const positionalArgs = args.filter(a => !a.startsWith('-'));
  const localDir = positionalArgs[0];
  const remotePrefix = positionalArgs[1] || '';

  // Help message
  if (flags.help || !localDir) {
    console.log(`
R2 Image Uploader (AWS SDK)

Usage:
  node upload-to-r2.mjs <directory> [prefix] [options]
  npm run upload -- <directory> [prefix] [options]

Options:
  -f, --force       Force upload all files (ignore cache and remote check)
  -n, --dry-run     Preview without uploading
  -l, --list-remote List remote files before upload (more accurate but slower)
  --no-cache        Don't use local cache file
  -h, --help        Show help

Examples:
  node upload-to-r2.mjs ./images
  node upload-to-r2.mjs ./images gallery
  node upload-to-r2.mjs ./images gallery --dry-run
  node upload-to-r2.mjs ./images gallery --force
  node upload-to-r2.mjs ./images gallery --list-remote

Environment Variables:
  R2_ACCOUNT_ID        Cloudflare Account ID
  R2_ACCESS_KEY_ID     R2 Access Key ID
  R2_SECRET_ACCESS_KEY R2 Secret Access Key
  R2_BUCKET_NAME       R2 Bucket Name

Proxy Support:
  http_proxy / https_proxy / HTTP_PROXY / HTTPS_PROXY
`);
    process.exit(0);
  }

  // Check environment variables
  const missing = [];
  if (!CONFIG.accountId) missing.push('R2_ACCOUNT_ID');
  if (!CONFIG.accessKeyId) missing.push('R2_ACCESS_KEY_ID');
  if (!CONFIG.secretAccessKey) missing.push('R2_SECRET_ACCESS_KEY');
  if (!CONFIG.bucketName) missing.push('R2_BUCKET_NAME');

  if (missing.length > 0) {
    console.error(`[ERROR] Missing environment variables: ${missing.join(', ')}`);
    console.error('[INFO] Create a .env file or set environment variables.');
    process.exit(1);
  }

  // Check directory
  try {
    const stat = statSync(localDir);
    if (!stat.isDirectory()) {
      console.error(`[ERROR] Not a directory: ${localDir}`);
      process.exit(1);
    }
  } catch {
    console.error(`[ERROR] Directory not found: ${localDir}`);
    process.exit(1);
  }

  console.log('[INFO] Scanning for images...\n');
  const files = getImageFiles(localDir);

  if (files.length === 0) {
    console.log('[WARN] No image files found.');
    process.exit(0);
  }

  // Statistics
  const totalSize = files.reduce((sum, f) => sum + f.size, 0);
  const extCounts = files.reduce((acc, f) => {
    acc[f.extension] = (acc[f.extension] || 0) + 1;
    return acc;
  }, {});

  console.log('Summary:');
  console.log(`  Files:  ${files.length} (${formatSize(totalSize)})`);
  console.log(`  Types:  ${Object.entries(extCounts).map(([e, c]) => `${e}(${c})`).join(', ')}`);
  console.log(`  Bucket: ${CONFIG.bucketName}`);
  console.log(`  Prefix: ${remotePrefix || '(root)'}`);
  if (flags.force) console.log('  Mode:   Force upload');
  if (flags.dryRun) console.log('  Mode:   Dry run');
  if (flags.listRemote) console.log('  Mode:   List remote files');
  console.log('');

  // Load cache
  const cache = flags.noCache ? null : new UploadCache(CONFIG.cacheFile);

  // Optionally fetch remote file list
  let remoteFiles = null;
  if (flags.listRemote && !flags.force) {
    console.log('[INFO] Fetching remote file list...');
    remoteFiles = await listObjects(remotePrefix);
    console.log(`[INFO] Found ${remoteFiles.size} files on R2\n`);
  }

  // Upload tracking
  const results = { uploaded: 0, skipped: 0, failed: 0 };
  let processed = 0;
  const startTime = Date.now();

  const showProgress = () => {
    const pct = ((processed / files.length) * 100).toFixed(1);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    process.stdout.write(
      `\r[PROGRESS] ${processed}/${files.length} (${pct}%) | uploaded:${results.uploaded} skipped:${results.skipped} failed:${results.failed} | ${elapsed}s`
    );
  };

  // Process single file
  const processFile = async (file) => {
    const remotePath = remotePrefix
      ? `${remotePrefix}/${file.relativePath}`
      : file.relativePath;

    try {
      const buffer = await readFile(file.localPath);
      const localHash = md5(buffer);

      // Check if upload is needed
      if (!flags.force) {
        // Check local cache first
        if (cache && cache.has(remotePath, localHash)) {
          results.skipped++;
          return;
        }

        // Check remote file
        if (remoteFiles) {
          // Use pre-fetched list
          const remoteHash = remoteFiles.get(remotePath);
          if (remoteHash === localHash) {
            if (cache) cache.set(remotePath, localHash, file.size);
            results.skipped++;
            return;
          }
        } else {
          // Check individual file
          const remote = await headObject(remotePath);
          if (remote && remote.etag === localHash) {
            if (cache) cache.set(remotePath, localHash, file.size);
            results.skipped++;
            return;
          }
        }
      }

      // Upload file
      if (!flags.dryRun) {
        const contentType = CONTENT_TYPES[file.extension] || 'application/octet-stream';
        await putObject(remotePath, buffer, contentType);
        if (cache) cache.set(remotePath, localHash, file.size);
      }

      results.uploaded++;

    } catch (err) {
      results.failed++;
      console.error(`\n[ERROR] ${file.relativePath}: ${err.message}`);
    } finally {
      processed++;
      showProgress();
    }
  };

  // Run concurrent uploads
  await asyncPool(CONFIG.concurrency, files, processFile);

  // Save cache
  if (cache && !flags.dryRun) {
    cache.save();
  }

  // Show results
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log('\n\nResults:');
  console.log(`  Uploaded: ${results.uploaded}`);
  console.log(`  Skipped:  ${results.skipped}`);
  console.log(`  Failed:   ${results.failed}`);
  console.log(`  Time:     ${elapsed}s`);

  // Save manifest
  if (results.uploaded > 0 && !flags.dryRun) {
    const manifest = {
      uploadedAt: new Date().toISOString(),
      bucket: CONFIG.bucketName,
      prefix: remotePrefix,
      stats: results,
    };
    writeFileSync('upload-manifest.json', JSON.stringify(manifest, null, 2));
    console.log('\n[INFO] Manifest saved to: upload-manifest.json');
  }
}

main().catch(err => {
  console.error('[FATAL]', err.message);
  process.exit(1);
});
