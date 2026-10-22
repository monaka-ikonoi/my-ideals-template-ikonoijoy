import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';

const templateFiles = [
  { file: 'equal-love.json', script: 'split-template.js' },
  { file: 'not-equal-me.json', script: 'split-template.js' },
  { file: 'nearly-equal-joy.json', script: 'split-template.js' },
  { file: 'equal-love-mini-photo.json', script: 'filter-normal-card.js' },
  { file: 'not-equal-me-mini-photo.json', script: 'filter-normal-card.js' },
  { file: 'nearly-equal-joy-mini-photo.json', script: 'filter-normal-card.js' },
  { file: 'equal-love-id-photo.json' },
  { file: 'not-equal-me-id-photo.json' },
  { file: 'nearly-equal-joy-id-photo.json' },
];
const productionBaseUrl = 'https://my-ideals-ikonoijoy-prod.chocomonaka.dev';
const imageBaseUrl = `${productionBaseUrl}/images`;
const templateBaseUrl = `${productionBaseUrl}/templates`;

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));

/** Build a complete, local publish bundle; this function never uploads anything. */
export async function preparePublish({
  sourceDir = path.dirname(scriptsDir),
  outputDir,
} = {}) {
  const imagesDir = path.join(outputDir, 'images');
  const templatesDir = path.join(outputDir, 'templates');
  await mkdir(imagesDir, { recursive: true });
  await mkdir(templatesDir, { recursive: true });
  let imageCount = 0;
  let missingImageCount = 0;

  for (const { file: filename, script } of templateFiles) {
    const stem = path.basename(filename, '.json');
    const template = JSON.parse(await readFile(path.join(sourceDir, filename), 'utf8'));
    const { format } = template.imageBaseUrl;
    template.imageBaseUrl.root = `${imageBaseUrl}/${stem}`;

    for (const collection of template.collections) {
      const collectionDir = path.join(imagesDir, stem, collection.id);
      await mkdir(collectionDir, { recursive: true });
      for (const item of collection.items) {
        // A supplied URL takes priority in the client. Never keep a stale source hash.
        delete item.imageHash;
        if (item.image) continue;

        const sourceImage = path.join(
          sourceDir,
          'resources',
          stem,
          collection.id,
          `${item.id}.${format}`,
        );
        let bytes;
        try {
          bytes = await readFile(sourceImage);
        } catch (error) {
          if (error.code !== 'ENOENT') throw error;
          missingImageCount += 1;
          continue;
        }
        item.imageHash = createHash('sha256').update(bytes).digest('hex').slice(0, 16);
        const imagePath = path.join(collectionDir, `${item.id}.${item.imageHash}.${format}`);
        await writeFile(imagePath, bytes);
        imageCount += 1;
      }
    }

    const templatePath = path.join(templatesDir, filename);
    await writeFile(templatePath, JSON.stringify(template));
    if (script) {
      execFileSync(process.execPath, [path.join(scriptsDir, script), templatePath, templatesDir]);
    }
  }

  const filenames = (await readdir(templatesDir)).filter(filename => filename.endsWith('.json'));
  for (const filename of filenames) {
    const templatePath = path.join(templatesDir, filename);
    const template = JSON.parse(await readFile(templatePath, 'utf8'));
    await writeFile(templatePath, JSON.stringify(template));
  }

  const manifest = JSON.parse(await readFile(path.join(sourceDir, 'manifest.json'), 'utf8'));
  for (const entry of manifest.templates) {
    if (entry.link === null) continue;
    const url = new URL(entry.link);
    if (!['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) continue;
    const filename = decodeURIComponent(url.pathname.replace(/^\//, ''));
    entry.link = `${templateBaseUrl}/${filename}${url.search}${url.hash}`;
  }
  await writeFile(path.join(outputDir, 'manifest.json'), JSON.stringify(manifest));

  if (missingImageCount > 0) {
    console.warn(
      `${missingImageCount} image(s) are missing locally; those items keep their unhashed fallback URL.`,
    );
  }
  return { templateCount: filenames.length, imageCount, missingImageCount };
}

async function main() {
  const { values } = parseArgs({
    options: {
      'source-dir': { type: 'string' },
      'output-dir': { type: 'string' },
      help: { type: 'boolean', short: 'h' },
    },
  });
  if (values.help) {
    console.log(
      'Usage: node scripts/prepare-publish.mjs --output-dir <path> [--source-dir <path>]',
    );
    return;
  }
  const summary = await preparePublish({
    sourceDir: values['source-dir'],
    outputDir: values['output-dir'],
  });
  console.log(
    `Prepared ${summary.templateCount} templates and ${summary.imageCount} hashed images (${summary.missingImageCount} missing images).`,
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
