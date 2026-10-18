#!/usr/bin/env node
/**
 * 校验 openapi.yaml 覆盖 router.go 与 legacy.go 中的全部端点。
 * 用法：node scripts/check-api-docs.mjs（从 yj-forum-ouo 根目录运行）
 */
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const router = read('server/internal/handler/router.go');
const legacy = read('server/internal/handler/legacy.go');
const openapi = read('docs/api/openapi.yaml');

const re = /\bapi\.(GET|POST|PUT|PATCH|DELETE)\("([^"]+)"/g;
const paths = new Set();
for (const m of router.matchAll(re)) paths.add('/ov2/api' + m[2]);
for (const m of legacy.matchAll(re)) paths.add('/api' + m[2]);

const toOas = (p) => p.replace(/:([A-Za-z0-9_]+)/g, '{$1}');
const missing = [...paths].filter((p) => !openapi.includes(`  ${toOas(p)}:`));

if (missing.length) {
  console.error(`[api-docs] ${missing.length} 个端点未出现在 openapi.yaml：`);
  for (const p of missing) console.error('  - ' + toOas(p));
  process.exit(1);
}
console.log(`[api-docs] OK：${paths.size} 个端点全部覆盖`);
