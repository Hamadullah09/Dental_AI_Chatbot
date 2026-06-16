"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { login, register } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { UserRole } from "@/lib/types";

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
    <main className="center-content">
      <form className="auth-card" onSubmit={onSubmit}>
        <div>
          <span className="badge">Dental AI RAG</span>
          <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          <p className="muted">
            {mode === "login"
              ? "Sign in to continue your dental knowledge sessions."
              : "Choose a role and start using grounded dental AI."}
          </p>
        </div>

        <div className="form-grid">
          <div className="field">
            <label>Email</label>
            <input className="input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </div>
          <div className="field">
            <label>Password</label>
            <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} />
          </div>
          {mode === "register" ? (
            <>
              <div className="field">
                <label>Full name</label>
                <input className="input" value={fullName} onChange={(event) => setFullName(event.target.value)} />
              </div>
              <div className="field">
                <label>Role</label>
                <select className="select" value={role} onChange={(event) => setRole(event.target.value as UserRole)}>
                  <option value="patient">Patient</option>
                  <option value="student">Student</option>
                  <option value="dentist">Dentist</option>
                </select>
              </div>
            </>
          ) : null}
        </div>

        <button className="button" disabled={isLoading}>
          {isLoading ? "Please wait..." : mode === "login" ? "Sign in" : "Register"}
        </button>

        <p className="muted">
          {mode === "login" ? "Need an account? " : "Already registered? "}
          <Link href={mode === "login" ? "/register" : "/login"}>
            {mode === "login" ? "Create one" : "Sign in"}
          </Link>
        </p>
        <div className="status">{status}</div>
      </form>
    </main>
  );
}
