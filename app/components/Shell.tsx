"use client";

import {
  BookOpen,
  Boxes,
  FileOutput,
  GraduationCap,
  Home,
  Library,
  LogOut,
  Menu,
  Settings,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { CurrentUser } from "../lib/api";
import { clsx } from "clsx";

const nav = [
  { to: "/", label: "儀表板", icon: Home },
  { to: "/classes", label: "班級", icon: GraduationCap },
  { to: "/materials", label: "教材庫", icon: Library },
  { to: "/generate", label: "產生教材", icon: Sparkles },
  { to: "/packages", label: "教材包", icon: BookOpen },
  { to: "/exports", label: "匯出中心", icon: FileOutput },
  { to: "/members", label: "組織與成員", icon: Users },
  { to: "/settings", label: "AI 與系統設定", icon: Settings },
];

export function Shell({
  user,
  onLogout,
  children,
}: {
  user: CurrentUser;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        跳到主要內容
      </a>
      <aside
        className={clsx("sidebar", open && "sidebar-open")}
        aria-label="主選單"
      >
        <div className="brand">
          <div className="brand-mark">
            <Boxes />
          </div>
          <div>
            <strong>LessonForge</strong>
            <span>TW 教材工作台</span>
          </div>
        </div>
        <button
          className="mobile-close"
          onClick={() => setOpen(false)}
          aria-label="關閉選單"
        >
          <X />
        </button>
        <nav>
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                clsx("nav-link", isActive && "active")
              }
            >
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-avatar" aria-hidden="true">
            {user.display_name.slice(0, 1)}
          </div>
          <div className="user-copy">
            <strong>{user.display_name}</strong>
            <span>
              {user.role} · {user.organization_name}
            </span>
          </div>
          <button
            className="icon-button inverse"
            onClick={onLogout}
            aria-label="登出"
          >
            <LogOut />
          </button>
        </div>
      </aside>
      {open ? (
        <button
          className="mobile-scrim"
          aria-label="關閉選單"
          onClick={() => setOpen(false)}
        />
      ) : null}
      <div className="main-column">
        <header className="topbar">
          <button
            className="mobile-menu"
            onClick={() => setOpen(true)}
            aria-label="開啟選單"
          >
            <Menu />
          </button>
          <div>
            <span className="eyebrow">{user.organization_name}</span>
            <strong>英文教材生產中心</strong>
          </div>
          <div className="topbar-badge">
            <span className="live-dot" />
            Mock 模式可用
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
