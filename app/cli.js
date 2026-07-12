#!/usr/bin/env node
/**
 * 妖精论坛管理员客户端内核 - 命令行入口
 *
 * 用法:
 *   # 交互模式（推荐）
 *   node app/cli.js
 *
 *   # 命令行模式
 *   node app/cli.js reports
 *   node app/cli.js users
 *   node app/cli.js stats
 *   node app/cli.js post <post_id>
 *   node app/cli.js delete-post <post_id>
 *   node app/cli.js delete-comment <comment_id>
 *   node app/cli.js ban <user_id_or_name>
 *   node app/cli.js unban <user_id_or_name>
 *   node app/cli.js resolve-report <report_id>
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const AdminKernel = require('./admin_client.js');

let config = {};
const CONFIG_PATH = path.join(__dirname, '..', '.admin_config.json');

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const raw = fs.readFileSync(CONFIG_PATH, 'utf-8');
      config = JSON.parse(raw);
      return true;
    }
  } catch (e) {}
  return false;
}

function saveConfig() {
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), 'utf-8');
    return true;
  } catch (e) {
    return false;
  }
}

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function ask(question) {
  return new Promise(resolve => {
    rl.question(question, answer => resolve(answer));
  });
}

async function ensureConfig() {
  if (config.apiUrl && config.adminId && config.adminToken) {
    return true;
  }

  console.log('\n=== 首次配置 ===');
  config.apiUrl = config.apiUrl || (await ask('API 地址: ')).trim();
  config.adminId = config.adminId || (await ask('管理员 ID: ')).trim();
  config.adminToken = config.adminToken || (await ask('管理员令牌 (10位): ')).trim();

  if (!config.apiUrl || !config.adminId || !config.adminToken) {
    console.log('[错误] 配置不完整');
    return false;
  }

  const save = (await ask('保存配置到本地? [Y/n]: ')).trim().toLowerCase() || 'y';
  if (save === 'y' || save === 'yes') {
    saveConfig();
    console.log(`[信息] 配置已保存到 ${CONFIG_PATH}`);
  }

  return true;
}

function createKernel() {
  return new AdminKernel({
    apiUrl: config.apiUrl,
    adminId: config.adminId,
    adminToken: config.adminToken
  });
}

// ========================
// 打印工具
// ========================

function printReports(reports) {
  if (!reports || reports.length === 0) {
    console.log('[信息] 没有举报记录');
    return;
  }
  console.log(`\n共 ${reports.length} 条举报记录`);
  console.log('='.repeat(100));
  console.log(
    '#'.padEnd(5) +
    '举报ID'.padEnd(10) +
    '帖子ID'.padEnd(20) +
    '帖子标题'.padEnd(20) +
    '举报人'.padEnd(14) +
    '原因'.padEnd(12) +
    '状态'.padEnd(8) +
    '时间'
  );
  console.log('-'.repeat(100));
  for (let i = 0; i < reports.length; i++) {
    const r = reports[i];
    const statusStr = r.status === 1 ? '已处理' : '待处理';
    const title = (r.post_title || '[已删除]').substring(0, 18);
    console.log(
      String(i + 1).padEnd(5) +
      String(r.id).padEnd(10) +
      String(r.post_id).padEnd(20) +
      title.padEnd(20) +
      String(r.reporter_name || '[未知]').padEnd(14) +
      String(r.reason).padEnd(12) +
      statusStr.padEnd(8) +
      String(r.created_at || '')
    );
  }
  console.log('='.repeat(100));
}

function printUsers(users) {
  if (!users || users.length === 0) {
    console.log('[信息] 没有找到用户');
    return;
  }
  console.log(`\n共 ${users.length} 个用户`);
  console.log('='.repeat(110));
  console.log(
    '#'.padEnd(5) +
    '用户ID'.padEnd(22) +
    '用户名'.padEnd(16) +
    '邮箱'.padEnd(28) +
    'VIP'.padEnd(6) +
    '封禁'.padEnd(6) +
    '年龄'.padEnd(8) +
    '最后登录'
  );
  console.log('-'.repeat(110));
  for (let i = 0; i < users.length; i++) {
    const u = users[i];
    const banned = u.is_banned === 1 ? '是' : '否';
    console.log(
      String(i + 1).padEnd(5) +
      String(u.id).padEnd(22) +
      String(u.name).padEnd(16) +
      String(u.email || '').padEnd(28) +
      String(u.vip || '0').padEnd(6) +
      banned.padEnd(6) +
      String(u.age || '').padEnd(8) +
      String(u.last_login || '-')
    );
  }
  console.log('='.repeat(110));
}

function printPostDetail(post) {
  if (!post) {
    console.log('[信息] 帖子不存在');
    return;
  }
  const statusStr = post.status === 1 ? '正常' : '已删除';
  console.log('\n' + '='.repeat(60));
  console.log(`帖子ID:   ${post.id}`);
  console.log(`标题:     ${post.title}`);
  console.log(`作者:     ${post.user_name} (${post.user_id})`);
  console.log(`分类:     ${post.category}`);
  console.log(`状态:     ${statusStr}`);
  console.log(`点赞:     ${post.likes}  浏览: ${post.views}`);
  console.log(`创建时间: ${post.created_at}`);
  console.log(`更新时间: ${post.updated_at}`);
  console.log('-'.repeat(60));
  console.log(`内容:\n${post.content}`);
  console.log('='.repeat(60));
}

function printComments(comments) {
  if (!comments || comments.length === 0) {
    console.log('[信息] 没有评论');
    return;
  }
  console.log(`\n共 ${comments.length} 条评论`);
  console.log('='.repeat(90));
  console.log(
    '#'.padEnd(5) +
    '评论ID'.padEnd(20) +
    '用户名'.padEnd(14) +
    '状态'.padEnd(8) +
    '内容'.padEnd(30) +
    '时间'
  );
  console.log('-'.repeat(90));
  for (let i = 0; i < comments.length; i++) {
    const c = comments[i];
    const statusStr = c.status === 1 ? '正常' : '已删除';
    const content = (c.content || '').substring(0, 28);
    console.log(
      String(i + 1).padEnd(5) +
      String(c.id).padEnd(20) +
      String(c.user_name || '[未知]').padEnd(14) +
      statusStr.padEnd(8) +
      content.padEnd(30) +
      String(c.created_at || '')
    );
  }
  console.log('='.repeat(90));
}

function printStats(stats) {
  console.log('\n' + '='.repeat(40));
  console.log('  论坛统计信息');
  console.log('='.repeat(40));
  console.log(`  总用户数:     ${stats.users}`);
  console.log(`  帖子总数:     ${stats.posts}`);
  console.log(`  评论总数:     ${stats.comments}`);
  console.log(`  待处理举报:   ${stats.pending_reports}`);
  console.log(`  已封禁用户:   ${stats.banned_users}`);
  console.log('='.repeat(40));
}

async function confirm(prompt) {
  const ans = await ask(`${prompt} [y/N]: `);
  return ans.trim().toLowerCase() === 'y';
}

async function selectFromList(items, label = '序号') {
  if (!items || items.length === 0) return -1;
  if (items.length === 1) return 0;
  while (true) {
    const choice = await ask(`请输入${label} (1-${items.length}) 或 q 退出: `);
    const c = choice.trim();
    if (c.toLowerCase() === 'q') return -1;
    const idx = parseInt(c, 10);
    if (!isNaN(idx) && idx >= 1 && idx <= items.length) {
      return idx - 1;
    }
    console.log(`[错误] 请输入 1-${items.length} 之间的数字`);
  }
}

// ========================
// 交互模式子菜单
// ========================

async function cliReports(kernel) {
  console.log('\n--- 举报列表 ---');
  console.log('  1. 查看全部举报');
  console.log('  2. 查看待处理举报');
  console.log('  3. 查看已处理举报');
  const sub = (await ask('选择 (默认1): ')).trim() || '1';

  let status = null;
  if (sub === '2') status = 0;
  else if (sub === '3') status = 1;

  const reports = await kernel.listReports(status);
  printReports(reports);

  if (!reports || reports.length === 0) return;

  console.log('\n可执行操作:');
  console.log('  1. 查看帖子详情');
  console.log('  2. 删除被举报的帖子');
  console.log('  3. 标记举报为已处理');
  console.log('  0. 返回');
  const action = (await ask('选择: ')).trim();

  if (action === '1') {
    const idx = await selectFromList(reports);
    if (idx >= 0) {
      const post = await kernel.getPostDetail(reports[idx].post_id);
      printPostDetail(post);
    }
  } else if (action === '2') {
    const idx = await selectFromList(reports);
    if (idx >= 0) {
      const r = reports[idx];
      if (await confirm(`确认删除帖子 '${r.post_title}'?`)) {
        const result = await kernel.deletePost(r.post_id);
        console.log(result.success !== false ? '[成功] 帖子已删除' : '[失败] 删除失败');
      }
    }
  } else if (action === '3') {
    const idx = await selectFromList(reports);
    if (idx >= 0) {
      const ok = await kernel.resolveReport(reports[idx].id);
      console.log(ok ? '[成功] 举报已标记为已处理' : '[失败] 操作失败');
    }
  }
}

async function cliUsers(kernel) {
  console.log('\n--- 用户管理 ---');
  console.log('  1. 查看所有用户');
  console.log('  2. 查找用户');
  console.log('  3. 修改用户信息');
  console.log('  4. 封禁用户');
  console.log('  5. 解封用户');
  console.log('  0. 返回');
  const action = (await ask('选择: ')).trim();

  if (action === '1') {
    const users = await kernel.listUsers();
    printUsers(users);
  } else if (action === '2') {
    console.log('可用字段: id, name, email, avatar, gender, age, intro, vip');
    const key = (await ask('查找字段: ')).trim();
    const value = await ask('查找值: ');
    const users = await kernel.findUser(key, value);
    printUsers(users);
  } else if (action === '3') {
    const identifier = (await ask('输入用户ID或用户名: ')).trim();
    const users = await kernel.findUserSmart(identifier);
    if (!users || users.length === 0) {
      console.log('[信息] 未找到用户');
      return;
    }
    printUsers(users);
    const idx = await selectFromList(users);
    if (idx < 0) return;
    const user = users[idx];
    console.log(`\n已选择: ${user.name} (${user.id})`);
    console.log('可修改字段: name, avatar, email, gender, age, intro, vip, password, is_banned');
    const key = (await ask('修改字段: ')).trim();
    const value = await ask('修改值: ');
    if (await confirm(`确认将 ${user.name} 的 ${key} 修改为: ${value}?`)) {
      const ok = await kernel.updateUser(user.id, key, value);
      console.log(ok ? '[成功] 用户数据已更新' : '[失败] 更新未生效');
    }
  } else if (action === '4') {
    const identifier = (await ask('输入用户ID或用户名: ')).trim();
    const users = await kernel.findUserSmart(identifier);
    if (!users || users.length === 0) {
      console.log('[信息] 未找到用户');
      return;
    }
    printUsers(users);
    const idx = await selectFromList(users);
    if (idx >= 0) {
      const user = users[idx];
      if (await confirm(`确认封禁用户 ${user.name} (${user.id})?`)) {
        const ok = await kernel.banUser(user.id);
        console.log(ok ? '[成功] 用户已被封禁' : '[失败] 操作失败');
      }
    }
  } else if (action === '5') {
    const identifier = (await ask('输入用户ID或用户名: ')).trim();
    const users = await kernel.findUserSmart(identifier);
    if (!users || users.length === 0) {
      console.log('[信息] 未找到用户');
      return;
    }
    printUsers(users);
    const idx = await selectFromList(users);
    if (idx >= 0) {
      const user = users[idx];
      if (await confirm(`确认解封用户 ${user.name} (${user.id})?`)) {
        const ok = await kernel.unbanUser(user.id);
        console.log(ok ? '[成功] 用户已被解封' : '[失败] 操作失败');
      }
    }
  }
}

async function cliPosts(kernel) {
  console.log('\n--- 帖子管理 ---');
  console.log('  1. 查看帖子详情');
  console.log('  2. 删除帖子');
  console.log('  3. 查看帖子评论');
  console.log('  4. 删除评论');
  console.log('  0. 返回');
  const action = (await ask('选择: ')).trim();

  if (action === '1') {
    const postId = (await ask('输入帖子ID: ')).trim();
    const post = await kernel.getPostDetail(postId);
    printPostDetail(post);
  } else if (action === '2') {
    const postId = (await ask('输入帖子ID: ')).trim();
    const post = await kernel.getPostDetail(postId);
    if (!post) {
      console.log('[信息] 帖子不存在');
      return;
    }
    printPostDetail(post);
    if (await confirm(`确认删除帖子 '${post.title}'?`)) {
      const result = await kernel.deletePost(postId);
      console.log(result.success !== false ? '[成功] 帖子已删除' : '[失败] 删除失败');
    }
  } else if (action === '3') {
    const postId = (await ask('输入帖子ID: ')).trim();
    const comments = await kernel.getPostComments(postId);
    printComments(comments);
  } else if (action === '4') {
    const commentId = (await ask('输入评论ID: ')).trim();
    if (await confirm(`确认删除评论 ${commentId}?`)) {
      const result = await kernel.deleteComment(commentId);
      console.log(result.success !== false ? '[成功] 评论已删除' : '[失败] 删除失败');
    }
  }
}

// ========================
// 交互模式主循环
// ========================

async function interactiveMode(kernel) {
  console.log('='.repeat(50));
  console.log('  妖精论坛管理员客户端内核');
  console.log('='.repeat(50));

  while (true) {
    console.log('\n主菜单:');
    console.log('  1. 举报管理');
    console.log('  2. 用户管理');
    console.log('  3. 帖子管理');
    console.log('  4. 统计信息');
    console.log('  5. 重新配置');
    console.log('  0. 退出');
    const choice = (await ask('选择: ')).trim();

    try {
      if (choice === '1') {
        await cliReports(kernel);
      } else if (choice === '2') {
        await cliUsers(kernel);
      } else if (choice === '3') {
        await cliPosts(kernel);
      } else if (choice === '4') {
        const stats = await kernel.getStats();
        printStats(stats);
      } else if (choice === '5') {
        config = {};
        if (await ensureConfig()) {
          kernel = createKernel();
          await kernel.connect();
          console.log('[成功] 已重新连接');
        }
      } else if (choice === '0') {
        console.log('[退出] 再见');
        break;
      } else {
        console.log('[错误] 无效选择');
      }
    } catch (e) {
      console.log(`[错误] ${e.message}`);
    }
  }

  rl.close();
}

// ========================
// 命令行模式
// ========================

async function commandLineMode(kernel, args) {
  try {
    const cmd = args[0];

    if (cmd === 'reports') {
      const reports = await kernel.listReports();
      printReports(reports);
      return;
    }

    if (cmd === 'users') {
      const users = await kernel.listUsers();
      printUsers(users);
      return;
    }

    if (cmd === 'stats') {
      const stats = await kernel.getStats();
      printStats(stats);
      return;
    }

    if (cmd === 'post' && args[1]) {
      const post = await kernel.getPostDetail(args[1]);
      printPostDetail(post);
      return;
    }

    if (cmd === 'delete-post' && args[1]) {
      const result = await kernel.deletePost(args[1]);
      console.log(result.success !== false ? '[成功] 帖子已删除' : '[失败] 删除失败');
      return;
    }

    if (cmd === 'delete-comment' && args[1]) {
      const result = await kernel.deleteComment(args[1]);
      console.log(result.success !== false ? '[成功] 评论已删除' : '[失败] 删除失败');
      return;
    }

    if (cmd === 'ban' && args[1]) {
      const users = await kernel.findUserSmart(args[1]);
      if (!users || users.length === 0) {
        console.log('[信息] 未找到用户');
        return;
      }
      for (const u of users) {
        const ok = await kernel.banUser(u.id);
        console.log(ok ? `[成功] 已封禁: ${u.name} (${u.id})` : `[失败] 封禁失败: ${u.name}`);
      }
      return;
    }

    if (cmd === 'unban' && args[1]) {
      const users = await kernel.findUserSmart(args[1]);
      if (!users || users.length === 0) {
        console.log('[信息] 未找到用户');
        return;
      }
      for (const u of users) {
        const ok = await kernel.unbanUser(u.id);
        console.log(ok ? `[成功] 已解封: ${u.name} (${u.id})` : `[失败] 解封失败: ${u.name}`);
      }
      return;
    }

    if (cmd === 'resolve-report' && args[1]) {
      const ok = await kernel.resolveReport(args[1]);
      console.log(ok ? '[成功] 举报已标记为已处理' : '[失败] 操作失败');
      return;
    }

    if (cmd === 'edit-user' && args[1] && args[2]) {
      function parse(arg) {
        if (!arg.includes('=')) return [null, null];
        const [k, ...rest] = arg.split('=');
        return [k.trim(), rest.join('=')];
      }
      const [skey, sval] = parse(args[1]);
      const [ukey, uval] = parse(args[2]);
      if (!skey || !ukey) {
        console.log('[错误] 参数格式错误，必须使用 key=value');
        return;
      }
      const users = await kernel.findUser(skey, sval);
      if (!users || users.length === 0) {
        console.log('[信息] 未找到用户');
        return;
      }
      printUsers(users);
      const idx = await selectFromList(users);
      if (idx >= 0) {
        const user = users[idx];
        if (await confirm(`确认将 ${user.name} 的 ${ukey} 修改为: ${uval}?`)) {
          const ok = await kernel.updateUser(user.id, ukey, uval);
          console.log(ok ? '[成功] 用户数据已更新' : '[失败] 更新未生效');
        }
      }
      return;
    }

    console.log(HELP_TEXT);
  } finally {
    rl.close();
  }
}

const HELP_TEXT = `
妖精论坛管理员客户端内核

用法:
  交互模式:
    node app/cli.js

  命令行模式:
    node app/cli.js reports                  查看举报列表
    node app/cli.js users                    查看用户列表
    node app/cli.js stats                    查看统计信息
    node app/cli.js post <post_id>          查看帖子详情
    node app/cli.js delete-post <post_id>      删除帖子
    node app/cli.js delete-comment <comment_id>  删除评论
    node app/cli.js ban <user_id_or_name>    封禁用户
    node app/cli.js unban <user_id_or_name>    解封用户
    node app/cli.js resolve-report <report_id>  标记举报已处理
    node app/cli.js edit-user "name=张三" "vip=1"  修改用户信息
`;

// ========================
// 主入口
// ========================

async function main() {
  loadConfig();

  const args = process.argv.slice(2);

  if (args.includes('--help') || args.includes('-h')) {
    console.log(HELP_TEXT);
    rl.close();
    return;
  }

  if (!await ensureConfig()) {
    rl.close();
    process.exit(1);
  }

  const kernel = createKernel();

  try {
    await kernel.connect();
    console.log('[成功] 已连接到管理 API');
  } catch (e) {
    console.log(`[错误] 连接失败: ${e.message}`);
    rl.close();
    process.exit(1);
  }

  if (args.length > 0) {
    await commandLineMode(kernel, args);
  } else {
    await interactiveMode(kernel);
  }
}

main().catch(e => {
  console.error('[致命错误]', e);
  rl.close();
  process.exit(1);
});
