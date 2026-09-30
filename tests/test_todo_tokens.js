// PRO·FREE 투두 입력의 날짜·시간 칩 인식 규칙을 검증하는 테스트
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

for (const edition of ['PRO', 'FREE']) {
  const file = `${edition}/templates/index.html`;
  const html = fs.readFileSync(file, 'utf8');
  assert(
    /<span class="d">\$\{d\}<\/span><span class="cal-cnt">\$\{cnt\}건<\/span>/.test(html),
    `${edition} 일간 달력은 일정이 없는 날짜에도 0건을 표시해야 합니다.`,
  );
  const block = html.match(/const TODO_EDITOR_HOUR=[\s\S]*?(?=function placeTodoCaretEnd)/);
  assert(block, `${edition} 투두 토큰 파서 코드를 찾을 수 없습니다.`);

  const context = {};
  vm.runInNewContext(`${block[0]}; this.todoParsePrefix = todoParsePrefix;`, context, {filename: file});
  const cases = [
    ['7월 15일 ', [{type: 'date', value: '7월 15일'}], ''],
    ['17일 ', [{type: 'date', value: '7월 17일'}], ''],
    ['17일 8시에 ', [{type: 'date', value: '7월 17일'}, {type: 'time', value: '8시'}], ''],
    ['17일 8시에 약속', [{type: 'date', value: '7월 17일'}, {type: 'time', value: '8시'}], '약속'],
    ['7월 17일 8시에 ', [{type: 'date', value: '7월 17일'}, {type: 'time', value: '8시'}], ''],
    ['07-15 09시~10시 ', [{type: 'date', value: '07-15'}, {type: 'time', value: '09시~10시'}], ''],
    ['07/15 09:00~10:00 점심식사', [{type: 'date', value: '07/15'}, {type: 'time', value: '09:00~10:00'}], '점심식사'],
    ['아홉시까지 ', [{type: 'time', value: '아홉시까지'}], ''],
    ['12시까지 제출', [{type: 'time', value: '12시까지'}], '제출'],
    ['32일 약속', [], '32일 약속'],
    ['02/30 약속', [], '02/30 약속'],
    ['17일간 작업', [], '17일간 작업'],
    ['7월 17일간 작업', [], '7월 17일간 작업'],
    ['8시간 작업', [], '8시간 작업'],
    ['8시에너지 연구', [], '8시에너지 연구'],
    ['일반 할 일', [], '일반 할 일'],
  ];
  for (const [input, tokens, rest] of cases) {
    const parsed = context.todoParsePrefix(input, '2026-07-16');
    assert.deepStrictEqual(JSON.parse(JSON.stringify(parsed.tokens)), tokens, `${edition}: ${input}`);
    assert.strictEqual(parsed.rest, rest, `${edition}: ${input}`);
  }
  console.log(`PASS todo token cases: ${edition} (${cases.length})`);
}
