import { useEffect, useRef, useState, type ReactNode } from "react";
import { signOut } from "firebase/auth";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ErrorBox, Logo, Spinner, btn, card, focusRing, pageTitle } from "./components/ui";
import { auth } from "./firebase";
import { useAuth } from "./lib/useAuth";
import Login from "./pages/Login";

import EmailHistory from "./pages/EmailHistory";
import VendorEmails from "./pages/VendorEmails";
import Exceptions from "./pages/Exceptions";
import ManualReview from "./pages/ManualReview";
import Settings from "./pages/Settings";
import Upload from "./pages/Upload";

const pages = [
  { path: "/upload", title: "Upload", element: <Upload /> },
  { path: "/results", title: "Vendor emails", element: <VendorEmails /> },
  { path: "/email-history", title: "Email History", element: <EmailHistory /> },
  { path: "/exceptions", title: "Exceptions", element: <Exceptions /> },
  { path: "/manual-review", title: "Manual review", element: <ManualReview /> },
  { path: "/settings", title: "Settings", element: <Settings /> },
];

// Settings lives in the account menu, so the tab bar only carries the daily pages
const tabs = pages.filter((p) => p.path !== "/settings");

function UserMenu({ email, isAdmin }: { email: string; isAdmin: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const onSettings = pathname === "/settings";
  const item = "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors";
  return (
    <div ref={ref} className="relative flex h-16 shrink-0 items-center">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu" aria-label="Account menu"
        className={`group flex items-center gap-2 rounded-full border p-1 pr-2.5 transition-all duration-150 ${focusRing} ${
          open || onSettings ? "border-indigo-300 bg-indigo-50" : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"}`}>
        <span aria-hidden className="grid h-7 w-7 place-items-center rounded-full bg-indigo-100 font-display text-xs font-semibold text-indigo-700">{email.slice(0, 2).toUpperCase()}</span>
        <svg aria-hidden viewBox="0 0 24 24" className={`h-3.5 w-3.5 text-slate-500 transition-transform duration-150 ${open ? "rotate-180 text-slate-900" : "group-hover:text-slate-700"}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-50 -mt-1 w-60 origin-top-right animate-pop rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl">
          <div className="border-b border-slate-200 px-3 py-2.5">
            <p className="truncate text-xs font-medium text-slate-900">{email}</p>
            <p className="mt-0.5 text-[11px] text-slate-500">{isAdmin ? "Admin" : "Viewer"} · Payment reconciliation</p>
          </div>
          <div className="py-1">
            <NavLink to="/settings" role="menuitem" onClick={() => setOpen(false)}
              className={`${item} justify-between ${onSettings ? "bg-indigo-50 text-indigo-700" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"}`}>
              <span className="flex items-center gap-2.5">
                <svg aria-hidden viewBox="0 0 24 24" className="h-3.5 w-3.5 text-slate-500" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" /></svg>
                Settings
              </span>
              {onSettings && <span className="font-mono text-[10px] text-indigo-700">Active</span>}
            </NavLink>
          </div>
          <div className="border-t border-slate-200 pt-1">
            <button type="button" role="menuitem" onClick={() => signOut(auth)} className={`${item} text-rose-700 hover:bg-rose-50 hover:text-rose-800`}>
              <svg aria-hidden viewBox="0 0 24 24" className="h-3.5 w-3.5 text-rose-400" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" /></svg>
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const FullScreen = ({ children }: { children: ReactNode }) => (
  <main id="main" className="grid min-h-screen place-items-center p-4">{children}</main>
);

export default function App() {
  const { user, me, notice, clearNotice } = useAuth();
  const { pathname } = useLocation();
  // Wait for Firebase's first answer and /auth/me, so a signed-in user never sees the login page flash
  if (user === undefined || (user && me.isPending)) {
    return <FullScreen><div role="status" className="flex animate-fade-in flex-col items-center gap-4 text-slate-500"><Logo className="h-12 w-12" /><span className="flex items-center gap-2"><Spinner />Checking sign-in…</span></div></FullScreen>;
  }
  if (!user || !me.data) {
    // Signed out, or /auth/me failed (a 403 signs out in useAuth; anything else is shown with a way out)
    if (user && me.isError) {
      return <FullScreen><div className={`${card} w-full max-w-sm animate-pop p-6`}><ErrorBox error={me.error} /><button className={`${btn} mt-3 w-full`} onClick={() => signOut(auth)}>Sign out</button></div></FullScreen>;
    }
    return (
      <Routes>
        <Route path="/login" element={<Login notice={notice} onDismiss={clearNotice} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded-lg focus:bg-white focus:p-2 focus:text-slate-900 focus:ring-2 focus:ring-indigo-500">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 px-4 sm:px-6 lg:flex-nowrap">
          <NavLink to="/results" className={`group flex h-16 shrink-0 items-center gap-3.5 rounded-lg ${focusRing}`}>
            <img src="/amrita-banner.png" alt="Amrita Vishwa Vidyapeetham" className="h-9 w-auto rounded-lg shadow-sm transition-transform duration-150 group-hover:scale-[1.02]" />
            <span aria-hidden className="hidden h-5 w-px bg-slate-200 md:block" />
            <span className="hidden leading-tight md:block">
              <span className="block font-display text-sm font-semibold tracking-tight text-slate-900 transition-colors group-hover:text-indigo-700">Vendor Paymail</span>
              <span className="block text-[11px] text-slate-500">Payment reconciliation</span>
            </span>
          </NavLink>
          {/* below lg the tabs drop to their own scrollable row instead of disappearing */}
          <nav aria-label="Main" className="order-last w-full overflow-x-auto pb-3 lg:order-none lg:w-auto lg:pb-0">
            <div className="flex w-max items-center gap-0.5 rounded-xl border border-slate-200 bg-slate-100 p-1">
              {tabs.map((p) => (
                <NavLink key={p.path} to={p.path}
                  className={({ isActive }) =>
                    `whitespace-nowrap rounded-lg border px-3.5 py-1.5 text-xs font-medium transition-colors duration-150 ${focusRing} ${
                      isActive ? "border-slate-200 bg-white text-indigo-700 shadow-sm" : "border-transparent text-slate-500 hover:text-slate-900"}`}>
                  {p.title}
                </NavLink>
              ))}
            </div>
          </nav>
          <UserMenu email={me.data.email} isAdmin={me.data.is_admin} />
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[110rem] px-3 py-6 sm:px-4">
        {/* keyed on the path so every page change replays the entrance animation */}
        <div key={pathname} className="animate-fade-up">
          <Routes>
            <Route path="/" element={<Navigate to="/upload" replace />} />
            <Route path="/login" element={<Navigate to="/upload" replace />} />
            {pages.map((p) => (
              <Route key={p.path} path={p.path} element={p.element} />
            ))}
            <Route path="/email-queue" element={<Navigate to="/results" replace />} />
            <Route path="/batch-results/*" element={<Navigate to="/results" replace />} />
            <Route path="*" element={<h1 className={pageTitle}>Page not found</h1>} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
