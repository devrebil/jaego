// PRO·FREE 화면의 인라인 JavaScript 문법을 일괄 검사하는 스크립트
const fs = require('fs');

for (const edition of ['PRO', 'FREE']) {
  const html = fs.readFileSync(`${edition}/templates/index.html`, 'utf8');
  const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(match => match[1]);
  scripts.forEach(script => new Function(script));
  console.log(`inline scripts parsed: ${edition} ${scripts.length}`);
}
