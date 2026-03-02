import * as fs from 'fs';
import * as path from 'path';

function filterNormalCards(inputPath, outputDir) {
  const template = JSON.parse(fs.readFileSync(inputPath, 'utf-8'));

  fs.mkdirSync(outputDir, { recursive: true });

  const normalTemplate = {
    ...template,
    id: `${template.id}-normal`,
    name: `${template.name} - ノーマル`,
    collections: template.collections.map(collection => ({
      ...collection,
      items: collection.items.filter(item => !item.id.includes('rare'))
    })),
  }
  normalTemplate.layout.columns = [3, 5, 10];

  const filename = `${template.id}-normal.json`;
  const filepath = path.join(outputDir, filename);
  fs.writeFileSync(filepath, JSON.stringify(normalTemplate, null, 2));

  const itemCount = normalTemplate.collections.reduce((sum, c) => sum + c.items.length, 0);
  console.log(`✓ ${filename} (${itemCount} items)`);
}

const args = process.argv.slice(2);

if (args.length < 2) {
  console.error('Usage: node filter-normal-card.js <input.json> <output-dir>');
  console.error('Example: node filter-normal-card.js template.json ./dist');
  process.exit(1);
}

const [inputPath, outputDir] = args;

if (!fs.existsSync(inputPath)) {
  console.error(`Error: File not found: ${inputPath}`);
  process.exit(1);
}

filterNormalCards(inputPath, outputDir);
