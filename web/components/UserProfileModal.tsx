"use client";

import { useRef, useState } from "react";
import Modal from "./ui/Modal";
import { UserAvatar } from "./ui/UserAvatar";
import { userApi, User, ApiException } from "@/lib/api";
import { useToast } from "./Toast";
import { ageDisplay } from "@/lib/constants";

/**
 * 用户资料弹窗（对齐 legacy ShowUserProfileDetail / ShowUserProfileEdit）：
 * - 详情：用户名/年龄/性别/注册时间（本人额外显示编辑按钮）
 * - 编辑：头像（URL 或上传）/用户名/简介/性别/出生日期
 */
export default function UserProfileModal({
  profile,
  isSelf,
  onClose,
  onSaved,
}: {
  profile: User;
  isSelf: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { toast } = useToast();
  const [mode, setMode] = useState<"detail" | "edit">("detail");
  const [name, setName] = useState(profile.name || "");
  const [intro, setIntro] = useState(profile.intro || "");
  const [avatar, setAvatar] = useState(profile.avatar || "");
  const [avatarTab, setAvatarTab] = useState<"url" | "upload">("url");
  const [gender, setGender] = useState<number>(profile.gender ?? 0);
  const [birthday, setBirthday] = useState<{ y: string; m: string; d: string }>(() => {
    const a = profile.age || "";
    if (/^\d{8}$/.test(a)) return { y: a.slice(0, 4), m: a.slice(4, 6), d: a.slice(6, 8) };
    return { y: "", m: "", d: "" };
  });
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [calView, setCalView] = useState<{ y: number; m: number }>(() => ({ y: new Date().getFullYear(), m: new Date().getMonth() + 1 }));
  const fileRef = useRef<HTMLInputElement>(null);

  const toggleCalendar = () => {
    if (!showCalendar) {
      setCalView({ y: parseInt(birthday.y, 10) || new Date().getFullYear(), m: parseInt(birthday.m, 10) || new Date().getMonth() + 1 });
    }
    setShowCalendar(!showCalendar);
  };

  const stepCalMonth = (delta: number) => {
    setCalView((v) => {
      let m = v.m + delta;
      let y = v.y;
      if (m < 1) { m = 12; y -= 1; }
      if (m > 12) { m = 1; y += 1; }
      return { y, m };
    });
  };

  const stepYear = (delta: number) => {
    setBirthday((b) => {
      const cur = parseInt(b.y, 10) || new Date().getFullYear();
      return { ...b, y: String(Math.max(1900, cur + delta)) };
    });
  };

  const doSave = async () => {
    if (saving) return;
    const cleanName = name.trim();
    if (cleanName.length < 2 || cleanName.length > 20) {
      toast("用户名需2-20个字符", "error");
      return;
    }
    const { y, m, d } = birthday;
    const ym = parseInt(m, 10);
    const yd = parseInt(d, 10);
    let bd = "";
    if (y || m || d) {
      if (!/^\d{4}$/.test(y) || !ym || !yd || ym < 1 || ym > 12 || yd < 1 || yd > 31) {
        toast("请检查出生日期", "error");
        return;
      }
      bd = `${y}${String(ym).padStart(2, "0")}${String(yd).padStart(2, "0")}`;
    }
    const payload: Record<string, unknown> = {};
    if (cleanName !== profile.name) payload.Name = cleanName;
    if (intro !== (profile.intro || "")) payload.intro = intro;
    if (gender !== (profile.gender ?? 0)) payload.gender = gender;
    if (bd !== (profile.age || "")) payload.age = bd;
    const avatarVal = avatar.trim();
    if (avatarVal !== (profile.avatar || "")) payload.avatar = avatarVal;
    if (Object.keys(payload).length === 0) {
      toast("未修改任何内容", "info");
      return;
    }
    setSaving(true);
    try {
      await userApi.updateMe(payload);
      toast("保存成功", "success");
      onSaved();
      onClose();
    } catch (e: any) {
      toast(e instanceof ApiException ? e.message : "保存失败", "error");
      setSaving(false);
    }
  };

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) {
      toast("图片大小不能超过10MB", "error");
      return;
    }
    setUploading(true);
    try {
      const r = await userApi.uploadAvatar(f);
      setAvatar(r.avatar);
      toast("头像已上传，点击保存后生效", "success");
    } catch (err: any) {
      toast(err instanceof ApiException ? err.message : "上传失败", "error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <Modal open onClose={onClose} cardStyle={{ maxWidth: 440 }} closeable={mode !== "detail"}>
      {mode === "detail" ? (
        <>
          <h3 className="donate-title profile-modal-title">
            <span><i className="fa fa-id-card-o"></i> 个人详情</span>
            {isSelf && (
              <button type="button" className="profile-detail-edit-btn" onClick={() => setMode("edit")}>
                <i className="fa fa-pencil"></i> 编辑
              </button>
            )}
          </h3>
          <div className="profile-modal-body">
            <div className="profile-detail-row"><span className="label">用户名</span><span className="value Username">{profile.name}</span></div>
            <div className="profile-detail-row"><span className="label">年龄</span><span className="value">{ageDisplay(profile.age)}</span></div>
            <div className="profile-detail-row"><span className="label">性别</span><span className="value">{profile.gender === 1 ? "男" : profile.gender === 2 ? "女" : "保密"}</span></div>
            <div className="profile-detail-row"><span className="label">注册时间</span><span className="value">{profile.created_at ? new Date(profile.created_at).toLocaleDateString("zh-CN") : "-"}</span></div>
          </div>
        </>
      ) : (
        <>
          <h3 className="donate-title"><i className="fa fa-pencil"></i> 编辑信息</h3>
          <div className="profile-modal-body">
            <div className="profile-edit-form">
              <div className="profile-edit-group">
                <label>头像</label>
                <div className="profile-avatar-edit">
                  <div className="profile-avatar-preview">
                    <UserAvatar
                      src={avatar || "/assets/img/favicon.png"}
                      alt="头像预览"
                      fallbackClassName=""
                      loading="eager"
                    />
                  </div>
                  <div className="profile-avatar-fields">
                    <input className="profile-edit-input" value={avatar} onChange={(e) => setAvatar(e.target.value)} placeholder="输入头像图片URL" />
                    <div className="profile-avatar-switch-row">
                      <button
                        type="button"
                        className="profile-avatar-switch-btn"
                        onClick={() => setAvatarTab(avatarTab === "upload" ? "url" : "upload")}
                      >
                        <i className={`fa ${avatarTab === "upload" ? "fa-link" : "fa-upload"}`}></i>
                        {avatarTab === "upload" ? "使用URL" : "上传本地图片"}
                      </button>
                    </div>
                  </div>
                </div>
                {avatarTab === "upload" && (
                  <div className="profile-avatar-upload-area" onClick={() => fileRef.current?.click()}>
                    {uploading ? (
                      <>
                        <i className="fa fa-spinner fa-spin"></i>
                        <span>上传中...</span>
                        <span className="profile-avatar-upload-hint">正在压缩为 400x400</span>
                      </>
                    ) : (
                      <>
                        <i className="fa fa-cloud-upload"></i>
                        <span>点击选择图片</span>
                        <span className="profile-avatar-upload-hint">支持 JPG/PNG/WebP，将压缩为400x400</span>
                      </>
                    )}
                  </div>
                )}
                <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={onUpload} />
              </div>
              <div className="profile-edit-group">
                <label>用户名</label>
                <input className="profile-edit-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={20} placeholder="2-20个字符" />
              </div>
              <div className="profile-edit-group">
                <label>简介</label>
                <textarea className="profile-edit-input profile-edit-textarea" value={intro} onChange={(e) => setIntro(e.target.value)} rows={3} placeholder="这个人很懒，什么都没留下~" maxLength={200} />
              </div>
              <div className="profile-edit-group">
                <label>性别</label>
                <div className="profile-gender-options">
                  <button type="button" className={`profile-gender-opt ${gender === 1 ? "active" : ""}`} onClick={() => setGender(1)}><i className="fa fa-mars"></i> 男</button>
                  <button type="button" className={`profile-gender-opt ${gender === 2 ? "active" : ""}`} onClick={() => setGender(2)}><i className="fa fa-venus"></i> 女</button>
                  <button type="button" className={`profile-gender-opt ${gender !== 1 && gender !== 2 ? "active" : ""}`} onClick={() => setGender(0)}><i className="fa fa-user"></i> 保密</button>
                </div>
              </div>
              <div className="profile-edit-group">
                <label>出生日期</label>
                <div className="profile-birthday-row">
                  <div className="profile-birthday-picker">
                    <button type="button" className="bp-arrow" onClick={() => stepYear(-1)} title="上一年"><i className="fa fa-chevron-left"></i></button>
                    <input className="bp-year" value={birthday.y} placeholder="1996" maxLength={4} onChange={(e) => setBirthday((b) => ({ ...b, y: e.target.value.replace(/\D/g, "") }))} />
                    <button type="button" className="bp-arrow" onClick={() => stepYear(1)} title="下一年"><i className="fa fa-chevron-right"></i></button>
                    <span className="bp-sep">-</span>
                    <input className="bp-month" value={birthday.m} placeholder="01" maxLength={2} onChange={(e) => setBirthday((b) => ({ ...b, m: e.target.value.replace(/\D/g, "") }))} />
                    <span className="bp-sep">-</span>
                    <input className="bp-day" value={birthday.d} placeholder="01" maxLength={2} onChange={(e) => setBirthday((b) => ({ ...b, d: e.target.value.replace(/\D/g, "") }))} />
                  </div>
                  <button type="button" className="profile-cal-btn" onClick={toggleCalendar} title="打开日历选择">
                    <i className="fa fa-calendar"></i>
                  </button>
                </div>
              </div>
              <div className="profile-edit-actions">
                <button type="button" className="profile-action-btn profile-action-cancel" onClick={() => setMode("detail")}>取消</button>
                <button type="button" className="profile-action-btn profile-action-save" disabled={saving} onClick={doSave}>
                  {saving ? "保存中..." : "保存"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
      </Modal>
      {showCalendar && (
        <Modal open onClose={() => setShowCalendar(false)} cardStyle={{ maxWidth: 320 }}>
          <div className="profile-cal-title"><i className="fa fa-calendar"></i> 选择日期</div>
          <div className="profile-calendar">
            <div className="profile-calendar-head">
              <button type="button" className="profile-cal-nav" onClick={() => stepCalMonth(-1)}><i className="fa fa-chevron-left"></i></button>
              <span className="profile-cal-month-title">{calView.y}年{calView.m}月</span>
              <button type="button" className="profile-cal-nav" onClick={() => stepCalMonth(1)}><i className="fa fa-chevron-right"></i></button>
            </div>
            <div className="profile-cal-grid">
              {["日", "一", "二", "三", "四", "五", "六"].map((w) => (
                <span className="profile-cal-week" key={w}>{w}</span>
              ))}
              {(() => {
                const daysInMonth = new Date(calView.y, calView.m, 0).getDate();
                const firstWeekday = new Date(calView.y, calView.m - 1, 1).getDay();
                const cells = [];
                for (let i = 0; i < firstWeekday; i++) cells.push(<span className="profile-cal-empty" key={`e${i}`} />);
                for (let d = 1; d <= daysInMonth; d++) {
                  const selected = parseInt(birthday.y, 10) === calView.y && parseInt(birthday.m, 10) === calView.m && parseInt(birthday.d, 10) === d;
                  cells.push(
                    <button
                      type="button"
                      key={d}
                      className={`profile-cal-day${selected ? " selected" : ""}`}
                      onClick={() => {
                        setBirthday({ y: String(calView.y), m: String(calView.m).padStart(2, "0"), d: String(d).padStart(2, "0") });
                        setShowCalendar(false);
                      }}
                    >
                      {d}
                    </button>
                  );
                }
                return cells;
              })()}
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}