"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { login, register } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UserRole } from "@/lib/types";
import { AlertCircle, Eye, EyeOff, KeyRound, Mail, User } from "lucide-react";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { saveAuth } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("patient");
  const [status, setStatus] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setStatus("");
    try {
      const auth = mode === "login"
        ? await login({ email, password })
        : await register({ email, password, full_name: fullName, role });
      saveAuth(auth);
      router.push(auth.user.role === "admin" ? "/admin" : "/chat");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Authentication failed");
    } finally {
      setIsLoading(false);
    }
  }

  function handleForgotPassword() {
    setStatus("Password reset is not configured yet. Please contact the DentalGPT admin for account recovery.");
  }

  return (
    <main className="flex min-h-screen w-screen flex-col items-center justify-center bg-[#050505] px-4 py-8 text-white selection:bg-dental-accent selection:text-white">
      <div className="w-full max-w-[430px] rounded-[1.75rem] border border-white/10 bg-[#202020] p-8 shadow-2xl fade-in">
        
        {/* Branding Logo */}
        <div className="flex flex-col items-center text-center">
          <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-[#111111]">
            <Image src="/chatbot-logo.svg" alt="DentalGPT logo" width={40} height={40} className="h-10 w-10 object-contain" priority />
          </div>
          <div className="mt-5 space-y-2">
            <p className="text-xl font-extrabold tracking-tight">
              DentalGPT
            </p>
            <h1 className="text-2xl font-semibold tracking-tight">
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="mx-auto max-w-[300px] text-sm leading-6 text-white/55">
              {mode === "login"
                ? "Sign in to continue your dental AI workspace."
                : "Create a workspace for grounded dental consultations."}
            </p>
          </div>
        </div>

        {/* Form Grid */}
        <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-4">
          <div className="space-y-4">
            {/* Full Name for register */}
            {mode === "register" && (
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-white/55">Full Name</label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-white/40" />
                  <input 
                    className="w-full rounded-2xl border border-white/10 bg-[#050505] py-3.5 pl-11 pr-4 text-sm text-white outline-none transition-all placeholder:text-white/35 focus:border-dental-accent focus:ring-2 focus:ring-dental-accent/20" 
                    type="text" 
                    placeholder="Hamadullah"
                    value={fullName} 
                    onChange={(event) => setFullName(event.target.value)} 
                    required 
                  />
                </div>
              </div>
            )}

            {/* Email Address */}
            <div className="flex flex-col gap-1">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-white/55">Email Address</label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-white/40" />
                <input 
                  className="w-full rounded-2xl border border-white/10 bg-[#050505] py-3.5 pl-11 pr-4 text-sm text-white outline-none transition-all placeholder:text-white/35 focus:border-dental-accent focus:ring-2 focus:ring-dental-accent/20" 
                  type="email" 
                  placeholder="name@example.com"
                  value={email} 
                  onChange={(event) => setEmail(event.target.value)} 
                  required 
                />
              </div>
            </div>

            {/* Password */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-3">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-white/55">Password</label>
                {mode === "login" && (
                  <button
                    type="button"
                    onClick={handleForgotPassword}
                    className="text-xs font-medium text-dental-accent transition-colors hover:text-dental-accentHover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/40"
                  >
                    Forgot password?
                  </button>
                )}
              </div>
              <div className="relative">
                <KeyRound className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-white/40" />
                <input 
                  className="w-full rounded-2xl border border-white/10 bg-[#050505] py-3.5 pl-11 pr-12 text-sm text-white outline-none transition-all placeholder:text-white/35 focus:border-dental-accent focus:ring-2 focus:ring-dental-accent/20" 
                  type={showPassword ? "text" : "password"} 
                  placeholder="••••••••"
                  value={password} 
                  onChange={(event) => setPassword(event.target.value)} 
                  required 
                  minLength={8} 
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  className="absolute right-3 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-white/45 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dental-accent/40"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  title={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Role Select for Register */}
            {mode === "register" && (
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-white/55">Clinical Workspace Role</label>
                <select 
                  className="w-full rounded-2xl border border-white/10 bg-[#050505] px-4 py-3.5 text-sm text-white outline-none transition-colors focus:border-dental-accent focus:ring-2 focus:ring-dental-accent/20" 
                  value={role} 
                  onChange={(event) => setRole(event.target.value as UserRole)}
                >
                  <option value="patient">Patient (Symptom consultation)</option>
                  <option value="student">Dental Student (Educational research)</option>
                  <option value="dentist">Specialist Dentist (Clinical decision support)</option>
                </select>
              </div>
            )}
          </div>

          {/* Submit Button */}
          <button 
            type="submit"
            className="mt-2 w-full rounded-2xl bg-white py-3.5 text-sm font-bold text-black shadow-lg transition-all duration-150 hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-50" 
            disabled={isLoading}
          >
            {isLoading ? "Authenticating..." : mode === "login" ? "Sign In" : "Register"}
          </button>
        </form>

        {/* Footer Navigation */}
        <div className="mt-6 flex flex-col gap-2 text-center">
          <p className="text-sm text-white/55">
            {mode === "login" ? "Don't have an account? " : "Already registered? "}
            <Link 
              href={mode === "login" ? "/register" : "/login"} 
              className="font-semibold text-dental-accent underline transition-colors hover:text-dental-accentHover"
            >
              {mode === "login" ? "Create an account" : "Sign In"}
            </Link>
          </p>
        </div>

        {/* Status Prompt */}
        {status && (
          <div className="mt-4 flex items-start gap-2 rounded-2xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300 animate-in fade-in">
            <AlertCircle size={15} className="mt-0.5 shrink-0" />
            <span>{status}</span>
          </div>
        )}
      </div>
    </main>
  );
}
