"use client";

import Link from "next/link";
import { useState } from "react";
import { useToast } from "@/components/Toast";
import { ApiException, miscApi } from "@/lib/api";

/** 提交反馈：游客也可提交，成功后引导去反馈中心查看 */
export default function FeedbackSubmitPage() {
  const { toast } = useToast();
  const [title, setTitle] = useState("");
  const [detail, setDetail] = useState("");
  const [steps, setSteps] = useState("");
  const [contact, setContact] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async () => {
    if (!title.trim() || !detail.trim()) {
      toast("请填写标题与详细描述", "warning");
      return;
    }
    setSubmitting(true);
    try {
      await miscApi.reportBug({
        title: title.trim(),
        detail: detail.trim(),
        steps: steps.trim(),
        contact: contact.trim(),
        page_url: window.location.href,
      });
      setDone(true);
    } catch (e) {
      toast(e instanceof ApiException ? e.message : "提交失败，请稍后重试", "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <div className="forum-container feedback-submit-page">
        <div className="feedback-success">
          <i className="fa fa-check-circle feedback-success-icon"></i>
          <h1 className="feedback-success-title">提交成功，感谢反馈！</h1>
          <p className="feedback-success-text">我们会尽快查看处理，处理进度会公开展示在反馈中心。</p>
          <div className="feedback-success-actions">
            <Link className="forum-create-btn" href="/feedback">去反馈中心看看</Link>
            <button
              type="button"
              className="feedback-secondary-btn"
              onClick={() => {
                setTitle("");
                setDetail("");
                setSteps("");
                setContact("");
                setDone(false);
              }}
            >
              再提交一条
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="forum-container feedback-submit-page">
      <div className="forum-header">
        <h1 className="forum-title">提交反馈</h1>
        <p className="forum-subtitle">无需登录也可提交，展示不会披露您的身份</p>
      </div>

      <div className="feedback-form">
        <label className="feedback-form-label" htmlFor="feedback-title">
          标题 <span className="feedback-required">*</span>
        </label>
        <input
          id="feedback-title"
          className="feedback-form-input"
          placeholder="一句话描述问题或建议"
          maxLength={200}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <label className="feedback-form-label" htmlFor="feedback-detail">
          详细描述 <span className="feedback-required">*</span>
        </label>
        <textarea
          id="feedback-detail"
          className="feedback-form-input feedback-form-textarea"
          placeholder="请尽量描述清楚：你期望的结果与实际发生的情况"
          rows={6}
          maxLength={5000}
          value={detail}
          onChange={(e) => setDetail(e.target.value)}
        />

        <label className="feedback-form-label" htmlFor="feedback-steps">
          复现步骤 <span className="feedback-form-optional">（选填）</span>
        </label>
        <textarea
          id="feedback-steps"
          className="feedback-form-input feedback-form-textarea"
          placeholder="例如：1. 打开首页；2. 点击……；3. 出现……"
          rows={4}
          maxLength={3000}
          value={steps}
          onChange={(e) => setSteps(e.target.value)}
        />

        <label className="feedback-form-label" htmlFor="feedback-contact">
          联系方式 <span className="feedback-form-optional">（选填，仅管理员可见）</span>
        </label>
        <input
          id="feedback-contact"
          className="feedback-form-input"
          placeholder="邮箱 / QQ 等，便于必要时与你联系"
          maxLength={200}
          value={contact}
          onChange={(e) => setContact(e.target.value)}
        />

        <button className="feedback-submit-btn" type="button" disabled={submitting} onClick={submit}>
          {submitting ? "提交中..." : "提交反馈"}
        </button>
      </div>
    </div>
  );
}
