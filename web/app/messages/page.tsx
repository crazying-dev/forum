"use client";

// 消息中心页面：MessageCenter 内部使用 useSearchParams（?type= 深链），
// 按 Next.js App Router 规范包一层 Suspense。

import { Suspense } from "react";
import GlobalLoading from "@/components/GlobalLoading";
import MessageCenter from "@/components/messages/MessageCenter";

export default function MessagesPage() {
  return (
    <Suspense
      fallback={
        <div className="route-loading">
          <GlobalLoading />
        </div>
      }
    >
      <MessageCenter />
    </Suspense>
  );
}
