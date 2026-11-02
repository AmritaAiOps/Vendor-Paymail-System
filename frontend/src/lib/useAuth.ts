import { useQuery, useQueryClient } from "@tanstack/react-query";
import { onAuthStateChanged, sendEmailVerification, signOut, type User } from "firebase/auth";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { auth } from "../firebase";

const IDLE_MS = 30 * 60_000;
const LAST_ACTIVE = "lastActiveAt";

/** Record activity now. Login calls it before signing in, so an old timestamp can't sign a fresh session out. */
export function markActive() {
  try { localStorage.setItem(LAST_ACTIVE, String(Date.now())); } catch { /* storage blocked: the timer just won't span tabs */ }
}

function lastActive(): number {
  try { return Number(localStorage.getItem(LAST_ACTIVE)) || Date.now(); } catch { return Date.now(); }
}

/** The signed-in user's MeOut, shared through the query cache (Settings reads is_admin from it). */
export const useMe = (uid = auth.currentUser?.uid) =>
  useQuery({ queryKey: ["me", uid], queryFn: api.me, enabled: !!uid, retry: false, staleTime: Infinity });

/** user: undefined until Firebase reports the first state, then the User or null. Firebase is the only source. */
export function useAuth() {
  const qc = useQueryClient();
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [notice, setNotice] = useState("");
  useEffect(() => onAuthStateChanged(auth, (u) => { if (!u) qc.clear(); setUser(u); }), [qc]);
  const me = useMe(user?.uid);
  useEffect(() => {
    if (!(me.error instanceof ApiError && me.error.status === 403)) return;
    const u = auth.currentUser;
    // Users added in the Firebase console start unverified, and the server refuses unverified emails
    if (u && !u.emailVerified) {
      sendEmailVerification(u)
        .then(() => setNotice(`We've emailed a verification link to ${u.email}. Open it, then sign in again.`))
        .catch(() => setNotice("Your email isn't verified yet, and the verification email couldn't be sent. Try again in a few minutes."))
        .finally(() => signOut(auth));
    } else {
      setNotice("Your account is not allowed to use this app.");
      signOut(auth);
    }
  }, [me.error]);
  // Sign out after IDLE_MS with no mouse, key, scroll or touch activity in ANY tab (they share the sign-in,
  // so they share the clock through localStorage). Reopening the browser after a long gap signs out at once.
  useEffect(() => {
    if (!user) return;
    const expire = () => {
      setNotice(`You were signed out after ${IDLE_MS / 60_000} minutes of inactivity.`);
      signOut(auth);
    };
    if (Date.now() - lastActive() > IDLE_MS) { expire(); return; }
    markActive();
    let wrote = Date.now();
    const touch = () => { if (Date.now() - wrote > 5_000) { wrote = Date.now(); markActive(); } };
    const check = window.setInterval(() => { if (Date.now() - lastActive() > IDLE_MS) expire(); }, 15_000);
    const events = ["pointerdown", "keydown", "wheel", "touchstart", "mousemove"];
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    return () => { clearInterval(check); events.forEach((e) => window.removeEventListener(e, touch)); };
  }, [user]);
  return { user, me, notice, clearNotice: () => setNotice("") };
}
