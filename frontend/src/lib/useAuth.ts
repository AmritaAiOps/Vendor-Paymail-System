import { useQuery, useQueryClient } from "@tanstack/react-query";
import { onAuthStateChanged, signOut, type User } from "firebase/auth";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { auth } from "../firebase";

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
    if (me.error instanceof ApiError && me.error.status === 403) {
      setNotice("Your account is not allowed to use this app.");
      signOut(auth);
    }
  }, [me.error]);
  return { user, me, notice, clearNotice: () => setNotice("") };
}
