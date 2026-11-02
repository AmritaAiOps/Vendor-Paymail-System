import { FirebaseError } from "firebase/app";
import { sendPasswordResetEmail, signInWithEmailAndPassword } from "firebase/auth";
import { useState, type FormEvent } from "react";
import { btn, btnPrimary, input } from "../components/ui";
import { auth } from "../firebase";

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

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const password = String(new FormData(e.currentTarget).get("password"));
    setError(""); setInfo(""); onDismiss(); setBusy(true);
    try {
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
    <section className="mx-auto mt-12 max-w-sm rounded-lg border border-slate-200 bg-white p-6">
      <h1 className="text-xl font-semibold">Sign in</h1>
      <form className="mt-4 grid gap-3" onSubmit={submit}>
        <div className="grid gap-1">
          <label htmlFor="email" className="font-medium">Email</label>
          <input id="email" type="email" autoComplete="username" required autoFocus value={email}
            onChange={(e) => setEmail(e.target.value)} className={input} />
        </div>
        <div className="grid gap-1">
          <label htmlFor="password" className="font-medium">Password</label>
          <input id="password" name="password" type="password" autoComplete="current-password" required className={input} />
        </div>
        <button type="submit" className={btnPrimary} disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <button type="button" className={btn} onClick={reset}>Forgot password</button>
      </form>
      {(notice || error) && <p role="alert" className="mt-3 text-sm text-red-800">{notice || error}</p>}
      {info && <p role="status" className="mt-3 text-sm text-green-800">{info}</p>}
    </section>
  );
}
