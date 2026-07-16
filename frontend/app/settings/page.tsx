"use client";

import React, { useState, useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/lib/auth";
import { useTheme, type Theme } from "@/lib/theme";
import { Sun, Moon, Monitor, Save, Check } from "lucide-react";

function SettingsContent() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [saved, setSaved] = useState(false);
  const [settings, setSettings] = useState({
    theme: theme,
    notifications: true,
    emailUpdates: false,
    language: "en",
    responseLength: "balanced",
  });

  useEffect(() => {
    setSettings((prev) => ({ ...prev, theme }));
  }, [theme]);

  const handleSave = () => {
    setTheme(settings.theme as any);
    localStorage.setItem("dental_ai_settings", JSON.stringify(settings));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-dental-textPrimary">Settings</h1>
        <p className="text-dental-textSecondary mt-1">Manage your preferences and account settings.</p>
      </div>

      <div className="space-y-6">
        <section className="bg-dental-card border border-dental-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-dental-textPrimary mb-4">Appearance</h2>
          <div className="space-y-3">
            <label className="text-sm text-dental-textSecondary">Theme</label>
            <div className="flex gap-3">
              {[
                { value: "light", icon: Sun, label: "Light" },
                { value: "dark", icon: Moon, label: "Dark" },
                { value: "system", icon: Monitor, label: "System" },
              ].map(({ value, icon: Icon, label }) => (
                <button
                  key={value}
                  onClick={() => setSettings((prev) => ({ ...prev, theme: value as Theme }))}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors ${
                    settings.theme === value
                      ? "border-dental-accent bg-dental-accent/10 text-dental-accent"
                      : "border-dental-border text-dental-textSecondary hover:border-dental-accent/50"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-dental-card border border-dental-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-dental-textPrimary mb-4">Notifications</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-dental-textPrimary">Push Notifications</p>
                <p className="text-xs text-dental-textSecondary">Receive notifications about document processing</p>
              </div>
              <button
                onClick={() => setSettings((prev) => ({ ...prev, notifications: !prev.notifications }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings.notifications ? "bg-dental-accent" : "bg-dental-border"
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  settings.notifications ? "translate-x-5" : ""
                }`} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-dental-textPrimary">Email Updates</p>
                <p className="text-xs text-dental-textSecondary">Get email updates about your account activity</p>
              </div>
              <button
                onClick={() => setSettings((prev) => ({ ...prev, emailUpdates: !prev.emailUpdates }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings.emailUpdates ? "bg-dental-accent" : "bg-dental-border"
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  settings.emailUpdates ? "translate-x-5" : ""
                }`} />
              </button>
            </div>
          </div>
        </section>

        <section className="bg-dental-card border border-dental-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-dental-textPrimary mb-4">Chat Preferences</h2>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-dental-textSecondary">Response Length</label>
              <select
                value={settings.responseLength}
                onChange={(e) => setSettings((prev) => ({ ...prev, responseLength: e.target.value }))}
                className="mt-1 w-full bg-dental-darkBg border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textPrimary"
              >
                <option value="concise">Concise</option>
                <option value="balanced">Balanced</option>
                <option value="detailed">Detailed</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-dental-textSecondary">Language</label>
              <select
                value={settings.language}
                onChange={(e) => setSettings((prev) => ({ ...prev, language: e.target.value }))}
                className="mt-1 w-full bg-dental-darkBg border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textPrimary"
              >
                <option value="en">English</option>
                <option value="ur">Urdu</option>
                <option value="ar">Arabic</option>
              </select>
            </div>
          </div>
        </section>

        <section className="bg-dental-card border border-dental-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-dental-textPrimary mb-4">Account</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-dental-textSecondary">Email</span>
              <span className="text-dental-textPrimary">{user?.email}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-dental-textSecondary">Role</span>
              <span className="text-dental-textPrimary capitalize">{user?.role}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-dental-textSecondary">Member since</span>
              <span className="text-dental-textPrimary">
                {user?.created_at ? new Date(user.created_at).toLocaleDateString() : "N/A"}
              </span>
            </div>
          </div>
        </section>

        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-6 py-2.5 bg-dental-accent text-white rounded-lg font-medium hover:opacity-90 transition-opacity"
        >
          {saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
          {saved ? "Saved!" : "Save Settings"}
        </button>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <AuthGate>
      <AppShell title="Settings" subtitle="Manage your preferences.">
        <SettingsContent />
      </AppShell>
    </AuthGate>
  );
}
