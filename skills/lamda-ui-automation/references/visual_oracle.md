# Read-only visual oracle

Use only after deterministic XML/state checks pass. The model sees a screenshot and returns a boolean/value; it must never touch the device.

## Requirements

- Node 20+
- `npm install @midscene/core@1.13.3`
- A vision-capable model configured in `MIDSCENE_MODEL_*`

## Minimal `oracle.mjs`

```js
import fs from 'node:fs';
import { Agent } from '@midscene/core';

const [screenshot, size, prompt] = process.argv.slice(2);
if (!screenshot || !size || !prompt) {
  throw new Error('usage: node oracle.mjs <shot.jpg> <WxH> <prompt>');
}

const [width, height] = size.split('x').map(Number);
const b64 = fs.readFileSync(screenshot).toString('base64');

const iface = {
  interfaceType: 'static-screenshot',
  screenshotBase64: async () => b64,
  size: async () => ({ width, height }),
  actionSpace: () => [],
};

const agent = new Agent(iface, { generateReport: false });
const result = await agent.aiAssert(prompt, undefined, {
  domIncluded: false,
  keepRawResponse: true,
});

console.log(JSON.stringify({
  pass: result?.pass === true,
  thought: result?.thought ?? null,
  message: result?.message ?? null,
}, null, 2));
```

Run:

```bash
export MIDSCENE_MODEL_NAME="deepseek-flash"
export MIDSCENE_MODEL_FAMILY="deepseek"
export MIDSCENE_MODEL_BASE_URL="https://api.deepseek.com"
export MIDSCENE_MODEL_API_KEY="..."

node oracle.mjs captures/screen.jpg 1080x2400 \
  "当前是手机号登录页，包含“请输入手机号码”输入框和国家码 86"
```

## Contract

- `actionSpace: []` — no click/type/navigation tools.
- `domIncluded: false` — pixels only, no hidden DOM.
- One screenshot per assertion.
- Record the prompt, pass/reject, thought, and token usage.
- Never use the oracle to decide an action; use LAMDA selectors for actions.
- If the oracle errors, fail the test as an infrastructure error, not as an app assertion failure.

## When not to use it

- XML/text can prove the condition: use deterministic assertions first.
- Payment/destructive flows: require explicit user approval and sandbox data.
- Pixel-perfect visual regression: this is semantic assertion, not image diff. Add a baseline/diff step separately if needed.
