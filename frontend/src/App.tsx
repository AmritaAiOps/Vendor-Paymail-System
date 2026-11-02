import type { ReactElement } from "react";
import { signOut } from "firebase/auth";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ErrorBox, Loading, btn } from "./components/ui";
import { auth } from "./firebase";
import { useAuth } from "./lib/useAuth";
import Login from "./pages/Login";
import BatchResults from "./pages/BatchResults";
import EmailHistory from "./pages/EmailHistory";
import EmailQueue from "./pages/EmailQueue";
import Exceptions from "./pages/Exceptions";
import ManualReview from "./pages/ManualReview";
import Settings from "./pages/Settings";
import { Placeholder } from "./pages/Placeholder";
import Upload from "./pages/Upload";

// Pages built so far; the rest still show a placeholder
const built: Record<string, ReactElement> = {
  "/upload": <Upload />, "/batch-results": <BatchResults />, "/email-queue": <EmailQueue />, "/email-history": <EmailHistory />,
  "/exceptions": <Exceptions />, "/manual-review": <ManualReview />, "/settings": <Settings />,
};

const pages = [
  { path: "/upload", title: "Upload" },
  { path: "/batch-results", title: "Batch results" },
  { path: "/email-queue", title: "Email queue" },
  { path: "/email-history", title: "Email History" },
  { path: "/exceptions", title: "Exceptions" },
  { path: "/manual-review", title: "Manual review" },
  { path: "/settings", title: "Settings" },
];

export default function App() {
  const { user, me, notice, clearNotice } = useAuth();
  // Wait for Firebase's first answer and /auth/me, so a signed-in user never sees the login page flash
  if (user === undefined || (user && me.isPending)) return <Loading what="Checking sign-in" />;
  if (!user || !me.data) {
    // Signed out, or /auth/me failed (a 403 signs out in useAuth; anything else is shown with a way out)
    return (
      <main id="main" className="min-h-screen bg-slate-50 p-4 text-slate-900">
        {user && me.isError && (
          <div className="mx-auto max-w-sm"><ErrorBox error={me.error} /><button className={`${btn} mt-2`} onClick={() => signOut(auth)}>Sign out</button></div>
        )}
        {!user && (
          <Routes>
            <Route path="/login" element={<Login notice={notice} onDismiss={clearNotice} />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        )}
      </main>
    );
  }
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:bg-white focus:p-2 focus:ring-2 focus:ring-blue-600">
        Skip to content
      </a>
      <header className="bg-slate-900 text-white">
        <nav aria-label="Main" className="mx-auto flex max-w-7xl flex-wrap items-center gap-1 px-4 py-2">
          <span className="mr-4 font-semibold">Vendor Payment Reconciliation</span>
          {pages.map((p) => (
            <NavLink
              key={p.path}
              to={p.path}
              className={({ isActive }) =>
                `rounded px-3 py-1.5 text-sm outline-none hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-white ${isActive ? "bg-slate-700" : ""}`
              }
            >
              {p.title}
            </NavLink>
          ))}
          <span className="ml-auto text-sm text-slate-300">{me.data.email}{me.data.is_admin && " (admin)"}</span>
          <button className={`${btn} text-slate-900`} onClick={() => signOut(auth)}>Sign out</button>
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-7xl p-4">
        <Routes>
          <Route path="/" element={<Navigate to="/upload" replace />} />
          <Route path="/login" element={<Navigate to="/upload" replace />} />
          {pages.map((p) => (
            <Route key={p.path} path={p.path} element={built[p.path] ?? <Placeholder title={p.title} />} />
          ))}
          <Route path="/batch-results/:id" element={<BatchResults />} />
          <Route path="*" element={<Placeholder title="Not found" />} />
        </Routes>
      </main>
    </div>
  );
}
