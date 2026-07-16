"use client";

import React, { useState, useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/lib/auth";
import { useTheme, type Theme } from "@/lib/theme";
import { getSettings, updateSettings, downloadPersonalData, deleteAccount } from "@/lib/api";
import type { UserSettings } from "@/lib/types";
import { Sun, Moon, Monitor, Save, Check, Download, Trash2, AlertCircle } from "lucide-react";

function SettingsContent() {
  const { user, token, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [settings, setSettings] = useState<UserSettings>({
    theme: theme,
    language: "en",
    timezone: "UTC",
    email_notifications: true,
    push_notifications: true,
    chat_history_retention_days: 90,
    data_sharing_consent: false,
    hipaa_consent: false,
    ai_disclaimer_acknowledged: false,
  });

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    setSettings((prev) => ({ ...prev, theme }));
  }, [theme]);

  async function loadSettings() {
    try {
      setLoading(true);
      const data = await getSettings(token!);
      setSettings(data);
      setTheme(data.theme as Theme);
    } catch {
      // Settings may not exist yet, use defaults
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    try {
      setError("");
      await updateSettings(settings, token!);
      setTheme(settings.theme as Theme);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(e.message || "Failed to save settings");
    }
  }

  async function handleDownloadData() {
    try {
      setDownloading(true);
      const blob = await downloadPersonalData(token!);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "my-dental-data.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message || "Failed to download data");
    } finally {
      setDownloading(false);
    }
  }

  async function handleDeleteAccount() {
    if (!confirm("This will permanently delete your account and all data. Are you sure?")) return;
    if (!confirm("This action CANNOT be undone. Type 'DELETE' in your mind and confirm.")) return;
    try {
      setDeleting(true);
      await deleteAccount(token!);
      logout();
    } catch (e: any) {
      setError(e.message || "Failed to delete account");
      setDeleting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-dental-textPrimary">Settings</h1>
        <p className="text-dental-textSecondary mt-1">Manage your preferences and account settings.</p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

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
                <p className="text-xs text-dental-textSecondary">Receive push notifications</p>
              </div>
              <button
                onClick={() => setSettings((prev) => ({ ...prev, push_notifications: !prev.push_notifications }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings.push_notifications ? "bg-dental-accent" : "bg-dental-border"
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  settings.push_notifications ? "translate-x-5" : ""
                }`} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-dental-textPrimary">Email Notifications</p>
                <p className="text-xs text-dental-textSecondary">Get email updates about appointments and prescriptions</p>
              </div>
              <button
                onClick={() => setSettings((prev) => ({ ...prev, email_notifications: !prev.email_notifications }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings.email_notifications ? "bg-dental-accent" : "bg-dental-border"
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  settings.email_notifications ? "translate-x-5" : ""
                }`} />
              </button>
            </div>
          </div>
        </section>

        <section className="bg-dental-card border border-dental-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-dental-textPrimary mb-4">Preferences</h2>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
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
              <div>
                <label className="text-sm text-dental-textSecondary">Timezone</label>
                <select
                  value={settings.timezone}
                  onChange={(e) => setSettings((prev) => ({ ...prev, timezone: e.target.value }))}
                  className="mt-1 w-full bg-dental-darkBg border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textPrimary"
                >
                  <option value="UTC">UTC</option>
                  <option value="Asia/Karachi">Pakistan (PKT)</option>
                  <option value="Asia/Dubai">UAE (GST)</option>
                  <option value="America/New_York">Eastern (ET)</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-sm text-dental-textSecondary">Chat History Retention</label>
              <select
                value={settings.chat_history_retention_days}
                onChange={(e) => setSettings((prev) => ({ ...prev, chat_history_retention_days: Number(e.target.value) }))}
                className="mt-1 w-full bg-dental-darkBg border border-dental-border rounded-lg px-3 py-2 text-sm text-dental-textPrimary"
              >
                <option value={30}>30 days</option>
                <option value={90}>90 days</option>
                <option value={180}>6 months</option>
                <option value={365}>1 year</option>
              </select>
            </div>
          </div>
        </section>

        <section className="bg-dental-card border border-dental-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-dental-textPrimary mb-4">Privacy & Security</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-dental-textPrimary">Data Sharing Consent</p>
                <p className="text-xs text-dental-textSecondary">Help improve the AI by sharing anonymized data</p>
              </div>
              <button
                onClick={() => setSettings((prev) => ({ ...prev, data_sharing_consent: !prev.data_sharing_consent }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings.data_sharing_consent ? "bg-dental-accent" : "bg-dental-border"
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  settings.data_sharing_consent ? "translate-x-5" : ""
                }`} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-dental-textPrimary">HIPAA Consent</p>
                <p className="text-xs text-dental-textSecondary">Acknowledge HIPAA data handling policies</p>
              </div>
              <button
                onClick={() => setSettings((prev) => ({ ...prev, hipaa_consent: !prev.hipaa_consent }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings.hipaa_consent ? "bg-dental-accent" : "bg-dental-border"
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                  settings.hipaa_consent ? "translate-x-5" : ""
                }`} />
              </button>
            </div>
          </div>
        </section>

        <section className="bg-dental-card border border-dental-border rounded-xl p-6">
          <h2 className="text-lg font-semibold text-dental-textPrimary mb-4">Account</h2>
          <div className="space-y-3 text-sm">
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
          <div className="mt-4 pt-4 border-t border-dental-border flex flex-wrap gap-3">
            <button
              onClick={handleDownloadData}
              disabled={downloading}
              className="flex items-center gap-2 px-4 py-2 text-sm text-dental-accent hover:bg-dental-accentSoft rounded-lg transition-colors"
            >
              <Download className="w-4 h-4" />
              {downloading ? "Downloading..." : "Download My Data"}
            </button>
            <button
              onClick={handleDeleteAccount}
              disabled={deleting}
              className="flex items-center gap-2 px-4 py-2 text-sm text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              {deleting ? "Deleting..." : "Delete Account"}
            </button>
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
