'use strict';

const { spawn } = require('child_process');
const { runMock } = require('./mockBob');

/**
 * Runs a prompt against Bob Shell (`bob run --format json "<prompt>"`).
 *
 * Real mode shells out to the actual `bob` binary (requires Bob Shell
 * installed locally and BOB_API_KEY set in the environment).
 *
 * Mock mode is used automatically when:
 *   - process.env.BOB_MOCK === 'true', or
 *   - the `bob` binary isn't found on PATH
 * It does NOT fake intelligence blindly — it reads the actual files
 * referenced via @path in the prompt and builds its response from
 * their real content, so wrapper logic (prompt construction, JSON
 * parsing, drift scoring) can be validated end-to-end without a live
 * Bob Shell install.
 *
 * @param {string} prompt - The prompt text, may include @path references.
 * @param {object} [opts]
 * @param {string} [opts.cwd] - Working directory for resolving @path refs.
 * @param {boolean} [opts.forceMock] - Force mock mode regardless of env/binary.
 * @returns {Promise<{last_message: string, tokens: object, cost: object, mocked: boolean}>}
 */
async function runBob(prompt, opts = {}) {
  const cwd = opts.cwd || process.cwd();
  const forceMock = !!opts.forceMock;
  const envMock = process.env.BOB_MOCK === 'true';

  if (forceMock || envMock) {
    return runMock(prompt, { cwd });
  }

  const binaryAvailable = await checkBobBinary();
  if (!binaryAvailable) {
    // Fall back to mock, but flag it clearly so callers/logs know
    // this wasn't a real Bob response.
    const result = await runMock(prompt, { cwd });
    result.fallbackReason = 'bob binary not found on PATH';
    return result;
  }

  return new Promise((resolve, reject) => {
    const child = spawn('bob', ['run', '--format', 'json', prompt], {
      cwd,
      env: process.env, // carries BOB_API_KEY through
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });

    child.on('error', (err) => {
      reject(new Error(`Failed to spawn bob: ${err.message}`));
    });

    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`bob exited with code ${code}: ${stderr || 'no stderr output'}`));
        return;
      }
      try {
        const parsed = JSON.parse(stdout);
        parsed.mocked = false;
        resolve(parsed);
      } catch (err) {
        reject(new Error(`Failed to parse bob JSON output: ${err.message}\nRaw output: ${stdout}`));
      }
    });
  });
}

function checkBobBinary() {
  return new Promise((resolve) => {
    const check = spawn('bob', ['--version']);
    check.on('error', () => resolve(false));
    check.on('close', (code) => resolve(code === 0));
  });
}

module.exports = { runBob };
