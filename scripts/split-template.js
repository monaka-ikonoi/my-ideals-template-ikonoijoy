import * as fs from 'fs';
import * as path from 'path';

function splitTemplateByMember(inputPath, outputDir) {
  const template = JSON.parse(fs.readFileSync(inputPath, 'utf-8'));

  fs.mkdirSync(outputDir, { recursive: true });

  for (const member of template.members) {
    const memberTemplate = {
      ...template,
      id: `${template.id}-${member.id}`,
      name: `${template.name} - ${member.name}`,
      members: [member],
      collections: template.collections
        .map(collection => ({
          ...collection,
          items: collection.items.filter(item => typeof item.member === 'string' && item.member === member.id),
        }))
        .filter(collection => collection.items.length > 0),
    };

    const filename = `${template.id}-${member.id}.json`;
    const filepath = path.join(outputDir, filename);
    fs.writeFileSync(filepath, JSON.stringify(memberTemplate, null, 2));

    const itemCount = memberTemplate.collections.reduce((sum, c) => sum + c.items.length, 0);
    console.log(`✓ ${filename} (${itemCount} items)`);
  }

  console.log(`\nDone! Generated ${template.members.length} files in ${outputDir}`);
}

const args = process.argv.slice(2);

if (args.length < 2) {
  console.error('Usage: tsx split-template.ts <input.json> <output-dir>');
  console.error('Example: tsx split-template.ts template.json ./dist');
  process.exit(1);
}

const [inputPath, outputDir] = args;

if (!fs.existsSync(inputPath)) {
  console.error(`Error: File not found: ${inputPath}`);
  process.exit(1);
}

splitTemplateByMember(inputPath, outputDir);
