import type { ReactElement } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import BatchResults from "./pages/BatchResults";
import EmailHistory from "./pages/EmailHistory";
import EmailQueue from "./pages/EmailQueue";
import { Placeholder } from "./pages/Placeholder";
import Upload from "./pages/Upload";

// Pages built so far; the rest still show a placeholder
const built: Record<string, ReactElement> = {
  "/upload": <Upload />, "/batch-results": <BatchResults />, "/email-queue": <EmailQueue />, "/email-history": <EmailHistory />,
};

const pages = [
  { path: "/upload", title: "Upload" },
  { path: "/batch-results", title: "Batch results" },
  { path: "/email-queue", title: "Email queue" },
  { path: "/email-history", title: "Email History" },
  { path: "/exceptions", title: "Exceptions" },
  { path: "/manual-review", title: "Manual review" },
  { path: "/settings", title: "Settings" },
  { path: "/login", title: "Login" },
];

export default function App() {
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
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-7xl p-4">
        <Routes>
          <Route path="/" element={<Navigate to="/upload" replace />} />
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
