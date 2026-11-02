import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const env = import.meta.env;
export const auth = getAuth(initializeApp({
  apiKey: env.VITE_FIREBASE_API_KEY, authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: env.VITE_FIREBASE_PROJECT_ID, appId: env.VITE_FIREBASE_APP_ID,
}));
