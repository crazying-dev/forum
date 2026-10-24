#!/usr/bin/env node
/**
 * 把 Next.js standalone 运行所需的静态资源复制进产出目录。
 *
 * 为什么必须有这一步：
 *   - `output: "standalone"` 生成的 .next/standalone/server.js 只服务【自身目录】内的文件：
 *       /_next/static/*   →  .next/standalone/.next/static/
 *       /assets/*、/manifest.json、/sw.js …  →  .next/standalone/public/
 *   - 而 `next build` 每次都会清空 .next（cleanDistDir: true），standalone 目录重新生成，
 *     其中【不含】public 与 static。漏复制 = 首页 HTML 正常返回、但所有 JS/CSS/图片 404
 *     （Next 直接回 9 字节 `Not Found`），页面白屏无样式。
 *
 * 因此打包动作挂在 package.json 的 postbuild 上，`pnpm build` 后自动执行，避免人工漏步。
 *
 * 用法：node scripts/prepare-standalone.mjs
 * 幂等：以 `src/. → dest/` 语义合并复制，可反复执行，不会嵌套成 public/public。
 */
import { cpSync, existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const standaloneRoot = join(webRoot, ".next", "standalone");

/** 源目录 → standalone 内目标目录 */
const JOBS = [
  { src: join(webRoot, "public"), dest: join(standaloneRoot, "public"), label: "public" },
  {
    src: join(webRoot, ".next", "static"),
    dest: join(standaloneRoot, ".next", "static"),
    label: ".next/static",
  },
];

const errors = [];

if (!existsSync(join(standaloneRoot, "server.js"))) {
  errors.push(
    `.next/standalone/server.js 不存在：请先执行 next build，并确认 next.config.ts 里 output: "standalone"`,
  );
}

/** 递归列出目录下所有文件（相对路径） */
function listFiles(root, prefix = "") {
  const out = [];
  for (const entry of readdirSync(join(root, prefix), { withFileTypes: true })) {
    const rel = prefix ? join(prefix, entry.name) : entry.name;
    if (entry.isDirectory()) out.push(...listFiles(root, rel));
    else if (entry.isFile()) out.push(rel);
  }
  return out;
}

for (const job of JOBS) {
  if (!existsSync(job.src) || !statSync(job.src).isDirectory()) {
    errors.push(`源目录不存在：${job.src}`);
    continue;
  }

  // src/. → dest/ ：目标已存在时按内容合并，保证幂等且不嵌套
  cpSync(job.src, job.dest, { recursive: true, force: true });

  const files = listFiles(job.src);
  const missing = files.filter((rel) => !existsSync(join(job.dest, rel)));
  if (missing.length > 0) {
    errors.push(
      `${job.label} 复制后校验失败：${missing.length}/${files.length} 个文件缺失，首个：${missing[0]}`,
    );
  } else {
    console.log(
      `[prepare-standalone] ${job.label} → ${relative(webRoot, job.dest)}（${files.length} 个文件）`,
    );
  }
}

if (errors.length > 0) {
  for (const message of errors) console.error(`[prepare-standalone][错误] ${message}`);
  console.error(
    "[prepare-standalone] 打包未完成：standalone 缺静态资源时，线上会首页 200 但 /_next/static/* 与 /assets/* 全部 404。",
  );
  process.exit(1);
}

console.log("[prepare-standalone] 完成：standalone 已含 static 与 public，可直接 node .next/standalone/server.js");
