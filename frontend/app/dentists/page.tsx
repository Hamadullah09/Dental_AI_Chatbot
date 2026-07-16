"use client";

import { useState, useEffect } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { useAuth } from "@/lib/auth";
import { getDentists } from "@/lib/api";
import type { Dentist } from "@/lib/types";
import { Search, MapPin, Star, Clock, Phone, Filter } from "lucide-react";

const SPECIALIZATIONS = [
  { value: "", label: "All Specializations" },
  { value: "general", label: "General Dentistry" },
  { value: "orthodontics", label: "Orthodontics" },
  { value: "periodontics", label: "Periodontics" },
  { value: "endodontics", label: "Endodontics" },
  { value: "prosthodontics", label: "Prosthodontics" },
  { value: "oral_surgery", label: "Oral Surgery" },
  { value: "pediatric", label: "Pediatric Dentistry" },
  { value: "cosmetic", label: "Cosmetic Dentistry" },
  { value: "implantology", label: "Implantology" },
];

function DentistsContent() {
  const { token } = useAuth();
  const [dentists, setDentists] = useState<Dentist[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [specFilter, setSpecFilter] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    loadDentists();
  }, [specFilter]);

  async function loadDentists() {
    try {
      setLoading(true);
      setError("");
      const data = await getDentists({ token: token!, specialization: specFilter || undefined });
      setDentists(data);
    } catch (e: any) {
      setError(e.message || "Failed to load dentists");
    } finally {
      setLoading(false);
    }
  }

  const filtered = dentists.filter(
    (d) =>
      !search ||
      d.full_name.toLowerCase().includes(search.toLowerCase()) ||
      d.clinic_name?.toLowerCase().includes(search.toLowerCase()) ||
      d.specialization.some((s) => s.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dental-textMuted" />
          <input
            type="text"
            placeholder="Search by name, clinic, or specialization..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary placeholder:text-dental-textMuted focus:outline-none focus:border-dental-accent"
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dental-textMuted" />
          <select
            value={specFilter}
            onChange={(e) => setSpecFilter(e.target.value)}
            className="pl-10 pr-8 py-2.5 bg-dental-input border border-dental-border rounded-xl text-dental-textPrimary focus:outline-none focus:border-dental-accent appearance-none cursor-pointer"
          >
            {SPECIALIZATIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 text-sm">{error}</div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-dental-card border border-dental-border rounded-2xl p-6 animate-pulse">
              <div className="h-12 w-12 bg-dental-muted rounded-full mb-4" />
              <div className="h-5 bg-dental-muted rounded w-2/3 mb-2" />
              <div className="h-4 bg-dental-muted rounded w-1/2 mb-4" />
              <div className="h-3 bg-dental-muted rounded w-full mb-2" />
              <div className="h-3 bg-dental-muted rounded w-3/4" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-dental-textMuted text-lg">No dentists found</p>
          <p className="text-dental-textMuted text-sm mt-1">Try adjusting your search or filters</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((dentist) => (
            <div
              key={dentist.id}
              className="bg-dental-card border border-dental-border rounded-2xl p-6 hover:border-dental-accent/50 transition-colors"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 rounded-full bg-dental-accent/10 flex items-center justify-center text-dental-accent font-semibold text-lg">
                  {dentist.full_name.charAt(0)}
                </div>
                <div className="min-w-0">
                  <h3 className="font-semibold text-dental-textPrimary truncate">{dentist.full_name}</h3>
                  <p className="text-sm text-dental-textMuted truncate">
                    {dentist.qualification || "Dentist"}
                  </p>
                </div>
              </div>

              {dentist.specialization.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {dentist.specialization.map((s) => (
                    <span
                      key={s}
                      className="px-2 py-0.5 bg-dental-accentSoft text-dental-accent text-xs rounded-full"
                    >
                      {s.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              )}

              <div className="space-y-2 text-sm text-dental-textSecondary">
                {dentist.clinic_name && (
                  <div className="flex items-center gap-2">
                    <MapPin className="w-3.5 h-3.5 text-dental-textMuted shrink-0" />
                    <span className="truncate">{dentist.clinic_name}</span>
                  </div>
                )}
                {dentist.experience_years != null && (
                  <div className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-dental-textMuted shrink-0" />
                    <span>{dentist.experience_years} years experience</span>
                  </div>
                )}
                {dentist.consultation_fee != null && (
                  <div className="flex items-center gap-2">
                    <Star className="w-3.5 h-3.5 text-dental-textMuted shrink-0" />
                    <span>PKR {dentist.consultation_fee.toLocaleString()} consultation</span>
                  </div>
                )}
              </div>

              {dentist.languages.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {dentist.languages.map((lang) => (
                    <span key={lang} className="text-xs text-dental-textMuted bg-dental-muted px-2 py-0.5 rounded-full">
                      {lang}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-4 pt-4 border-t border-dental-border flex items-center justify-between">
                <span className={`text-xs font-medium ${dentist.is_available ? "text-green-400" : "text-dental-textMuted"}`}>
                  {dentist.is_available ? "Available" : "Unavailable"}
                </span>
                <a
                  href={`/appointments?dentist=${dentist.id}`}
                  className="text-sm font-medium text-dental-accent hover:text-dental-accentHover transition-colors"
                >
                  Book Appointment
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DentistsPage() {
  return (
    <AuthGate>
      <AppShell title="Find Dentists" subtitle="Browse our network of qualified dental professionals.">
        <DentistsContent />
      </AppShell>
    </AuthGate>
  );
}
