import GlobalLoading from "@/components/GlobalLoading";

/** 路由切换时的全局加载态（顶部栏与页脚由 layout 保留） */
export default function Loading() {
  return (
    <div className="route-loading">
      <GlobalLoading />
    </div>
  );
}
