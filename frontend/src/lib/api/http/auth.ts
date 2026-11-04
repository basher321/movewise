// Sign-up, sign-in, sign-out, the session and the applicant's own
// profile (B03).

import type {
  AdminUser,
  ApplicantAccount,
  Module,
  ProfileInput,
  Session,
  SetupStatus,
  SignOutTarget,
} from "../types";
import { get, patch, post } from "./client";

export const getSetupStatus = () => get<SetupStatus>("/auth/setup-status");

// Staff sign-up: always waits for the Super Admin's approval (B14).
export const adminSignUp = (name: string, email: string, password: string) =>
  post<AdminUser>("/auth/admin/signup", { name, email, password });

export const adminSignIn = (email: string, password: string) => post<AdminUser>("/auth/admin/signin", { email, password });

// The Super Admin's own page (B14). Sign-up works only while no Super Admin exists.
export const superAdminSignUp = (name: string, email: string, password: string, setupToken?: string) =>
  post<AdminUser>("/auth/super/signup", { name, email, password, setup_token: setupToken ?? "" });

export const superAdminSignIn = (email: string, password: string) => post<AdminUser>("/auth/super/signin", { email, password });

// The signed-in staff member's own name, email and password (B13). currentPassword is needed
// only when the email changes.
export const updateMyAdminAccount = (name: string, email: string, currentPassword: string) =>
  patch<AdminUser>("/auth/admin/me", { name, email, current_password: currentPassword });

export async function changeMyAdminPassword(currentPassword: string, newPassword: string): Promise<void> {
  await post("/auth/admin/password", { current_password: currentPassword, new_password: newPassword });
}

// Owner decision (2026-11-01): username and password, signed in at once, no email code.
// Email and mobile are optional. A forgotten password is reset by staff.
export interface SignUpInput {
  name: string;
  username: string;
  password: string;
  email: string;
  phone: string;
}

export const applicantSignUp = (module: Module, input: SignUpInput) => post<ApplicantAccount>(`/auth/applicant/${module}/signup`, input);

// login is the username, or the email for accounts made before usernames.
export const applicantSignIn = (module: Module, login: string, password: string) =>
  post<ApplicantAccount>(`/auth/applicant/${module}/signin`, { login, password });

export async function signOut(target: SignOutTarget): Promise<void> {
  await post("/auth/signout", { target });
}

export const getSession = () => get<Session>("/auth/session");

// "Forgot password?" by email link (B15). kind "admin" is any staff sign-in (email);
// a module is that module's applicant account (username or email).
export type ResetKind = "admin" | Module;

export const getPasswordOptions = () => get<{ email: boolean }>("/auth/password/options");

export async function forgotPassword(kind: ResetKind, login: string): Promise<void> {
  await post("/auth/password/forgot", { kind, login });
}

export const resetPassword = (token: string, newPassword: string) =>
  post<{ ok: true; kind: ResetKind }>("/auth/password/reset", { token, new_password: newPassword });

export const updateMyProfile = (module: Module, input: ProfileInput) => patch<ApplicantAccount>(`/me/${module}/profile`, input);

export async function changeMyPassword(module: Module, currentPassword: string, newPassword: string): Promise<void> {
  await post(`/me/${module}/password`, { current_password: currentPassword, new_password: newPassword });
}
