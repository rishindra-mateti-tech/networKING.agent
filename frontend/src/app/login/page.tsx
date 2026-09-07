"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Script from "next/script";
import Link from "next/link";
import { AlertCircle, ArrowLeft } from "lucide-react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (resp: { credential: string }) => void }) => void;
          renderButton: (parent: HTMLElement, options: Record<string, string>) => void;
        };
      };
    };
  }
}

export default function LoginPage() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const googleButtonRef = useRef<HTMLDivElement>(null);
  // Whether Google's button actually made it onto the page, so the "or" divider
  // never appears above an empty space, and so a visitor whose network blocks
  // accounts.google.com is told to use email rather than left staring at a gap.
  const [googleReady, setGoogleReady] = useState(false);
  const [googleUnavailable, setGoogleUnavailable] = useState(false);
  const googleRenderedRef = useRef(false);

  useEffect(() => {
    if (localStorage.getItem("token")) {
      router.replace("/");
      return;
    }
    if (window.location.search.includes("mode=register")) {
      setAuthMode("register");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleGoogleCredential = async (resp: { credential: string }) => {
    setAuthError("");
    setSubmitting(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential: resp.credential }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAuthError(data.detail || "Google sign-in failed");
        setSubmitting(false);
        return;
      }
      localStorage.setItem("token", data.access_token);
      router.push("/");
    } catch (err) {
      setAuthError("Failed to connect to backend");
      setSubmitting(false);
    }
  };

  const initGoogleButton = () => {
    if (googleRenderedRef.current) return true;
    if (!GOOGLE_CLIENT_ID || !window.google?.accounts?.id || !googleButtonRef.current) return false;
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: handleGoogleCredential,
    });
    window.google.accounts.id.renderButton(googleButtonRef.current, {
      theme: "filled_black",
      shape: "pill",
      size: "large",
      width: "336",
      text: "continue_with",
    });
    googleRenderedRef.current = true;
    setGoogleReady(true);
    return true;
  };

  // Google's script and this component can finish in either order, and once
  // next/script has loaded a src it does not fire onLoad again for the same
  // script on a later client-side navigation. Arriving at /login from the
  // landing page could therefore leave the button unrendered -- a visitor
  // signing up for the first time had no Google option at all -- while a hard
  // refresh reloaded the script and happened to win the race. Retrying until
  // both halves exist removes the ordering dependency entirely.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || initGoogleButton()) return;
    const poll = setInterval(() => {
      if (initGoogleButton()) clearInterval(poll);
    }, 100);
    const giveUp = setTimeout(() => {
      clearInterval(poll);
      if (!googleRenderedRef.current) setGoogleUnavailable(true);
    }, 8000);
    return () => {
      clearInterval(poll);
      clearTimeout(giveUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    setSubmitting(true);
    const path = authMode === "login" ? "/api/auth/login" : "/api/auth/register";

    try {
      const res = await fetch(`${BACKEND_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();

      if (!res.ok) {
        setAuthError(data.detail || "Authentication failed");
        setSubmitting(false);
        return;
      }

      if (authMode === "login") {
        localStorage.setItem("token", data.access_token);
        router.push("/");
        return;
      }

      // Registered successfully, auto login
      const loginRes = await fetch(`${BACKEND_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const loginData = await loginRes.json();
      if (loginRes.ok) {
        localStorage.setItem("token", loginData.access_token);
        router.push("/");
        return;
      }
      setAuthMode("login");
      setAuthError("Account created. Sign in to continue.");
    } catch (err) {
      setAuthError("Failed to connect to backend");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col justify-center items-center px-4 relative">
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(ellipse 600px 400px at 50% 40%, rgba(77,133,101,0.08), transparent 70%)" }}
      />

      <Link
        href="/"
        className="absolute top-6 left-6 flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <ArrowLeft size={14} />
        Back to networKING.agent
      </Link>

      <div className="max-w-sm w-full relative">
        <div className="text-center mb-8">
          <img src="/icon-192.png" alt="networKING.agent" className="w-10 h-10 mx-auto mb-4" />
          <h1 className="text-2xl font-extrabold tracking-tight text-[#ebe5d6]">
            networ<span className="text-[#4d8565]">KING</span>.agent
          </h1>
          <p className="text-sm text-zinc-500 mt-2">
            {authMode === "login"
              ? "Sign in to pick up your outreach pipeline."
              : "Create your account. Free with your own key."}
          </p>
        </div>

        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 shadow-2xl shadow-black/40">
          {GOOGLE_CLIENT_ID && (
            <>
              <Script
                src="https://accounts.google.com/gsi/client"
                strategy="afterInteractive"
                onReady={() => { initGoogleButton(); }}
              />
              <div ref={googleButtonRef} className="flex justify-center [&>div]:!w-full" />
              {!googleReady && !googleUnavailable && (
                <div className="h-10 rounded-full bg-white/[0.04] border border-white/10 animate-pulse" />
              )}
              {googleUnavailable && (
                <p className="text-[11px] text-zinc-500 text-center leading-relaxed">
                  Google sign-in couldn&apos;t load. Use your email and password below.
                </p>
              )}
              <div className="flex items-center gap-3 my-5">
                <div className="h-px flex-1 bg-white/10" />
                <span className="text-[11px] text-zinc-600 uppercase tracking-wider">or</span>
                <div className="h-px flex-1 bg-white/10" />
              </div>
            </>
          )}

          <form onSubmit={handleAuthSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full bg-black border border-white/10 rounded-lg px-4 py-2.5 text-sm text-zinc-200 focus:outline-none focus:border-[#4d8565]/60 focus:ring-1 focus:ring-[#4d8565]/40 transition-colors"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full bg-black border border-white/10 rounded-lg px-4 py-2.5 text-sm text-zinc-200 focus:outline-none focus:border-[#4d8565]/60 focus:ring-1 focus:ring-[#4d8565]/40 transition-colors"
                placeholder="••••••••"
              />
            </div>

            {authError && (
              <div className="flex items-center space-x-2 text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg p-3">
                <AlertCircle size={15} className="shrink-0" />
                <span>{authError}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-[#4d8565] hover:bg-[#5a9873] text-zinc-950 text-sm font-bold py-2.5 rounded-lg transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? "Please wait" : authMode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>
        </div>

        <div className="text-center mt-6">
          <button
            onClick={() => {
              setAuthMode(authMode === "login" ? "register" : "login");
              setAuthError("");
            }}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
          >
            {authMode === "login" ? "Need an account? " : "Already have an account? "}
            <span className="text-[#4d8565] font-medium">
              {authMode === "login" ? "Sign up" : "Log in"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
