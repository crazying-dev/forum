"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, MotionConfig, useAnimate, useReducedMotion, type Variants } from "motion/react";
import GlobalLoading from "@/components/GlobalLoading";
import GuildLogo from "@/components/ui/GuildLogo";
import { guildApi, GuildListItem } from "@/lib/api";
import { contrastText, formatUserTime, themeColor, themeTint } from "@/lib/constants";
import { useCarousel } from "@/lib/useCarousel";

/**
 * 中央大卡：扑克牌式方向感知动效（custom = dir：+1 下一个 / -1 上一个）
 * - enter：从 dir 反方向「发牌」入场（位移 + 倾斜 + 缩放 + 半透明）
 * - center：spring 归位（stiffness 260 / damping 24，轻微过冲）
 * - exit：向 dir 方向「甩牌」离场（约 200ms ease-out）
 * variants 提到模块级常量、方向由 custom 传入，避免每次渲染新建大对象。
 */
const CARD_VARIANTS: Variants = {
  enter: (dir: number) => ({ x: dir * 130, rotate: dir * 11, scale: 0.88, opacity: 0.65 }),
  center: {
    x: 0,
    rotate: 0,
    scale: 1,
    opacity: 1,
    transition: { type: "spring", stiffness: 260, damping: 24 },
  },
  exit: (dir: number) => ({
    x: dir * -90,
    rotate: dir * -8,
    scale: 0.94,
    opacity: 0,
    transition: { duration: 0.2, ease: "easeOut" },
  }),
};

/** 左右缩略「扇形手牌」静止姿态：轻微外倾（±7°）+ 向中央卡收拢 */
const THUMB_REST = { prev: { rotate: -7, x: 10 }, next: { rotate: 7, x: -10 } } as const;
/** 手牌回位弹簧（略快于主卡，幅度小） */
const THUMB_SPRING = { type: "spring", stiffness: 260, damping: 22 } as const;

/** 会馆广场：轮播主视图 + 紧凑列表切换（motion 动效，尊重 prefers-reduced-motion） */
export default function HuiGuanPage() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [guilds, setGuilds] = useState<GuildListItem[] | null>(null);
  const [view, setView] = useState<"carousel" | "list">("carousel");
  const count = guilds?.length || 0;
  const { index, go, jump, hoverProps } = useCarousel(count);
  const current = guilds && count > 0 ? guilds[index] : null;

  // 切换方向：+1 = 下一个（新卡自右发牌），-1 = 上一个。在渲染期同步派生（React「调整 state」模式），
  // 让方向与新下标在同一次提交生效；出/入场动画方向一致，自动轮播 / 箭头 / 圆点 / 缩略图均适用。
  const [dir, setDir] = useState<1 | -1>(1);
  const [lastIndex, setLastIndex] = useState(0);
  if (index !== lastIndex) {
    const n = count || 1;
    const step = (index - lastIndex + n) % n; // 向后前进的步数（含首尾循环）
    setLastIndex(index);
    setDir(step === 0 || step <= n - step ? 1 : -1);
  }

  // 动效参数：减少动效（prefers-reduced-motion）时位移归零、时长趋近 0
  const enterY = reduce ? 0 : 10;
  const dur = reduce ? 0.01 : 0.28;

  // 两侧「手牌」甩牌摆动：切换时按方向小幅摆动再 spring 回位。
  // 这里用命令式动画：外层 AnimatePresence 的 initial={false} 会抑制后挂载元素的 initial/变体变化，
  // 命令式动画不受该抑制影响；仅当下标真的变化且在轮播视图内、非 reduce 时才摆动。
  const [stageRef, animateStage] = useAnimate();
  const swingIndex = useRef(index);
  useEffect(() => {
    const changed = swingIndex.current !== index;
    swingIndex.current = index;
    if (!changed || !stageRef.current || reduce) return;
    // 注意：useAnimate 的作用域动画在「选择器匹配 0 个元素」时会直接抛错（framer-motion
    // resolveElements invariant），故这里先自行 querySelector 取元素，判空后再对该元素执行动画，
    // 对应手牌（prev/next）未渲染时静默跳过，不影响其余动画。
    const swing = (selector: string, pose: { rotate: number; x: number }) => {
      const el = stageRef.current?.querySelector(selector);
      if (!el) return;
      void animateStage(
        el,
        { rotate: [pose.rotate - dir * 5, pose.rotate], x: [pose.x + dir * 6, pose.x] },
        THUMB_SPRING
      );
    };
    swing(".thumb-prev", THUMB_REST.prev);
    swing(".thumb-next", THUMB_REST.next);
  }, [index, dir, reduce, animateStage, stageRef]);

  useEffect(() => {
    (async () => {
      try {
        const r = await guildApi.list();
        // 按 id 升序（后端已排序，此处兜底）
        setGuilds([...(r.guilds || [])].sort((a, b) => a.id - b.id));
      } catch {
        setGuilds([]);
      }
    })();
  }, []);

  const prev = guilds && count > 1 ? guilds[(index - 1 + count) % count] : null;
  const next = guilds && count > 1 ? guilds[(index + 1) % count] : null;

  // 主卡（轮播切换时由父级 motion.div 负责淡入/滑入，故此处保持普通元素以复用 CSS hover）
  const card = current ? (
    <div
      className="guild-carousel-card"
      onClick={() => router.push(`/huiguan/${current.slug}`)}
      style={{ borderColor: themeTint(current.theme_color, "55") }}
    >
      <div className="guild-card-glow" style={{ background: `linear-gradient(135deg, ${themeTint(current.theme_color, "44")} 0%, transparent 72%)` }}></div>
      <GuildLogo
        logoFileId={current.logo_file_id}
        name={current.name}
        hasLogo={current.has_logo}
        color={current.theme_color}
        size={96}
        className="guild-logo guild-card-logo"
      />
      <div className="guild-card-body">
        <div className="guild-card-name-row">
          <span className="guild-card-name">{current.name}</span>
          <span
            className="guild-card-id"
            style={{ background: themeColor(current.theme_color), color: contrastText(themeColor(current.theme_color)) }}
          >
            #{current.id}
          </span>
        </div>
        <p className="guild-card-intro">{current.intro || "这个会馆还没有简介～"}</p>
        <div className="guild-card-meta">
          <span className="guild-card-meta-item">
            <i className="fa fa-user-o"></i> 馆长：{current.leader?.name || "虚位以待"}
          </span>
          <Link
            className="guild-card-meta-item guild-card-meta-link"
            href={`/huiguan/${current.slug}/members`}
            onClick={(e) => e.stopPropagation()}
          >
            <i className="fa fa-users"></i> {current.member_count} 人
          </Link>
          <span className="guild-card-meta-item">
            <i className="fa fa-clock-o"></i> 创建于 {current.created_at ? formatUserTime(current.created_at) : "—"}
          </span>
        </div>
      </div>
      <Link
        className="guild-enter-btn"
        href={`/huiguan/${current.slug}`}
        onClick={(e) => e.stopPropagation()}
        style={{ background: themeColor(current.theme_color) }}
      >
        进入会馆 <i className="fa fa-arrow-right"></i>
      </Link>
    </div>
  ) : null;

  return (
    /* reducedMotion="user"：跟随系统「减少动态效果」，位移/缩放直接吸附，仅保留透明度过渡 */
    <MotionConfig reducedMotion="user">
      <div className="guild-page">
        <div className="guild-page-header">
          <h1 className="guild-page-title">会馆广场</h1>
          <p className="guild-page-subtitle">走进会馆，遇见同好</p>
          {count > 0 && (
            <motion.button
              className="guild-view-toggle"
              whileHover={reduce ? undefined : { scale: 1.03 }}
              whileTap={reduce ? undefined : { scale: 0.97 }}
              onClick={() => setView(view === "carousel" ? "list" : "carousel")}
            >
              <i className={`fa ${view === "carousel" ? "fa-list-ul" : "fa-picture-o"}`}></i>
              {view === "carousel" ? "查看所有会馆" : "返回轮播"}
            </motion.button>
          )}
        </div>

        {guilds === null ? (
          <GlobalLoading />
        ) : count === 0 ? (
          <div className="guild-empty">
            <i className="fa fa-home"></i>
            <p className="guild-empty-title">还没有会馆</p>
            <p className="guild-empty-desc">会馆正在筹建中，先去论坛逛逛吧～</p>
            <Link className="guild-empty-link" href="/forum">
              前往论坛广场 <i className="fa fa-arrow-right"></i>
            </Link>
          </div>
        ) : (
          /* 轮播 ⇄ 列表切换：mode="wait" 保证退出动画结束后再入场（layout 动画用于列表重排） */
          <AnimatePresence mode="wait" initial={false}>
            {view === "carousel" && current ? (
              <motion.div
                key="carousel"
                className="guild-carousel"
                initial={{ opacity: 0, y: enterY }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -enterY }}
                transition={{ duration: dur, ease: "easeOut" }}
                {...hoverProps}
              >
                <div className="guild-carousel-stage" ref={stageRef}>
                  {prev && (
                    /* 扇形手牌：静止姿态由 animate 固定，切换摆动由命令式动画叠加 */
                    <motion.button
                      className="guild-carousel-thumb thumb-prev"
                      onClick={() => go(-1)}
                      title={`切换到 ${prev.name}`}
                      animate={{ rotate: THUMB_REST.prev.rotate, x: THUMB_REST.prev.x, scale: 1 }}
                      whileHover={reduce ? undefined : { scale: 1.06, y: -2 }}
                      whileTap={reduce ? undefined : { scale: 0.96 }}
                    >
                      <GuildLogo
                        logoFileId={prev.logo_file_id}
                        name={prev.name}
                        hasLogo={prev.has_logo}
                        color={prev.theme_color}
                        size={44}
                        className="guild-logo guild-thumb-logo"
                      />
                      <span className="guild-thumb-name">{prev.name}</span>
                    </motion.button>
                    )}

                  <button className="guild-carousel-arrow arrow-left" aria-label="上一个会馆" onClick={() => go(-1)}>
                    <i className="fa fa-chevron-left"></i>
                  </button>

                  {/* 主卡：扑克牌式切换——旧卡向 dir 方向甩出，新卡自 dir 反方向发牌入场；
                      popLayout 让出/入场同时进行（离场卡脱离文档流），舞台布局不跳动 */}
                  <AnimatePresence mode="popLayout" initial={false} custom={dir}>
                    <motion.div
                      key={current.slug}
                      className="guild-carousel-card-wrap"
                      custom={dir}
                      variants={CARD_VARIANTS}
                      initial={reduce ? "center" : "enter"}
                      animate="center"
                      exit="exit"
                    >
                      {card}
                    </motion.div>
                  </AnimatePresence>

                  <button className="guild-carousel-arrow arrow-right" aria-label="下一个会馆" onClick={() => go(1)}>
                    <i className="fa fa-chevron-right"></i>
                  </button>

                  {next && (
                    <motion.button
                      className="guild-carousel-thumb thumb-next"
                      onClick={() => go(1)}
                      title={`切换到 ${next.name}`}
                      animate={{ rotate: THUMB_REST.next.rotate, x: THUMB_REST.next.x, scale: 1 }}
                      whileHover={reduce ? undefined : { scale: 1.06, y: -2 }}
                      whileTap={reduce ? undefined : { scale: 0.96 }}
                    >
                      <GuildLogo
                        logoFileId={next.logo_file_id}
                        name={next.name}
                        hasLogo={next.has_logo}
                        color={next.theme_color}
                        size={44}
                        className="guild-logo guild-thumb-logo"
                      />
                      <span className="guild-thumb-name">{next.name}</span>
                    </motion.button>
                    )}
                </div>

                <div className="guild-carousel-dots">
                  {guilds.map((g, i) => (
                    <motion.button
                      key={g.uuid || g.slug}
                      className={`guild-carousel-dot ${i === index ? "active" : ""}`}
                      aria-label={`切换到 ${g.name}`}
                      onClick={() => jump(i)}
                      animate={{ scale: i === index && !reduce ? 1.35 : 1, opacity: i === index ? 1 : 0.55 }}
                      transition={{ duration: reduce ? 0 : 0.22, ease: "easeOut" }}
                      style={i === index ? { background: themeColor(g.theme_color) } : undefined}
                    ></motion.button>
                  ))}
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="list"
                className="guild-list"
                initial={{ opacity: 0, y: enterY }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -enterY }}
                transition={{ duration: dur, ease: "easeOut" }}
              >
                {guilds.map((g, i) => (
                  <motion.div
                    key={g.uuid || g.slug}
                    className="guild-list-cell"
                    layout={!reduce}
                    initial={{ opacity: 0, y: reduce ? 0 : 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: dur, delay: reduce ? 0 : Math.min(i * 0.04, 0.24), ease: "easeOut" }}
                    whileHover={reduce ? undefined : { y: -2 }}
                    whileTap={reduce ? undefined : { scale: 0.995 }}
                  >
                    <Link className="guild-list-item" href={`/huiguan/${g.slug}`}>
                      <GuildLogo
                        logoFileId={g.logo_file_id}
                        name={g.name}
                        hasLogo={g.has_logo}
                        color={g.theme_color}
                        size={48}
                        className="guild-logo guild-list-logo"
                      />
                      <div className="guild-list-body">
                        <div className="guild-list-name-row">
                          <span className="guild-list-name">{g.name}</span>
                          <span
                            className="guild-list-id"
                            style={{ background: themeColor(g.theme_color), color: contrastText(themeColor(g.theme_color)) }}
                          >
                            #{g.id}
                          </span>
                        </div>
                        <p className="guild-list-intro">{g.intro || "这个会馆还没有简介～"}</p>
                      </div>
                      <div className="guild-list-meta">
                        <span>
                          <i className="fa fa-user-o"></i> {g.leader?.name || "虚位以待"}
                        </span>
                        <span
                          className="guild-list-meta-link"
                          title="查看成员名单"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            router.push(`/huiguan/${g.slug}/members`);
                          }}
                        >
                          <i className="fa fa-users"></i> {g.member_count}
                        </span>
                      </div>
                    </Link>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </div>
    </MotionConfig>
  );
}
