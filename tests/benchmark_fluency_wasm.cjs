// Full-resolution browser/worker benchmark; requires an existing Playwright installation.
// Run against the canonical production build; no module injection or source modification.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const reportPath = process.env.FLUENCY_REPORT || '/tmp/flowgraph-fluency-packaged-profile.json';

(async () => {
  const bytes = fs.readFileSync(path.join(__dirname, '../src/flowgraph/testdata/ColorCardboard.jpg'));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    page.on('console', msg => console.log(msg.text()));
    await page.goto(`${process.env.FLOWGRAPH_URL || 'http://localhost:8082'}/favicon.svg`);
    const report = await page.evaluate(async ({ base64 }) => {
      const { PythonExecutor } = await import('/python-executor.js');
      const executor = new PythonExecutor();
      const report = { runs: [], timeoutMs: executor.timeoutMs, width: 2850, height: 2484, resized: false };
      try {
        const start = performance.now();
        await executor.warmup();
        report.warmupMs = performance.now() - start;
        await executor.writeFile('/tmp/flowgraph-user-data/ColorCardboard.jpg', Uint8Array.from(atob(base64), c => c.charCodeAt(0)).buffer);
        for (let round = 1; round <= 3; round++) {
          for (const ports of [['contrast', 'complexity', 'self_similarity', 'symmetry_horizontal'], ['symmetry_vertical']]) {
            const inner = {
              format: 'flowgraph-workflow', version: 3, inputs: [], outputs: [],
              nodes: [
                { id: 'path', definition_id: 'set-string', parameters: { value: '/tmp/flowgraph-user-data/ColorCardboard.jpg' } },
                { id: 'read', definition_id: 'read-image', parameters: { path: '/tmp/flowgraph-user-data/Label 8.png' } },
                { id: 'metrics', definition_id: 'image-fluency-metrics', parameters: { complexity_rotate: false, self_similarity_full: false, symmetry_shift_range: 0.05 } },
                ...ports.map(port => ({ id: `show-${port}`, definition_id: 'show-value', parameters: {} })),
              ],
              edges: [
                { source_node: 'path', source_port: 'value', target_node: 'read', target_port: 'path' },
                { source_node: 'read', source_port: 'image', target_node: 'metrics', target_port: 'image' },
                ...ports.map(port => ({ source_node: 'metrics', source_port: port, target_node: `show-${port}`, target_port: 'value' })),
              ],
            };
            const code = `def Execute() -> tuple[str]:
    import json
    from time import perf_counter
    from flowgraph.adapters import image_tools
    from flowgraph.application.workflow_execution import execute_workflow_json
    timings = {}
    counts = {}
    originals = {}
    def wrap(name):
        original = getattr(image_tools, name)
        originals[name] = original
        def measured(*args, **kwargs):
            key = args[1] if name == '_mirror_similarity' else name
            start = perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                timings[key] = timings.get(key, 0.0) + perf_counter() - start
                counts[key] = counts.get(key, 0) + 1
        setattr(image_tools, name, measured)
    for name in ('_metric_channels', '_rms_contrast', '_self_similarity_channel', '_mirror_similarity', '_compression_complexity'):
        wrap(name)
    start = perf_counter()
    try:
        response = json.loads(execute_workflow_json(${JSON.stringify(JSON.stringify(inner))}))
    finally:
        elapsed = perf_counter() - start
        for name, original in originals.items():
            setattr(image_tools, name, original)
    if response['status'] != 'ok':
        raise RuntimeError(str(response))
    from PIL import Image
    with Image.open('/tmp/flowgraph-user-data/ColorCardboard.jpg') as image:
        size = image.size
    return (json.dumps({'seconds': timings, 'calls': counts, 'workflowSeconds': elapsed, 'outputs': response['nodes']['outputs']['metrics'], 'size': size, 'executedNodes': response['execution_order']}),)
`;
            const outer = { format: 'flowgraph-workflow', version: 3, inputs: [], outputs: [], edges: [], nodes: [{ id: 'profile', definition_id: 'user-function', parameters: { code } }] };
            console.log(`PROFILE_START round=${round} ports=${ports.join(',')}`);
            const before = performance.now();
            const response = await executor.execute(JSON.stringify(outer));
            if (response.status !== 'ok') throw new Error(JSON.stringify(response));
            const result = JSON.parse(Object.values(response.nodes.outputs.profile)[0]);
            if (result.size[0] !== 2850 || result.size[1] !== 2484) throw new Error('Dimensions changed');
            report.runs.push({ round, ports, requestMs: performance.now() - before, ...result });
            console.log(`PROFILE_RESULT ${JSON.stringify(report.runs.at(-1))}`);
          }
        }
        return report;
      } finally { executor.dispose(); }
    }, { base64: bytes.toString('base64') });
    assert.equal(report.runs.length, 6);
    report.browser = await browser.version();
    for (const run of report.runs) {
      const expected = { contrast: 0.23056522442221628, complexity: 0.4780461269010887, self_similarity: -0.9260709412666948, symmetry_horizontal: 0.09835141271341244, symmetry_vertical: 0.13342087298643024 };
      for (const port of run.ports) assert.ok(Math.abs(run.outputs[port] - expected[port]) < 5e-12, `${port}: ${run.outputs[port]}`);
    }
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });