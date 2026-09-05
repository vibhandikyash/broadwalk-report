import { defineConfig } from 'vitest/config';

// The Angular builder hands Vitest absolute spec paths as glob patterns. When the checkout lives in a
// folder whose name contains glob metacharacters (parentheses, brackets, braces) those patterns match
// nothing and Vitest reports "No test files found". Escaping them here keeps `ng test` working anywhere.
export default defineConfig({
  plugins: [
    {
      name: 'escape-glob-metacharacters-in-test-include',
      configResolved(config) {
        const test = (config as unknown as { test?: { include?: string[] } }).test;
        if (test?.include) test.include = test.include.map((p) => p.replace(/[()[\]{}]/g, (m) => '\\' + m));
      },
    },
  ],
});
