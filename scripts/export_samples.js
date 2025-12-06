const fs = require('fs');
const path = require('path');

// Read the sampleData.ts file
const sampleDataPath = path.join(__dirname, '..', 'utils', 'sampleData.ts');
const content = fs.readFileSync(sampleDataPath, 'utf-8');

// Extract each DOC constant using regex
const docRegex = /const (DOC_\d+_\w+) = `([\s\S]*?)`;/g;
const docs = [];

let match;
while ((match = docRegex.exec(content)) !== null) {
  const name = match[1];
  const docContent = match[2];
  docs.push({ name, content: docContent });
}

// Create output directory
const outputDir = path.join(__dirname, '..', 'sample_documents');
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

// Map names to friendly filenames
const nameMap = {
  'DOC_1_METROPOLITAN': '01_Metropolitan_College_Foundation.md',
  'DOC_2_GLOBAL': '02_Global_Pension_Trust.md',
  'DOC_3_STATE': '03_State_University_Endowment_Fund.md',
  'DOC_4_TEACHERS': '04_Teachers_Retirement_System.md',
  'DOC_5_PACIFIC': '05_Pacific_Coast_Retirement_Fund.md',
  'DOC_6_HERITAGE': '06_Heritage_Insurance_Group.md',
  'DOC_7_NORDIC': '07_Nordic_Pension_Alliance.md',
  'DOC_8_SOVEREIGN': '08_Sovereign_Wealth_Partners.md',
};

// Write each document
docs.forEach(doc => {
  const filename = nameMap[doc.name] || `${doc.name}.md`;
  const filepath = path.join(outputDir, filename);
  fs.writeFileSync(filepath, doc.content);
  console.log(`Created: ${filename}`);
});

console.log(`\nExported ${docs.length} documents to ${outputDir}`);

