"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/lib/auth";
import { User, Mail, Calendar, Shield, Save, Check, Key } from "lucide-react";

function ProfileContent() {
  const { user } = useAuth();
  const [saved, setSaved] = useState(false);
  const [profile, setProfile] = useState({
    full_name: user?.full_name || "",
    email: user?.email || "",
  });
  const [passwords, setPasswords] = useState({
    current: "",
    new_password: "",
    confirm: "",
  });
  const [passwordError, setPasswordError] = useState("");
  const [passwordSaved, setPasswordSaved] = useState(false);

  const handleProfileSave = () => {
    localStorage.setItem("dental_ai_user", JSON.stringify({ ...user, ...profile }));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handlePasswordChange = () => {
    setPasswordError("");
    if (passwords.new_password.length < 8) {
      setPasswordError("Password must be at least 8 characters.");
      return;
    }
    if (passwords.new_password !== passwords.confirm) {
      setPasswordError("Passwords do not match.");
      return;
    }
    setPasswordSaved(true);
    setPasswords({ current: "", new_password: "", confirm: "" });
    setTimeout(() => setPasswordSaved(false), 2000);
  };

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-dental-textPrimary">Profile</h1>
        <p className="text-dental-textSecondary mt-1">Manage your account information.</p>
      </div>

      <section className="bg-dental-card border border-dental-border rounded-xl p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="h-16 w-16 rounded-full bg-dental-accent/20 flex items-center justify-center">
            <User className="h-8 w-8 text-dental-accent" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-dental-textPrimary">{user?.full_name || "User"}</h2>
            <p className="text-sm text-dental-textSecondary capitalize flex items-center gap-1">
              <Shield className="h-3 w-3" /> {user?.role}
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-sm text-dental-textSecondary flex items-center gap-1">
              <User className="h-3 w-3" /> Full Name
            </label>
            <input
              type="text"
              value={profile.full_name}
              onChange={(e) => setProfile((prev) => ({ ...prev, full_name: e.target.value }))}
              className="mt-1 w-full bg-dental-darkBg border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textPrimary"
            />
          </div>
          <div>
            <label className="text-sm text-dental-textSecondary flex items-center gap-1">
              <Mail className="h-3 w-3" /> Email
            </label>
            <input
              type="email"
              value={profile.email}
              disabled
              className="mt-1 w-full bg-dental-darkBg/50 border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textSecondary cursor-not-allowed"
            />
          </div>
          <div>
            <label className="text-sm text-dental-textSecondary flex items-center gap-1">
              <Calendar className="h-3 w-3" /> Member Since
            </label>
            <p className="mt-1 text-sm text-dental-textPrimary">
              {user?.created_at ? new Date(user.created_at).toLocaleDateString() : "N/A"}
            </p>
          </div>
        </div>

        <button
          onClick={handleProfileSave}
          className="mt-6 flex items-center gap-2 px-5 py-2 bg-dental-accent text-white rounded-lg text-sm font-medium hover:opacity-90"
        >
          {saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
          {saved ? "Saved!" : "Save Changes"}
        </button>
      </section>

      <section className="bg-dental-card border border-dental-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-dental-textPrimary mb-4 flex items-center gap-2">
          <Key className="h-5 w-5" /> Change Password
        </h2>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-dental-textSecondary">Current Password</label>
            <input
              type="password"
              value={passwords.current}
              onChange={(e) => setPasswords((prev) => ({ ...prev, current: e.target.value }))}
              className="mt-1 w-full bg-dental-darkBg border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textPrimary"
            />
          </div>
          <div>
            <label className="text-sm text-dental-textSecondary">New Password</label>
            <input
              type="password"
              value={passwords.new_password}
              onChange={(e) => setPasswords((prev) => ({ ...prev, new_password: e.target.value }))}
              className="mt-1 w-full bg-dental-darkBg border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textPrimary"
            />
          </div>
          <div>
            <label className="text-sm text-dental-textSecondary">Confirm New Password</label>
            <input
              type="password"
              value={passwords.confirm}
              onChange={(e) => setPasswords((prev) => ({ ...prev, confirm: e.target.value }))}
              className="mt-1 w-full bg-dental-darkBg border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textPrimary"
            />
          </div>
          {passwordError && <p className="text-xs text-red-500">{passwordError}</p>}
          <button
            onClick={handlePasswordChange}
            className="flex items-center gap-2 px-5 py-2 bg-dental-border text-dental-textPrimary rounded-lg text-sm font-medium hover:bg-dental-accent/20"
          >
            {passwordSaved ? <Check className="h-4 w-4" /> : <Key className="h-4 w-4" />}
            {passwordSaved ? "Password Updated!" : "Update Password"}
          </button>
        </div>
      </section>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <AuthGate>
      <AppShell title="Profile" subtitle="Manage your account.">
        <ProfileContent />
      </AppShell>
    </AuthGate>
  );
}
