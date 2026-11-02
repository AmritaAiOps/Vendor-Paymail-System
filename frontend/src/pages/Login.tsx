import { FirebaseError } from "firebase/app";
import { sendPasswordResetEmail, signInWithEmailAndPassword } from "firebase/auth";
import { useState, type FormEvent } from "react";
import { Spinner, btnPrimary, card, focusRing, input } from "../components/ui";
import { auth } from "../firebase";
import { markActive } from "../lib/useAuth";

function plainWords(err: unknown): string {
  const code = err instanceof FirebaseError ? err.code : "";
  // With email enumeration protection on, Firebase reports wrong password and unknown user both as invalid-credential
  if (["auth/invalid-credential", "auth/wrong-password", "auth/user-not-found", "auth/invalid-email"].includes(code))
    return "Wrong email or password.";
  if (code === "auth/too-many-requests") return "Too many attempts. Wait a few minutes or reset your password.";
  if (code === "auth/user-disabled") return "This account has been disabled. Ask an admin.";
  if (code === "auth/network-request-failed") return "Cannot reach Firebase. Check your connection.";
  return "Sign-in failed. Try again.";
}

export default function Login({ notice, onDismiss }: { notice: string; onDismiss: () => void }) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const password = String(new FormData(e.currentTarget).get("password"));
    setError(""); setInfo(""); onDismiss(); setBusy(true);
    try {
      markActive();
      await signInWithEmailAndPassword(auth, email.trim(), password);
    } catch (err) {
      setError(plainWords(err));
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setError(""); setInfo("");
    if (!email.trim()) { setError("Type your email first, then choose Forgot password."); return; }
    try {
      await sendPasswordResetEmail(auth, email.trim());
      setInfo("If that email has an account, a reset link is on its way.");
    } catch (err) {
      setError(plainWords(err));
    }
  }

  return (
    <main id="main" className="flex min-h-screen flex-col items-center justify-center gap-6 p-4">
      <section className={`${card} w-full max-w-md animate-pop rounded-2xl p-8`}>
        <div className="flex flex-col items-center text-center">
          <img src="/amrita-banner.png" alt="Amrita Vishwa Vidyapeetham" className="h-11 w-auto rounded-lg shadow-sm" />
          <h1 className="mt-6 text-xl font-semibold tracking-tight">Vendor Paymail</h1>
          <p className="mt-1 text-xs text-slate-500">Sign in to the payment reconciliation portal</p>
        </div>
        <form className="mt-8 grid gap-4" onSubmit={submit}>
          <div className="grid gap-1.5">
            <label htmlFor="email" className="text-xs font-medium text-slate-500">Email</label>
            <input id="email" type="email" autoComplete="username" required autoFocus value={email} placeholder="you@company.com"
              onChange={(e) => setEmail(e.target.value)} className={`${input} py-2.5`} />
          </div>
          <div className="grid gap-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="text-xs font-medium text-slate-500">Password</label>
              <button type="button" onClick={reset} className={`rounded text-xs font-medium text-indigo-600 transition hover:text-indigo-700 ${focusRing}`}>
                Forgot password?
              </button>
            </div>
            <div className="relative">
              <input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required
                className={`${input} w-full py-2.5 pr-16`} />
              <button type="button" onClick={() => setShowPassword((s) => !s)} aria-pressed={showPassword}
                className={`absolute inset-y-1 right-1 rounded-md px-2.5 text-xs font-medium text-slate-500 transition hover:bg-slate-50 hover:text-slate-900 ${focusRing}`}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </div>
          <button type="submit" className={`${btnPrimary} mt-2 py-2.5`} disabled={busy}>
            {busy ? <><Spinner />Signing in…</> : "Sign in"}
          </button>
        </form>
        {notice && <p role="alert" className="mt-4 animate-fade-up rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-800">{notice}</p>}
        {error && <p role="alert" className="mt-4 animate-fade-up rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
        {info && <p role="status" className="mt-4 animate-fade-up rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{info}</p>}
      </section>
    </main>
  );
}
