"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { login, register } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UserRole } from "@/lib/types";
import { Tooth, AlertCircle, KeyRound, Mail, User } from "lucide-react";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { saveAuth } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("patient");
  const [status, setStatus] = useState("");
  const [isLoading, setIsLoading] = useState(false);

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

  return (
    <main className="min-h-screen w-screen flex flex-col justify-center items-center bg-dental-darkBg px-4 py-8 select-none">
      <div className="w-full max-w-[420px] p-8 bg-dental-card border border-dental-border rounded-2xl shadow-2xl flex flex-col gap-6 fade-in">
        
        {/* Branding Logo */}
        <div className="text-center flex flex-col items-center gap-2">
          <div className="bg-dental-accent/10 p-3.5 rounded-2xl text-dental-accent shadow-md shadow-dental-accent/5">
            <Tooth size={28} />
          </div>
          <div className="mt-2 space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-white">
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="text-xs text-dental-textSecondary leading-normal max-w-[280px] mx-auto">
              {mode === "login"
                ? "Sign in to access your dental records and clinical AI consultations."
                : "Join Dental AI and explore grounded clinical knowledge sessions."}
            </p>
          </div>
        </div>

        {/* Form Grid */}
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="space-y-3">
            {/* Full Name for register */}
            {mode === "register" && (
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold text-dental-textSecondary uppercase tracking-wider">Full Name</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 w-4 h-4" />
                  <input 
                    className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-3 pl-10 pr-3 text-sm text-white focus:outline-none focus:border-dental-accent focus:ring-1 focus:ring-dental-accent/40 transition-all placeholder-gray-600" 
                    type="text" 
                    placeholder="Wazeer Ali"
                    value={fullName} 
                    onChange={(event) => setFullName(event.target.value)} 
                    required 
                  />
                </div>
              </div>
            )}

            {/* Email Address */}
            <div className="flex flex-col gap-1">
              <label className="text-[11px] font-semibold text-dental-textSecondary uppercase tracking-wider">Email Address</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 w-4 h-4" />
                <input 
                  className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-3 pl-10 pr-3 text-sm text-white focus:outline-none focus:border-dental-accent focus:ring-1 focus:ring-dental-accent/40 transition-all placeholder-gray-600" 
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
              <label className="text-[11px] font-semibold text-dental-textSecondary uppercase tracking-wider">Password</label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 w-4 h-4" />
                <input 
                  className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-3 pl-10 pr-3 text-sm text-white focus:outline-none focus:border-dental-accent focus:ring-1 focus:ring-dental-accent/40 transition-all placeholder-gray-600" 
                  type="password" 
                  placeholder="••••••••"
                  value={password} 
                  onChange={(event) => setPassword(event.target.value)} 
                  required 
                  minLength={8} 
                />
              </div>
            </div>

            {/* Role Select for Register */}
            {mode === "register" && (
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold text-dental-textSecondary uppercase tracking-wider">Clinical Workspace Role</label>
                <select 
                  className="w-full bg-dental-darkBg border border-dental-border rounded-xl py-3 px-3 text-sm text-white focus:outline-none focus:border-dental-accent transition-colors" 
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
            className="w-full bg-dental-accent hover:bg-dental-accentHover text-white py-3 rounded-xl text-sm font-bold shadow-lg shadow-dental-accent/10 hover:shadow-dental-accent/20 transition-all duration-150 disabled:opacity-50 mt-2" 
            disabled={isLoading}
          >
            {isLoading ? "Authenticating..." : mode === "login" ? "Sign In" : "Register"}
          </button>
        </form>

        {/* Footer Navigation */}
        <div className="text-center mt-2 flex flex-col gap-2">
          <p className="text-xs text-dental-textSecondary">
            {mode === "login" ? "Don't have an account? " : "Already registered? "}
            <Link 
              href={mode === "login" ? "/register" : "/login"} 
              className="text-dental-accent hover:text-dental-accentHover font-semibold transition-colors underline text-sm"
            >
              {mode === "login" ? "Create an account" : "Sign In"}
            </Link>
          </p>
        </div>

        {/* Status Prompt */}
        {status && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-400 text-xs rounded-xl flex gap-2 items-start animate-in fade-in">
            <AlertCircle size={15} className="mt-0.5 shrink-0" />
            <span>{status}</span>
          </div>
        )}
      </div>
    </main>
  );
}
