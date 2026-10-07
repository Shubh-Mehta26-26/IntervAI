export type User = { id: string; email: string; display_name: string; role: "candidate" | "recruiter" | "admin"; is_active: boolean; created_at: string };
export type Session = { user: User; csrf_token: string; expires_at: string };
export type Goal = { role_title: string; priority: number; active: boolean };
export type Education = { institution: string; qualification: string; field_of_study: string | null; start_date: string | null; end_date: string | null };
export type Experience = { organization: string; title: string; description: string | null; start_date: string | null; end_date: string | null };
export type Preferences = { interview_mode: "text" | "voice"; interview_duration_minutes: 10 | 20 | 30 | 45 | 60; locale: "en" | "hi" | "en-IN" };
export type Profile = {
  id: string; user_id: string; display_name: string; email: string;
  phone: string | null; location: string | null; headline: string | null;
  biography: string | null; timezone: string; experience_months: number;
  revision: number; career_interests: string[]; goals: Goal[];
  education: Education[]; experience: Experience[]; preferences: Preferences;
  created_at: string; updated_at: string;
};
